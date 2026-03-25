import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the server/ HTMX stack (port 8100).
 *
 * The server must be running before tests execute.
 * Start it with:
 *   python tests/e2e/run_test_server.py
 *
 * Or let the webServer block below handle it automatically.
 */

const BASE_URL = process.env.BASE_URL || "http://localhost:8100";

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  timeout: 30_000,

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    command: ".venv/bin/python3 tests/e2e/run_test_server.py",
    url: `${BASE_URL}/`,
    reuseExistingServer: !process.env.CI,
    stdout: "ignore",
    stderr: "pipe",
    timeout: 15_000,
    cwd: "../../",
  },
});
