/** Real synthetic-demo workflow regression; mutates a throwaway local database. */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { parseArgs } from "node:util";
import { chromium } from "playwright";

const { values } = parseArgs({ options: {
  url: { type: "string", default: "http://127.0.0.1:8770" },
  chromium: { type: "string" },
  output: { type: "string", default: "test-results/review-ui.json" },
} });
const url = new URL(values.url);
assert(["localhost", "127.0.0.1", "[::1]"].includes(url.hostname), "Use a local throwaway demo instance");
const report = { checks: [], javascript_errors: [], entities: {}, error: null };
const browser = await chromium.launch({ executablePath: values.chromium || process.env.COMPASS_CHROMIUM || undefined });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const health = await context.request.get(new URL("/api/health", url).href);
  assert(health.ok() && (await health.json()).mode === "synthetic_demo", "Refusing to write outside a throwaway synthetic demo");
  const page = await context.newPage();
  page.on("pageerror", error => report.javascript_errors.push(String(error)));
  const tag = `Browser workflow ${randomUUID().slice(0, 8)}`;
  async function read(path) {
    const response = await context.request.get(new URL(`/api${path}`, url).href);
    assert(response.ok(), `Read failed: ${path} (${response.status()})`);
    return response.json();
  }
  async function submit(button, path, method = "POST", status = 200) {
    report.pending_action = `${method} ${path}`;
    const invalid = await button.evaluate(button => Array.from(button.form?.elements || []).filter(input => input.willValidate && !input.validity.valid).map(input => ({ name: input.name, message: input.validationMessage })));
    assert.deepEqual(invalid, [], `UI form validation blocked ${method} ${path}: ${JSON.stringify(invalid)}`);
    const pending = page.waitForResponse(response => new URL(response.url()).pathname === `/api${path}` && response.request().method() === method);
    await button.click();
    const response = await pending;
    const result = await response.json();
    assert.equal(response.status(), status, `${method} ${path}: ${JSON.stringify(result)}`);
    report.pending_action = null;
    return result;
  }
  async function announced(message) {
    await page.waitForFunction(expected => document.getElementById("announcement").textContent.includes(expected) &&
      !Array.from(document.querySelectorAll("button")).some(button => button.textContent === "Saving…"), message);
  }
  function formWithButton(name) {
    return page.locator("form").filter({ has: page.getByRole("button", { name, exact: true }) });
  }
  async function assertNoSpuriousApplicability(isAbsence = false) {
    assert(!/\bundefined\b/.test(await page.locator("#main").innerText()), "A review form rendered literal undefined");
    assert.equal(await page.getByRole("checkbox", { name: /Confirm the searched sources are the complete in-scope set/ }).count(), isAbsence ? 1 : 0);
  }
  async function createReview(title, sources) {
    await page.getByRole("button", { name: "Reviews", exact: true }).click();
    await page.getByRole("button", { name: "＋ New review", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Review title").fill(title);
    await dialog.getByLabel("Review as-of date").fill("2026-11-06");
    for (const checkbox of await dialog.locator('input[name="source_ids"]').all()) await checkbox.uncheck();
    for (const source of sources) {
      const checkbox = dialog.locator(`input[name="source_ids"][value="${source.id}"]`);
      const label = checkbox.locator("..");
      assert((await label.innerText()).includes((source.hash || source.id).slice(0, 8)), "Pinned source choices must identify their exact revision");
      if (source.verification?.status === "verified") assert((await label.innerText()).includes("verified"));
      await checkbox.check();
    }
    await dialog.getByLabel("Coverage limitations").fill("Synthetic browser regression only. Coverage is limited to the deliberately selected fixture snapshots.");
    const created = await submit(dialog.getByRole("button", { name: "Create review", exact: true }), "/runs", "POST", 201);
    await dialog.waitFor({ state: "hidden" });
    await page.getByRole("heading", { name: title, exact: true }).waitFor();
    assert.deepEqual([...created.source_ids].sort(), sources.map(source => source.id).sort());
    return created;
  }
  async function createFinding(run, type, summary, passages = []) {
    await page.getByRole("button", { name: "＋ Add finding", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Evidence structure").selectOption(type);
    await dialog.getByLabel("Finding summary").fill(summary);
    await dialog.getByLabel("Category", { exact: true }).selectOption(type === "internal_conflict" ? "conflict" : "opportunity");
    await dialog.getByLabel("Issue severity").selectOption("high");
    await dialog.getByLabel("Analysis rationale").fill("Synthetic regression: record the actual passages or declared search and preserve uncertainty until a separate applicability review.");
    if (type === "absence") {
      assert.equal(await dialog.getByLabel("Exact passage").count(), 0, "An absence must not demand an invented quote");
      await dialog.getByLabel("Search description").fill("Searched the complete selected synthetic instrument for notice, resident appeal, contestability and review language. No such passage was found in this deliberately limited corpus.");
      await dialog.getByRole("checkbox", { name: new RegExp(`${tag} internal`) }).check();
    } else {
      assert.equal(passages.length, 2);
      for (const [index, passage] of passages.entries()) {
        await dialog.getByLabel("Passage source").nth(index).selectOption(passage.source.id);
        await dialog.getByLabel("Exact passage").nth(index).fill(passage.quote);
        await dialog.getByLabel("Passage location").nth(index).fill(passage.location);
      }
      await dialog.getByRole("checkbox", { name: /Potential concentrated harm/ }).check();
      await dialog.getByRole("checkbox", { name: /Potential irreversible harm/ }).check();
    }
    const created = await submit(dialog.getByRole("button", { name: "Record finding", exact: true }), `/runs/${run.id}/findings`, "POST", 201);
    await dialog.waitFor({ state: "hidden" });
    await page.getByRole("heading", { name: summary, exact: true }).waitFor();
    await assertNoSpuriousApplicability(type === "absence");
    assert.equal(created.finding_type, type);
    assert.equal(created.status, "pending");
    return created;
  }
  async function applicability(finding, determination, complete = false) {
    const form = formWithButton("Record applicability");
    await form.getByLabel("Determination", { exact: true }).selectOption(determination);
    await form.getByLabel("Applicability rationale").fill("Synthetic agency review confirms only the stated fixture scope, relevant dates and recorded supporting basis; this is not an assertion about real law.");
    await form.getByLabel("Authority relied on").fill("Synthetic fixture sections only; agency-appointed review of the declared exercise scope.");
    if (finding.finding_type === "absence") await form.getByRole("checkbox", { name: /Confirm the searched sources/ }).setChecked(complete);
    const result = await submit(form.getByRole("button", { name: "Record applicability", exact: true }), `/findings/${finding.id}/applicability`);
    await announced("Applicability recorded");
    return result;
  }
  async function accept(finding, status = 200) {
    const form = formWithButton("Record decision");
    await form.getByLabel("Outcome", { exact: true }).selectOption("accept");
    await form.getByLabel("Decision rationale").fill("Synthetic policy-owner decision on the preserved exercise evidence and separately recorded review.");
    const result = await submit(form.getByRole("button", { name: "Record decision", exact: true }), `/findings/${finding.id}/decisions`, "POST", status);
    if (status === 200) await announced("Decision recorded");
    return result;
  }

  await page.goto(url.href, { waitUntil: "networkidle" });
  // This separate synthetic office avoids the accessibility/import helpers'
  // Georgia Policy Office preference changes and requires no fabricated user.
  await page.getByRole("button", { name: /Casey Rivera/ }).click();
  await page.getByRole("button", { name: "Settings", exact: true }).waitFor();
  await Promise.all([
    page.waitForResponse(response => response.url().endsWith("/api/preferences") && response.request().method() === "PUT"),
    page.locator("#view-mode").selectOption("advanced"),
  ]);
  const internalText = "Section 1. The office reviews its inventory monthly.\nSection 2. The office reviews its inventory annually.\nSection 3. The office keeps a public inventory.";
  const externalText = "Section 10. The office shall review its inventory annually.\nSection 11. Research-only pilots are excluded.";
  async function setupSource(kind, text) {
    const response = await context.request.post(new URL("/api/sources", url).href, { data: {
      kind, title: `${tag} ${kind === "instrument" ? "internal" : "external"}`,
      jurisdiction_id: kind === "instrument" ? "US-GA" : "US-FED", version: "synthetic-1",
      text, authority_type: kind === "instrument" ? "internal_policy" : "statute", legal_status: "unknown",
      effective_from: "2026-01-01", source_key: `${tag}/${kind}`,
    } });
    assert(response.ok(), `Fixture setup failed: ${await response.text()}`);
    return response.json();
  }
  const internal = await setupSource("instrument", internalText);
  const original = await setupSource("external", externalText);
  report.entities.original_source = original.id;

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  let membership = page.locator("form").filter({ has: page.getByRole("checkbox", { name: /Casey Rivera/ }) });
  if (await membership.getByRole("checkbox").isChecked()) {
    await membership.getByRole("checkbox").uncheck();
    await submit(membership.getByRole("button", { name: "Save review permission", exact: true }), "/memberships/ga-peer-owner", "PATCH");
    await announced("Agency review permission saved");
    membership = page.locator("form").filter({ has: page.getByRole("checkbox", { name: /Casey Rivera/ }) });
  }
  await membership.getByRole("checkbox").check();
  await submit(membership.getByRole("button", { name: "Save review permission", exact: true }), "/memberships/ga-peer-owner", "PATCH");
  await announced("Agency review permission saved");
  assert.equal((await read("/session")).workspace.can_determine_applicability, true);
  report.checks.push("policy owner grants self review permission through Settings with an audited API action");

  await page.getByRole("button", { name: "Sources", exact: true }).click();
  const card = page.locator("article.source-card").filter({ has: page.getByRole("heading", { name: original.title, exact: true }) });
  await card.getByRole("button", { name: "Review source status", exact: true }).click();
  const reviewDialog = page.getByRole("dialog");
  await reviewDialog.getByLabel("Verification status").selectOption("verified");
  await reviewDialog.getByLabel("Primary source location").fill("Synthetic exercise source, sections 10–11; no real statute asserted.");
  await reviewDialog.getByLabel("Reviewed legal status").selectOption("in_force");
  await reviewDialog.getByLabel("Review rationale").fill("Checked the complete synthetic exercise text and its defined dates; scope and research-only exception remain attached.");
  const verified = await submit(reviewDialog.getByRole("button", { name: "Preserve reviewed revision", exact: true }), `/sources/${original.id}/review`, "PATCH", 201);
  await reviewDialog.waitFor({ state: "hidden" });
  assert.notEqual(verified.id, original.id);
  assert.equal(verified.verification.status, "verified");
  assert.equal(verified.verification.verified_by_id, "ga-peer-owner");
  assert.deepEqual(await read(`/sources/${original.id}`), original, "Verification must preserve the original source and hash");
  report.entities.verified_source = verified.id;
  report.checks.push("source review creates an attributed verified revision and preserves the unverified original bytes/hash");

  const externalRun = await createReview(`${tag} external-gap review`, [internal, verified]);
  report.entities.external_run = externalRun.id;
  const gap = await createFinding(externalRun, "external_gap", `${tag} external gap`, [
    { source: internal, quote: "The office reviews its inventory monthly.", location: "Section 1" },
    { source: verified, quote: "The office shall review its inventory annually.", location: "Section 10; exception in Section 11" },
  ]);
  assert.equal(gap.concentrated_harm, true);
  assert.equal(gap.irreversible, true);
  assert.equal(gap.severity, "high");
  await applicability(gap, "binding");
  await accept(gap);
  const acceptedGap = await read(`/findings/${gap.id}`);
  assert.equal(acceptedGap.status, "accepted");
  assert.equal(acceptedGap.applicability.determination, "binding");
  report.checks.push("UI pins the verified revision, records an external gap with optional harm flags, determines binding scope and accepts an owner decision");

  await page.getByRole("button", { name: "Reviews", exact: true }).click();
  await page.locator("article.run-card").filter({ has: page.getByRole("heading", { name: externalRun.title, exact: true }) }).getByRole("button", { name: "Open review →", exact: true }).click();
  const conflict = await createFinding(externalRun, "internal_conflict", `${tag} internal conflict`, [
    { source: internal, quote: "The office reviews its inventory monthly.", location: "Section 1" },
    { source: internal, quote: "The office reviews its inventory annually.", location: "Section 2" },
  ]);
  assert.equal(conflict.evidence.length, 2);
  assert(conflict.evidence.every(piece => piece.kind === "instrument"));
  await applicability(conflict, "persuasive");
  await accept(conflict);
  report.checks.push("internal-conflict UI records two actual instrument passages without inventing an external source");

  const absenceRun = await createReview(`${tag} internal-only review`, [internal]);
  const absence = await createFinding(absenceRun, "absence", `${tag} missing resident review mechanism`);
  assert.deepEqual(absence.evidence, []);
  assert.deepEqual(absence.search_source_ids, [internal.id]);
  await applicability(absence, "persuasive", false);
  const denied = await accept(absence, 409);
  assert(denied.detail.includes("complete in-scope search set"), "Absence acceptance must be refused specifically for unconfirmed search completeness");
  await page.getByRole("alert").filter({ hasText: "complete in-scope search set" }).waitFor();
  assert.equal((await read(`/findings/${absence.id}`)).status, "pending");
  report.checks.push("absence acceptance is refused with a visible 409 error while search completeness is unconfirmed");
  await applicability(absence, "persuasive", true);
  assert(await page.getByRole("checkbox", { name: /Confirm the searched sources/ }).isChecked(), "A saved completeness confirmation must remain checked after refresh");
  await accept(absence);
  const acceptedAbsence = await read(`/findings/${absence.id}`);
  assert.equal(acceptedAbsence.status, "accepted");
  assert.equal(acceptedAbsence.applicability.scope_complete, true);
  assert.equal(acceptedAbsence.applicability.completeness_confirmed_by, "ga-peer-owner");
  report.checks.push("an appointed reviewer's scoped search confirmation enables a separate owner acceptance without fabricated quotations");

  const bundle = await read(`/runs/${externalRun.id}/export`);
  assert.deepEqual(bundle.run.source_ids.sort(), [internal.id, verified.id].sort());
  assert.equal(bundle.sources.find(source => source.id === verified.id).hash, verified.hash);
  assert.equal(bundle.findings.find(finding => finding.id === gap.id).status, "accepted");
  const events = (await read("/audit")).events;
  assert(events.some(event => event.action === "membership.applicability_permission_changed" && event.entity_id === "ga-peer-owner" && event.details.current));
  assert(events.some(event => event.action === "source.reviewed" && event.entity_id === original.id && event.details.revised_source_id === verified.id));
  assert.equal((await read(`/sources/${original.id}`)).hash, original.hash);
  assert.deepEqual(report.javascript_errors, [], "Unexpected JavaScript exception in the review workflow");
  report.checks.push("exports retain pinned source hashes and decisions; permission and source review actions remain attributable in audit");
} catch (error) {
  report.error = String(error);
  process.exitCode = 1;
} finally {
  await browser.close();
  await mkdir(dirname(values.output), { recursive: true });
  await writeFile(values.output, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
}
