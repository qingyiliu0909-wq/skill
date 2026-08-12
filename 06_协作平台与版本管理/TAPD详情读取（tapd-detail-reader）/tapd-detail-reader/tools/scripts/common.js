"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const toolRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(toolRoot, "..", "..", "..", "..");
const cacheRoot = path.join(projectRoot, ".tapd-reader");
const configPath = path.join(cacheRoot, "config.json");

const browserSpecs = {
  edge: {
    key: "edge",
    label: "Microsoft Edge",
    channel: "msedge",
    installName: "msedge"
  },
  chrome: {
    key: "chrome",
    label: "Google Chrome",
    channel: "chrome",
    installName: "chrome"
  },
  chromium: {
    key: "chromium",
    label: "Chromium",
    channel: null,
    installName: "chromium"
  }
};

function ensureCacheRoot() {
  fs.mkdirSync(cacheRoot, { recursive: true });
}

function normalizeText(text) {
  return String(text || "")
    .replace(/\r/g, "")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function readJson(filePath) {
  if (!fs.existsSync(filePath)) {
    return null;
  }

  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, value) {
  ensureCacheRoot();
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function loadConfig() {
  return readJson(configPath) || {};
}

function saveConfig(nextConfig) {
  const current = loadConfig();
  writeJson(configPath, { ...current, ...nextConfig });
}

function resolveBrowserName(cliBrowser) {
  const browserName = cliBrowser || loadConfig().browser || "edge";
  if (!browserSpecs[browserName]) {
    throw new Error(`Unsupported browser "${browserName}". Expected one of: ${Object.keys(browserSpecs).join(", ")}.`);
  }

  return browserName;
}

function getBrowserSpec(browserName) {
  const spec = browserSpecs[browserName];
  if (!spec) {
    throw new Error(`Unknown browser "${browserName}".`);
  }

  return spec;
}

function getStorageStatePath(browserName) {
  ensureCacheRoot();
  return path.join(cacheRoot, `storage-state-${browserName}.json`);
}

function hasStorageState(browserName) {
  return fs.existsSync(getStorageStatePath(browserName));
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      continue;
    }

    const key = token.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
      continue;
    }

    args[key] = next;
    index += 1;
  }

  return args;
}

async function launchBrowserSession(options) {
  const browserName = resolveBrowserName(options.browserName);
  const spec = getBrowserSpec(browserName);
  const launchOptions = {
    headless: Boolean(options.headless),
    args: [
      "--disable-blink-features=AutomationControlled",
      "--disable-features=IsolateOrigins,site-per-process",
      "--disable-dev-shm-usage",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-infobars"
    ]
  };
  if (spec.channel) {
    launchOptions.channel = spec.channel;
  }

  const browser = await chromium.launch(launchOptions);
  const contextOptions = {
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    colorScheme: "light",
    deviceScaleFactor: 1.25,
    viewport: {
      width: 1600,
      height: 900
    },
    screen: {
      width: 1600,
      height: 900
    },
    userAgent: options.userAgent || "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
  };
  if (options.storageState && fs.existsSync(options.storageState)) {
    contextOptions.storageState = options.storageState;
  }

  const context = await browser.newContext(contextOptions);
  await context.addInitScript(() => {
    const override = (object, key, value) => {
      Object.defineProperty(object, key, {
        configurable: true,
        enumerable: true,
        get() {
          return value;
        }
      });
    };

    override(Navigator.prototype, "webdriver", false);
    override(Navigator.prototype, "language", "zh-CN");
    override(Navigator.prototype, "languages", ["zh-CN", "zh", "en-US", "en"]);
    override(Navigator.prototype, "platform", "Win32");
    override(Navigator.prototype, "hardwareConcurrency", 8);
    override(Navigator.prototype, "maxTouchPoints", 0);

    if (!window.chrome) {
      Object.defineProperty(window, "chrome", {
        configurable: true,
        enumerable: true,
        value: {
          app: {},
          runtime: {}
        }
      });
    }

    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {
      window.navigator.permissions.query = (parameters) => {
        if (parameters && parameters.name === "notifications") {
          return Promise.resolve({ state: Notification.permission });
        }

        return originalQuery.call(window.navigator.permissions, parameters);
      };
    }
  });

  await context.setExtraHTTPHeaders({
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8"
  });
  const page = await context.newPage();
  return { browser, context, page, browserName, spec };
}

function isProbablyLoginUrl(currentUrl) {
  const url = String(currentUrl || "").toLowerCase();
  return url.includes("login") || url.includes("signin") || url.includes("passport");
}

async function isLoginRequired(page) {
  if (isProbablyLoginUrl(page.url())) {
    return true;
  }

  const loginTexts = [
    "登录",
    "扫码登录",
    "账号登录",
    "TAPD 登录",
    "TAPD登录",
    "Sign in"
  ];

  for (const text of loginTexts) {
    const locator = page.getByText(text, { exact: false }).first();
    if (await locator.count() > 0) {
      try {
        if (await locator.isVisible()) {
          return true;
        }
      } catch (error) {
        void error;
      }
    }
  }

  return false;
}

async function openTapdPage(page, targetUrl) {
  await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(1200);
}

async function activateDetailTab(page) {
  const candidates = [
    page.getByRole("tab", { name: /详细信息/i }).first(),
    page.getByText("详细信息", { exact: true }).first(),
    page.locator("a, button, span, div").filter({ hasText: "详细信息" }).first()
  ];

  for (const locator of candidates) {
    try {
      if (await locator.count() === 0) {
        continue;
      }

      if (!(await locator.isVisible())) {
        continue;
      }

      await locator.click({ timeout: 5000 });
      await page.waitForTimeout(1000);
      return true;
    } catch (error) {
      void error;
    }
  }

  return false;
}

