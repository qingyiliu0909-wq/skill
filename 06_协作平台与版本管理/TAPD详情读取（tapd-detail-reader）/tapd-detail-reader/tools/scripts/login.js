"use strict";

const readline = require("readline");
const {
  getStorageStatePath,
  isLoginRequired,
  launchBrowserSession,
  openTapdPage,
  parseArgs,
  resolveBrowserName,
  saveConfig
} = require("./common");

function waitForEnter(message) {
  const reader = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise((resolve) => {
    reader.question(message, () => {
      reader.close();
      resolve();
    });
  });
}

async function waitForLoginAuto(page, maxWaitMs) {
  const intervalMs = 2000;
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    const needLogin = await isLoginRequired(page).catch(() => true);
    if (!needLogin) {
      return true;
    }
  }
  return false;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const browserName = resolveBrowserName(args.browser);
  const targetUrl = args.url || "https://www.tapd.cn/";
  const storageStatePath = getStorageStatePath(browserName);
  const session = await launchBrowserSession({
    browserName,
    headless: false,
    storageState: storageStatePath
  });

  try {
    await openTapdPage(session.page, targetUrl);
    if (args.auto) {
      console.log("Waiting for TAPD login (auto-detect, max 3 minutes)...");
      const success = await waitForLoginAuto(session.page, 180000);
      if (!success) {
        throw new Error("Timed out waiting for TAPD login.");
      }
    } else {
      console.log("Please complete TAPD login in the opened browser window.");
      console.log("After login is complete and the target page is visible, return here and press Enter.");
      await waitForEnter("Press Enter after TAPD login is complete: ");
    }

    if (await isLoginRequired(session.page)) {
      throw new Error("TAPD login is still required. Please complete login and run the command again.");
    }

    await session.context.storageState({ path: storageStatePath });
    saveConfig({
      browser: browserName,
      lastLoginAt: new Date().toISOString()
    });
    console.log(`Saved TAPD login state to ${storageStatePath}.`);
  } finally {
    await session.browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
