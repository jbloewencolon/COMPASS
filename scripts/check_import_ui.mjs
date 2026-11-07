/** Development regression: source-file races and provenance, synthetic demo only. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { parseArgs } from "node:util";
import { chromium } from "playwright";

const { values } = parseArgs({ options: {
  url: { type: "string", default: "http://127.0.0.1:8000" },
  chromium: { type: "string" },
  output: { type: "string", default: "test-results/import-ui.json" },
} });
const url = new URL(values.url);
assert(["localhost", "127.0.0.1", "[::1]"].includes(url.hostname), "Use a local throwaway demo instance");
const report = { checks: [], javascript_errors: [], error: null };
const browser = await chromium.launch({ executablePath: values.chromium || process.env.COMPASS_CHROMIUM || undefined });
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const health = await context.request.get(new URL("/api/health", url).href);
  assert(health.ok() && (await health.json()).mode === "synthetic_demo", "Use a throwaway synthetic demo database");
  const page = await context.newPage();
  page.on("pageerror", error => report.javascript_errors.push(String(error)));
  const previews = new Map();
  const sourcePosts = [];
  const digest = bytes => createHash("sha256").update(bytes).digest("hex");

  // Only preview timing and source POST are intercepted. Login, page rendering,
  // workspace permissions, dashboard and seeded finding use the real local app.
  await page.route("**/api/import/pdf-text", async route => {
    const bytes = route.request().postDataBuffer();
    const name = bytes.toString("utf8");
    let release;
    const response = new Promise(resolve => { release = resolve; });
    previews.set(name, { bytes, release });
    const result = await response;
    await route.fulfill({ status: result.status || 200, json: result.body });
  });
  await page.route("**/api/sources", async route => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    const payload = route.request().postDataJSON();
    sourcePosts.push(payload);
    await route.fulfill({ status: 201, json: {
      ...payload, id: `synthetic-ui-capture-${sourcePosts.length}`, hash: digest(JSON.stringify(payload)),
      created_at: "2026-11-06T16:00:00Z",
    } });
  });
  async function waitUntil(predicate, message) {
    const limit = Date.now() + 5000;
    while (!predicate()) {
      assert(Date.now() < limit, message);
      await new Promise(resolve => setTimeout(resolve, 10));
    }
  }
  async function nextPaint() {
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  }
  async function openImport() {
    await page.getByRole("button", { name: "Sources", exact: true }).click();
    await page.getByRole("button", { name: "＋ Import source", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.waitFor();
    return { dialog, file: dialog.getByLabel("Choose a source file (optional)", { exact: true }),
      text: dialog.getByLabel("Preserved source text"), notice: dialog.getByRole("status") };
  }
  async function selectPdf(controls, name) {
    const bytes = Buffer.from(`%PDF-1.7\nsynthetic browser fixture ${name}\n%%EOF`);
    await controls.file.setInputFiles({ name: `${name}.pdf`, mimeType: "application/pdf", buffer: bytes });
    await waitUntil(() => previews.has(bytes.toString("utf8")), "PDF preview was not requested");
    assert(await controls.text.isDisabled(), "Source text must be disabled during extraction");
    return { ...previews.get(bytes.toString("utf8")), name };
  }
  function extraction(request, text, incomplete = false) {
    return { text, text_provenance: "extracted", original_sha256: digest(request.bytes),
      page_count: incomplete ? 2 : 1, page_spans: [{ page: 1, start: 0, end: text.length }],
      failed_pages: incomplete ? [{ page: 2, reason: "No extractable text; OCR is not available." }] : [] };
  }
  async function releasePreview(request, body, status = 200) {
    const finished = page.waitForResponse(response => response.url().endsWith("/api/import/pdf-text") &&
      response.request().postDataBuffer()?.equals(request.bytes));
    request.release({ status, body });
    const response = await finished;
    await response.finished();
    await nextPaint();
  }
  async function importCaptured(controls) {
    const previous = sourcePosts.length;
    await controls.dialog.getByRole("button", { name: "Import snapshot", exact: true }).click();
    await waitUntil(() => sourcePosts.length > previous, "Source import did not submit");
    await controls.dialog.waitFor({ state: "hidden" });
    return sourcePosts.at(-1);
  }

  await page.goto(url.href, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Alex Morgan/ }).click();
  await page.getByRole("button", { name: "Sources", exact: true }).waitFor();

  const controls = await openImport();
  const first = await selectPdf(controls, "first-slow");
  const middle = await selectPdf(controls, "middle-stale");
  const latest = await selectPdf(controls, "latest-partial");
  await releasePreview(middle, extraction(middle, "The stale middle office shall review records."));
  assert(await controls.text.isDisabled(), "An obsolete completion must not unlock the latest pending extraction");
  assert.equal(await controls.text.inputValue(), "", "An obsolete completion must not populate source text");
  report.checks.push("older completion cannot unlock or populate a newer pending selection");

  const latestText = "The latest office shall keep a public inventory.";
  const latestResult = extraction(latest, latestText, true);
  await releasePreview(latest, latestResult);
  assert(await controls.text.isEnabled(), "Latest completed extraction must enable editing");
  assert.equal(await controls.text.inputValue(), latestText);
  assert((await controls.notice.innerText()).includes("page 2"), "Partial extraction must disclose its missing page");
  await releasePreview(first, extraction(first, "The first slow office shall review records."));
  assert.equal(await controls.text.inputValue(), latestText, "Late obsolete preview must not overwrite latest text");
  report.checks.push("late obsolete preview cannot overwrite the latest text or provenance");

  const edited = latestText + "\nA reviewer corrected this synthetic transcription.";
  await controls.text.fill(edited);
  assert((await controls.notice.innerText()).includes("page 2"), "Editing must retain the original missing-page warning");
  const saved = await importCaptured(controls);
  assert.equal(saved.text, edited);
  assert.equal(saved.text_provenance, "transcribed");
  assert.equal(saved.original_sha256, latestResult.original_sha256);
  assert.deepEqual(saved.page_spans, []);
  assert.equal(saved.page_count, latestResult.page_count);
  assert.deepEqual(saved.failed_pages, latestResult.failed_pages);
  report.checks.push("manual editing clears page mapping and retains original hash, page count and failure disclosures");

  const rejected = await openImport();
  const previewCount = previews.size;
  await rejected.file.setInputFiles({ name: "unsupported.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("synthetic DOCX placeholder") });
  await page.waitForFunction(() => document.querySelector('input[type="file"]').files.length === 0);
  assert((await rejected.notice.innerText()).includes("DOCX is not supported"));
  assert.equal(await rejected.text.inputValue(), "");
  assert(await rejected.text.isEnabled());
  assert.equal(previews.size, previewCount, "DOCX must not be sent to the PDF extractor");
  report.checks.push("unsupported DOCX is refused without extraction or source creation");

  await rejected.file.setInputFiles({ name: "invalid.txt", mimeType: "text/plain", buffer: Buffer.from([0xff, 0xfe, 0xfd]) });
  await page.waitForFunction(() => document.querySelector('input[type="file"]').files.length === 0);
  assert.equal(await rejected.text.inputValue(), "");
  assert((await rejected.notice.innerText()).length > 0, "Invalid UTF-8 must have a visible error");
  report.checks.push("invalid UTF-8 text is refused without a fabricated transcription");

  const imageOnly = await selectPdf(rejected, "image-only");
  await releasePreview(imageOnly, { detail: "No PDF text could be extracted. OCR is not available.", failed_pages: [{ page: 1, reason: "No extractable text" }], page_count: 1 }, 422);
  assert.equal(await rejected.text.inputValue(), "");
  assert((await rejected.notice.innerText()).includes("OCR is not available"));
  assert(await rejected.text.isEnabled());
  assert.equal(sourcePosts.length, 1, "Rejected files must not create a source");
  report.checks.push("image-only PDF failure remains visible and does not trigger OCR or source creation");

  const textBytes = Buffer.from("The office must publish a synthetic inventory.\n", "utf8");
  await rejected.file.setInputFiles({ name: "public-policy.txt", mimeType: "text/plain", buffer: textBytes });
  await page.waitForFunction(expected => document.querySelector('textarea[name="text"]').value === expected &&
    !document.querySelector('textarea[name="text"]').disabled, textBytes.toString("utf8"));
  const original = await importCaptured(rejected);
  assert.equal(original.text_provenance, "original");
  assert.equal(original.original_sha256, digest(textBytes));
  assert.deepEqual(original.page_spans, []);
  assert.deepEqual(original.failed_pages, []);
  assert.equal(original.page_count, null);
  report.checks.push("UTF-8 text import retains the original byte hash without fabricated PDF pages");

  await Promise.all([
    page.waitForResponse(response => response.url().endsWith("/api/preferences") && response.request().method() === "PUT"),
    page.locator("#view-mode").selectOption("advanced"),
  ]);
  await page.getByRole("button", { name: "Home", exact: true }).click();
  await page.getByRole("button", { name: /Confirm an annual review schedule for the AI inventory/ }).click();
  await page.getByLabel("Authority relied on").waitFor();
  assert(!/\bundefined\b/.test(await page.locator("#main").innerText()), "Applicability form must not append literal undefined");
  assert.equal(await page.getByLabel("Confirm the searched sources are the complete in-scope set", { exact: true }).count(), 0,
    "A non-absence finding must not show an absence completeness confirmation");
  report.checks.push("non-absence applicability form has no spurious text or completeness confirmation");
  assert.deepEqual(report.javascript_errors, [], "Unexpected browser JavaScript exception");
} catch (error) {
  report.error = String(error);
  process.exitCode = 1;
} finally {
  await browser.close();
  await mkdir(dirname(values.output), { recursive: true });
  await writeFile(values.output, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
}
