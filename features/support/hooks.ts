import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFile, spawn, type ChildProcess } from "node:child_process";
import { promisify } from "node:util";

import {
  After,
  AfterAll,
  Before,
  BeforeAll,
  setDefaultTimeout,
  Status,
  type ITestCaseHookParameter,
} from "@cucumber/cucumber";
import { chromium, type Browser } from "playwright";

import { CheckoutWorld } from "./world.ts";

let browser: Browser;
let serverProcess: ChildProcess;
let testDirectory: string;
let baseUrl: string;
let pythonExecutable: string;

const execFileAsync = promisify(execFile);

setDefaultTimeout(20_000);

BeforeAll(async () => {
  const port = await availablePort();
  testDirectory = await mkdtemp(join(tmpdir(), "payment-quality-lab-"));
  const databasePath = join(testDirectory, "browser-tests.db");
  const localPython = resolve(".venv/bin/python");
  pythonExecutable = existsSync(localPython) ? localPython : "python3";

  serverProcess = spawn(pythonExecutable, ["features/support/test_server.py"], {
    env: {
      ...process.env,
      PAYMENT_LAB_TEST_DATABASE_URL: `sqlite:///${databasePath}`,
      PAYMENT_LAB_TEST_PORT: String(port),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  serverProcess.stderr?.on("data", (chunk) => process.stderr.write(chunk));
  baseUrl = `http://127.0.0.1:${port}`;
  await waitUntilHealthy(baseUrl, serverProcess);
  browser = await chromium.launch();
});

Before(async function (this: CheckoutWorld, scenario: ITestCaseHookParameter) {
  const mobile = scenario.pickle.tags.some((tag) => tag.name === "@mobile");
  this.baseUrl = baseUrl;
  this.context = await browser.newContext({
    viewport: mobile ? { width: 390, height: 844 } : { width: 1280, height: 800 },
  });
  await this.context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  this.page = await this.context.newPage();
  this.page.on("request", (request) => {
    if (new URL(request.url()).origin !== baseUrl) {
      this.externalRequestUrls.push(request.url());
    }
    if (request.method() === "POST" && new URL(request.url()).pathname === "/payments") {
      this.paymentRequestCount += 1;
      const key = request.headers()["idempotency-key"];
      if (key) {
        this.observedIdempotencyKeys.push(key);
      }
    }
  });
});

After(async function (this: CheckoutWorld, scenario: ITestCaseHookParameter) {
  if (!this.context || !this.page) {
    return;
  }

  const failed = scenario.result?.status === Status.FAILED;
  const name = scenario.pickle.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  if (failed) {
    const screenshot = await this.page.screenshot({
      fullPage: true,
      path: `reports/browser/screenshots/${name}.png`,
    });
    await this.attach(screenshot, "image/png");
    const tracePath = `reports/browser/traces/${name}.zip`;
    await this.context.tracing.stop({ path: tracePath });
    await execFileAsync(pythonExecutable, ["scripts/sanitize_trace.py", tracePath]);
  } else {
    await this.context.tracing.stop();
  }
  await this.context.close();
});

AfterAll(async () => {
  await browser?.close();
  if (serverProcess && serverProcess.exitCode === null) {
    serverProcess.kill("SIGTERM");
    await Promise.race([
      new Promise<void>((resolveExit) => serverProcess.once("exit", () => resolveExit())),
      new Promise<void>((resolveTimeout) => setTimeout(resolveTimeout, 3_000)),
    ]);
  }
  if (testDirectory) {
    await rm(testDirectory, { force: true, recursive: true });
  }
});

async function availablePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("Could not reserve a browser-test port"));
        return;
      }
      server.close(() => resolvePort(address.port));
    });
  });
}

async function waitUntilHealthy(url: string, process: ChildProcess): Promise<void> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (process.exitCode !== null) {
      throw new Error(`Browser test server exited with code ${process.exitCode}`);
    }
    try {
      const response = await fetch(`${url}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      // Startup can refuse connections until Uvicorn is listening.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  throw new Error("Browser test server did not become healthy");
}
