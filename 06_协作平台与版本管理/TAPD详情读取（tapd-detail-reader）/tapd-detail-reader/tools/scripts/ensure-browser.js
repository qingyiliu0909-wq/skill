"use strict";

const childProcess = require("child_process");
const path = require("path");
const { chromium } = require("playwright");
const {
  getBrowserSpec,
  loadConfig,
  parseArgs,
  resolveBrowserName,
  saveConfig
} = require("./common");

async function tryLaunch(browserName) {
  const spec = getBrowserSpec(browserName);
  const launchOptions = { headless: true };
  if (spec.channel) {
    launchOptions.channel = spec.channel;
  }

  const browser = await chromium.launch(launchOptions);
  await browser.close();
}

async function ensureBrowser(browserName) {
  try {
    await tryLaunch(browserName);
    return false;
  } catch (error) {
    const message = String(error && error.message ? error.message : error);
    if (!/executable doesn't exist|channel .* not found|browserType\.launch/i.test(message)) {
      throw error;
    }
  }

  const spec = getBrowserSpec(browserName);
  const cliPath = path.join(__dirname, "..", "node_modules", "playwright", "cli.js");
  const installResult = childProcess.spawnSync(process.execPath, [cliPath, "install", spec.installName], {
    cwd: path.join(__dirname, ".."),
    stdio: "inherit"
  });

  if (installResult.status !== 0) {
    throw new Error(`Failed to install ${spec.label}.`);
  }

  await tryLaunch(browserName);
  return true;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const browserName = resolveBrowserName(args.browser);
  const installed = await ensureBrowser(browserName);
  const current = loadConfig();
  saveConfig({
    ...current,
    browser: browserName
  });

  if (installed) {
    console.log(`Installed ${getBrowserSpec(browserName).label}.`);
    return;
  }

  console.log(`${getBrowserSpec(browserName).label} is ready.`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
