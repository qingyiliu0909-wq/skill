"use strict";

const {
  activateDetailTab,
  extractDetailText,
  getStorageStatePath,
  hasStorageState,
  isLoginRequired,
  launchBrowserSession,
  openTapdPage,
  parseArgs,
  resolveBrowserName
} = require("./common");

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url) {
    throw new Error("Missing required argument --url.");
  }

  const browserName = resolveBrowserName(args.browser);
  const storageStatePath = getStorageStatePath(browserName);
  if (!hasStorageState(browserName)) {
    console.error(`Missing TAPD login cache: ${storageStatePath}`);
    process.exit(10);
    return;
  }

  const session = await launchBrowserSession({
    browserName,
    headless: true,
    storageState: storageStatePath
  });

  try {
    await openTapdPage(session.page, args.url);
    if (await isLoginRequired(session.page)) {
      console.error("TAPD login cache is invalid or expired.");
      process.exit(10);
      return;
    }

    await activateDetailTab(session.page);
    const detailText = await extractDetailText(session.page);
    if (!detailText) {
      throw new Error("Unable to extract content from the TAPD detail tab.");
    }

    process.stdout.write(`${detailText}\n`);
  } finally {
    await session.browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
