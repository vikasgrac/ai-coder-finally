import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  timeout: 60000,
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:8000",
    headless: true,
  },
  retries: 1,
  webServer: {
    command: "echo 'server already running'",
    url: process.env.BASE_URL || "http://localhost:8000",
    reuseExistingServer: true,
    timeout: 30000,
  },
});