async function extractDetailText(page) {
  const content = await page.evaluate(() => {
    function normalize(text) {
      return String(text || "")
        .replace(/\r/g, "")
        .replace(/\u00a0/g, " ")
        .replace(/[ \t]+\n/g, "\n")
        .replace(/\n[ \t]+/g, "\n")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
    }

    function cleanDetailText(text) {
      return normalize(text)
        .replace(/^上级需求:[^\n]*\n?/u, "")
        .replace(/^展开详情\s*/u, "")
        .replace(/\n?编辑$/u, "")
        .trim();
    }

    function extractElementText(element) {
      const richRoot = element.matches(".cherry-editor-content, .content-wrap")
        ? element
        : element.querySelector(".cherry-editor-content, .content-wrap");

      if (richRoot && isVisible(richRoot)) {
        return cleanDetailText(richRoot.innerText || "");
      }

      return cleanDetailText(element.innerText || "");
    }

    function isVisible(element) {
      if (!(element instanceof HTMLElement)) {
        return false;
      }

      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      if (style.display === "none" || style.visibility === "hidden") {
        return false;
      }

      if (rect.width <= 0 || rect.height <= 0) {
        return false;
      }

      return true;
    }

    function extractFromPrioritySelectors() {
      const selectors = [
        ".tab-container-item.current-tab .detail-info-tab",
        ".tab-container-item.current-tab",
        ".detail-container-content .tab-detail-item.detail-item__content .cherry-editor-content",
        ".detail-container-content .tab-detail-item.detail-item__content .content-wrap",
        ".detail-container-content .detail-item__content-wrapper .cherry-editor-content",
        ".detail-container-content .detail-item__content-wrapper .content-wrap",
        ".detail-container-content .tab-detail-item.detail-item__content",
        ".detail-container-content .detail-item__content-wrapper",
        ".detail-container-content"
      ];

      const exactContentSelectors = selectors.slice(2, 8);
      for (const selector of exactContentSelectors) {
        const element = document.querySelector(selector);
        if (!element || !isVisible(element)) {
          continue;
        }

        const text = extractElementText(element);
        if (text) {
          return text;
        }
      }

      const activeTab = document.querySelector(".tab-container-item.current-tab");
      if (activeTab && normalize(activeTab.textContent || "").includes("详细信息")) {
        const detailContainer = document.querySelector(".detail-container-content");
        if (detailContainer && isVisible(detailContainer)) {
          const preferredChildren = Array.from(detailContainer.querySelectorAll(".cherry-editor-content, .content-wrap, .detail-item__content-wrapper, .tab-detail-item.detail-item__content"))
            .filter((element) => isVisible(element));

          for (const element of preferredChildren) {
            const text = extractElementText(element);
            if (text) {
              return text;
            }
          }
        }
      }

      return "";
    }

    function hasNoiseAncestor(element) {
      return Boolean(element.closest("nav, header, footer, aside"));
    }

    function score(element) {
      const text = normalize(element.innerText || "");
      if (!text) {
        return -1;
      }

      let total = Math.min(text.length, 6000);
      const className = String(element.className || "").toLowerCase();
      const id = String(element.id || "").toLowerCase();
      const role = String(element.getAttribute("role") || "").toLowerCase();

      if (role === "tabpanel") {
        total += 1200;
      }

      if (className.includes("tab") || className.includes("detail") || className.includes("story") || className.includes("desc")) {
        total += 600;
      }

      if (id.includes("detail") || id.includes("desc")) {
        total += 400;
      }

      if (/详细信息|需求描述|描述|验收标准|备注/.test(text)) {
        total += 1500;
      }

      if (element.querySelector("table")) {
        total += 250;
      }

      if (element.querySelector("p, li")) {
        total += 150;
      }

      return total;
    }

    function pickByActiveTab() {
      const possibleTabs = Array.from(document.querySelectorAll("[role='tab'], a, button, span, div")).filter((element) => {
        const text = normalize(element.textContent || "");
        if (!text.includes("详细信息")) {
          return false;
        }

        return isVisible(element);
      });

      for (const tab of possibleTabs) {
        const ariaControls = tab.getAttribute("aria-controls");
        if (ariaControls) {
          const panel = document.getElementById(ariaControls);
          if (panel && isVisible(panel)) {
            return panel;
          }
        }

        const href = tab.getAttribute("href");
        if (href && href.startsWith("#")) {
          const panel = document.querySelector(href);
          if (panel && isVisible(panel)) {
            return panel;
          }
        }
      }

      return null;
    }

    const exactContent = extractFromPrioritySelectors();
    if (exactContent) {
      return exactContent;
    }

    const panelFromActiveTab = pickByActiveTab();
    if (panelFromActiveTab) {
      return extractElementText(panelFromActiveTab);
    }

    const candidates = Array.from(document.querySelectorAll("[role='tabpanel'], .tab-content, .tab-pane, .detail, .details, .story-detail, main, article, section, div"))
      .filter((element) => isVisible(element) && !hasNoiseAncestor(element))
      .filter((element) => normalize(element.innerText || "").length >= 20);

    candidates.sort((left, right) => score(right) - score(left));
    const best = candidates[0] || document.body;
    return extractElementText(best);
  });

  return normalizeText(content);
}

module.exports = {
  cacheRoot,
  configPath,
  getBrowserSpec,
  getStorageStatePath,
  hasStorageState,
  isLoginRequired,
  launchBrowserSession,
  loadConfig,
  normalizeText,
  openTapdPage,
  parseArgs,
  projectRoot,
  resolveBrowserName,
  saveConfig,
  toolRoot,
  activateDetailTab,
  extractDetailText
};
