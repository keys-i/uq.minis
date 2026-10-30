import { readFileSync } from "node:fs";
import { defineConfig, type PlaywrightTestConfig } from "@playwright/test";

const settings = JSON.parse(
  readFileSync(new URL("../out/tools/playwright.json", import.meta.url), "utf8"),
) as PlaywrightTestConfig;

export default defineConfig({
  ...settings,
  use: {
    ...settings.use,
    launchOptions: { executablePath: process.env.MINIS_BROWSER || undefined },
  },
  webServer: {
    ...(settings.webServer as Exclude<PlaywrightTestConfig["webServer"], unknown[]>),
    command: "npm run dev -- --port 5174",
    reuseExistingServer: !process.env.CI,
  },
});
