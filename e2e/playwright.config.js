// Tests navigateur : site compilé (frontend/build, REACT_APP_BACKEND_URL=http://127.0.0.1:8765)
// face à l'API simulée. Lancer depuis e2e/ : npx playwright test
const { defineConfig } = require("@playwright/test");

const python = process.env.PYTHON || "python";

module.exports = defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8766",
    viewport: { width: 390, height: 844 },
    screenshot: "only-on-failure",
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
  webServer: [
    { command: `${python} api_server.py`, url: "http://127.0.0.1:8765/api/health", timeout: 60_000, reuseExistingServer: false },
    { command: `${python} spa_server.py`, url: "http://127.0.0.1:8766/", timeout: 30_000, reuseExistingServer: false },
  ],
});
