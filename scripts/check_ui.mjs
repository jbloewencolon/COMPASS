/** Locked development audit; run only against a throwaway local demo database. */
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname } from "node:path";
import { parseArgs } from "node:util";
import { chromium } from "playwright";

const require = createRequire(import.meta.url);
const { values } = parseArgs({ options: {
  url: { type: "string", default: "http://127.0.0.1:8000" },
  "axe-script": { type: "string", default: require.resolve("axe-core/axe.min.js") },
  chromium: { type: "string" },
  output: { type: "string", default: "test-results/accessibility.json" },
} });
const url = new URL(values.url);
assert(["localhost", "127.0.0.1", "[::1]"].includes(url.hostname), "Use a local throwaway demo instance");

const report = { axe_version: null, checks: [], javascript_errors: [], detector_negative_case: null };
const browser = await chromium.launch({ executablePath: values.chromium || process.env.COMPASS_CHROMIUM || undefined });
try {
  // Test-only injection of the lockfile's axe script. App CSP is unchanged.
  const context = await browser.newContext({ bypassCSP: true, viewport: { width: 1280, height: 900 } });
  const health = await context.request.get(new URL("/api/health", url).href);
  assert(health.ok() && (await health.json()).mode === "synthetic_demo", "Refusing to change preferences outside the synthetic demo");

  // A deliberately inaccessible isolated page must be detected. It never enters
  // the application report or its database and guards against an inert audit.
  const probe = await context.newPage();
  await probe.setContent('<!doctype html><html lang="en"><head><title>Negative audit probe</title></head><body><main><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="></main></body></html>');
  await probe.addScriptTag({ path: values["axe-script"] });
  report.axe_version = await probe.evaluate(() => axe.version);
  const detected = await probe.evaluate(async () => (await axe.run(document, { runOnly: { type: "rule", values: ["image-alt"] } })).violations.some(item => item.id === "image-alt"));
  assert(detected, "The accessibility detector did not flag the known missing-alt error");
  report.detector_negative_case = { rule: "image-alt", detected: true };
  await probe.close();

  const page = await context.newPage();
  page.on("pageerror", error => report.javascript_errors.push(String(error)));
  await page.goto(url.href, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Alex Morgan/ }).click();
  await page.getByRole("button", { name: "Sources", exact: true }).waitFor();
  await page.addScriptTag({ path: values["axe-script"] });
  report.axe_version = await page.evaluate(() => axe.version);

  async function audit(name) {
    const result = await page.evaluate(async () => {
      const result = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } });
      const summarize = item => ({ id: item.id, impact: item.impact, help: item.help, help_url: item.helpUrl, targets: item.nodes.map(node => node.target) });
      return { violations: result.violations.map(summarize), incomplete: result.incomplete.map(summarize), passes: result.passes.length };
    });
    report.checks.push({ page: name, ...result });
  }

  for (const mode of ["simple", "advanced"]) {
    await Promise.all([
      page.waitForResponse(response => response.url().endsWith("/api/preferences") && response.request().method() === "PUT"),
      page.locator("#view-mode").selectOption(mode),
    ]);
    await page.getByRole("button", { name: "Sources", exact: true }).click();
    await page.getByRole("button", { name: "＋ Import source", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.waitFor();
    const notice = page.locator("#source-import-safety");
    assert(await notice.isVisible(), "Source import notice must remain visible");
    assert.equal(await notice.getAttribute("role"), "note");
    assert((await dialog.getByLabel("Preserved source text").getAttribute("aria-describedby") || "").split(/\s+/).includes("source-import-safety"), "Source text must describe the restricted-data notice");
    await audit(`${mode} source import`);
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    for (const name of ["Home", "Reviews", "Settings"]) {
      await page.getByRole("button", { name, exact: true }).click();
      await audit(`${mode} ${name}`);
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await page.getByRole("button", { name: "＋ Import source", exact: true }).click();
  assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), "Mobile source import overflows horizontally");
  await audit("mobile source import");
  assert.equal(report.javascript_errors.length, 0, "Browser JavaScript exceptions occurred");
  assert.equal(report.checks.length, 9, "All core page states must be audited");
  assert(!report.checks.some(check => check.violations.length), "Automated accessibility violations; inspect the report");
} catch (error) {
  report.error = String(error);
  process.exitCode = 1;
} finally {
  await browser.close();
  await mkdir(dirname(values.output), { recursive: true });
  await writeFile(values.output, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify({ checks: report.checks.length, violations: report.checks.filter(check => check.violations.length), javascript_errors: report.javascript_errors, error: report.error || null }, null, 2));
}
