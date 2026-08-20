import { mkdir, rm } from "node:fs/promises";

await rm("reports/browser", { force: true, recursive: true });
await rm("reports/cucumber", { force: true, recursive: true });
await mkdir("reports/browser/screenshots", { recursive: true });
await mkdir("reports/browser/traces", { recursive: true });
await mkdir("reports/cucumber", { recursive: true });
