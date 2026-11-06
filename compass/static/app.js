"use strict";

const state = { session: null, data: null, view: "overview", run: null, finding: null, mode: "simple", settings: null, context: null, insights: null, workspaceInsights: null, analysisRunId: null, monitoring: null, activeFeature: "change_detection", checking: false, pollTimer: null, refreshSeq: 0 };
const main = document.getElementById("main");
const dialog = document.getElementById("form-dialog");
const dialogContent = document.getElementById("dialog-content");
const viewLabels = { overview: "Home", reviews: "Reviews", sources: "Sources", settings: "Settings", insights: "Insights", monitoring: "Monitoring", activity: "Activity", finding: "Review finding", run: "Review detail" };
const FEATURES = {
  change_detection: ["Changes", "Compare revisions of sources with stable identifiers."],
  obligations: ["Obligations", "Locate obligation language for a policy owner to review."],
  citations: ["References", "Check declared references against available source identifiers."],
  terminology: ["Terminology", "Surface definition and terminology issues in the supplied material."],
  coverage: ["Coverage", "Compare the topics supplied with your office's stated review scope."],
  impact: ["Impact", "Connect source changes with the assets and programs you identify."],
  language: ["Language", "Flag wording that may need a clearer policy expression."],
  deadlines: ["Dates", "Surface effective dates within the selected time horizon."],
  peer_research: ["Peer research", "Consider explicitly marked public reference material as optional ideas."]
};
const COMPLEX_FEATURES = new Set(["terminology", "impact", "language", "peer_research"]);
const lines = (value) => [...new Set(String(value || "").split(/\n/).map((item) => item.trim()).filter(Boolean))];
const advanced = () => state.mode === "advanced";
const words = (value) => String(value ?? "").replaceAll("_", " ");
const label = (value) => { const text = words(value); return text ? text[0].toUpperCase() + text.slice(1) : "—"; };
const date = (value) => {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const calendarDate = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const options = { month: "short", day: "numeric", year: "numeric", timeZone: calendarDate ? "UTC" : "America/New_York" };
  if (!calendarDate) Object.assign(options, { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  return new Intl.DateTimeFormat("en-US", options).format(parsed);
};
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "checked" || key === "disabled" || key === "required" || key === "hidden") node[key] = Boolean(value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) if (child !== null && child !== undefined && child !== false) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}
function button(text, onClick, style = "secondary", extra = {}) { return el("button", { type: "button", class: `button button-${style}`, onClick, ...extra }, text); }
function badge(value) { return el("span", { class: `badge ${String(value).replace(/[^a-z_]/g, "")}` }, label(value)); }
function announce(message = "", error = false) { const node = document.getElementById("announcement"); node.textContent = message; node.classList.toggle("error", error); }
function errorMessage(error) { return error?.message || "The request could not be completed. Please try again."; }
async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api${path}`, { credentials: "same-origin", ...options, headers, body: options.body === undefined ? undefined : JSON.stringify(options.body) });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const body = await response.json(); const detail = body.detail ?? body.error ?? body.message; if (typeof detail === "string") message = detail; else if (Array.isArray(detail)) message = detail.map((item) => `${item.loc?.filter((part) => part !== "body").join(" · ") || "Input"}: ${item.msg}`).join("\n"); } catch { /* Keep the HTTP status if no JSON error is available. */ }
    const error = new Error(message); error.status = response.status; throw error;
  }
  return response.status === 204 ? null : response.json();
}
function heading(eyebrow, title, subtitle, action) { return el("div", { class: "page-heading" }, el("div", {}, el("div", { class: "eyebrow" }, eyebrow), el("h1", {}, title), el("p", { class: "subtitle" }, subtitle)), action); }
function panel(title, body, subtitle = "", action = null) { return el("section", { class: "panel" }, el("div", { class: "panel-header" }, el("div", {}, el("h2", {}, title), subtitle ? el("p", { class: "helper" }, subtitle) : null), action), body); }
function empty(title, description) { return el("div", { class: "empty" }, el("strong", {}, title), description); }
function definitions(entries) { return el("dl", { class: "definition-list" }, entries.map(([key, value]) => el("div", {}, el("dt", {}, key), el("dd", {}, value)))); }
function isOwner() { return state.session?.workspace?.role === "owner"; }
function back(text, fn) { return button(`← ${text}`, fn, "quiet", { class: "button button-quiet back-button" }); }
function runTitle(id) { return state.data?.runs?.find((run) => run.id === id)?.title || "Review run"; }
function findings() { return state.data?.findings || []; }
function currentFinding() { return findings().find((finding) => finding.id === state.finding?.id) || state.finding; }
function findStatus(finding) { return finding.status || "pending"; }

async function refresh() {
  const sequence = ++state.refreshSeq;
  const workspaceId = state.session?.workspace?.id;
  const analysisRunId = state.analysisRunId;
  const [data, settings, context, officeInsights, monitoring, reviewInsights, run] = await Promise.all([api("/dashboard"), api("/settings"), api("/context"), api("/insights"), api("/monitoring"), analysisRunId ? api(`/insights?run_id=${encodeURIComponent(analysisRunId)}`) : null, state.run ? api(`/runs/${encodeURIComponent(state.run.id)}`) : null]);
  if (sequence !== state.refreshSeq || workspaceId !== state.session?.workspace?.id) return;
  Object.assign(state, { data, settings, context, workspaceInsights: officeInsights, monitoring });
  state.insights = reviewInsights && analysisRunId === state.analysisRunId ? reviewInsights : officeInsights;
  if (run && run.id === state.run?.id) state.run = run;
  render();
}
function navigate(view) { clearTimeout(state.pollTimer); state.pollTimer = null; if (view === "overview") { state.analysisRunId = null; state.insights = state.workspaceInsights; } state.view = view; announce(); render(); main.focus(); }
function renderNavigation() {
  const items = [["overview", "◫", "Home"], ["reviews", "▤", "Reviews"], ["sources", "▧", "Sources"], ...(advanced() ? [["insights", "◇", "Insights"], ["monitoring", "◉", "Monitoring"], ["activity", "◷", "Activity"]] : []), ["settings", "⚙", "Settings"]];
  document.getElementById("navigation").replaceChildren(...items.map(([view, icon, title]) => el("button", { class: "nav-item", "data-view": view, type: "button", disabled: !state.session }, el("span", { "aria-hidden": "true" }, icon), title)));
  document.getElementById("view-control").hidden = !state.session;
  document.getElementById("view-mode").value = state.mode;
}
function render() {
  renderNavigation();
  const active = state.view === "finding" || state.view === "run" ? "reviews" : state.view;
  document.querySelectorAll("[data-view]").forEach((node) => { const current = node.dataset.view === active; node.classList.toggle("active", current); if (current) node.setAttribute("aria-current", "page"); else node.removeAttribute("aria-current"); });
  document.getElementById("breadcrumb-label").textContent = viewLabels[state.view] || "Overview";
  document.title = `${viewLabels[state.view] || "Workspace"} · COMPASS`;
  if (!state.data) return;
  const renderers = { overview: advanced() ? overview : guidedHome, reviews, sources, settings: settingsView, insights: insightsView, monitoring: monitoringView, activity, finding: findingDetail, run: runDetail };
  main.replaceChildren((renderers[state.view] || overview)());
  scheduleMonitoringPoll();
}
function findingRow(finding) {
  return el("button", { type: "button", class: "finding-row", onClick: () => { state.finding = finding; navigate("finding"); } },
    el("span", { class: "row-meta" }, badge(finding.severity), badge(findStatus(finding)), el("span", { class: "helper" }, label(finding.category))),
    el("span", { class: "finding-title" }, finding.summary),
    el("span", { class: "finding-bottom" }, el("span", {}, runTitle(finding.run_id)), el("span", {}, finding.assignment?.assignee ? `Assigned to ${finding.assignment.assignee}${finding.assignment.due_date ? ` · Due ${date(finding.assignment.due_date)}` : ""}` : `Applicability: ${words(finding.applicability?.determination || "unknown")}`)));
}
function coverageNote() { return el("div", { class: "coverage-note" }, el("strong", {}, "Coverage has not been verified"), el("p", {}, state.data.coverage?.message || "The external policy database is not connected. This workspace uses synthetic examples and manually supplied snapshots.")); }
function overview() {
  const data = state.data; const counts = data.counts || {};
  const stats = [["Pending decisions", counts.pending ?? 0, "Awaiting policy-owner review", "◷"], ["Source snapshots", counts.sources ?? data.sources?.length ?? 0, "Versioned evidence, preserved", "▧"], ["Review runs", counts.runs ?? data.runs?.length ?? 0, "Pinned inputs and profile", "▤"], ["Accepted findings", counts.accepted ?? 0, "Attributed owner decisions", "✓"]];
  const pending = findings().filter((finding) => ["pending", "needs_information"].includes(findStatus(finding)));
  const list = pending.length ? pending.slice(0, 8).map(findingRow) : empty("Your review queue is clear", "Create a review with source snapshots to record evidence-linked findings.");
  return el("div", {}, heading("Your policy review workspace", "A clearer path to confident decisions.", "Inspect local rule checks, review the evidence, and preserve accountable decisions.", el("div", { class: "action-group" }, checkButton(), button("＋ New review", newRun, "secondary"))),
    el("div", { class: "stats" }, stats.map(([title, value, description, icon]) => el("article", { class: "stat" }, el("span", { class: "stat-marker", "aria-hidden": "true" }, icon), el("span", { class: "stat-label" }, title), el("div", { class: "stat-value" }, value), el("div", { class: "stat-description" }, description)))),
    el("div", { class: "two-column" }, panel("Your review queue", el("div", {}, list), "Evidence-linked findings that need a closer look.", button("View reviews →", () => navigate("reviews"), "quiet", { class: "button button-quiet small" })),
      el("div", { class: "stack" }, panel("Workspace context", el("div", { class: "panel-body" }, definitions([["Office", data.workspace?.name || state.session.workspace.name], ["Jurisdiction", data.profile?.name || data.workspace?.jurisdiction_id], ["Profile", `v${data.profile?.version || "—"}`], ["Your role", label(state.session.workspace.role)], ["Analysis method", "Manual, evidence-led"]]), el("div", { class: "section-gap" }, coverageNote()))),
        panel("From evidence to decision", el("div", { class: "panel-body" }, el("ol", { class: "numbered-steps" }, el("li", {}, el("strong", {}, "Preserve the source"), "Import an immutable instrument or external record."), el("li", {}, el("strong", {}, "Connect the evidence"), "Record a finding with exact supporting excerpts."), el("li", {}, el("strong", {}, "Review and decide"), "A policy owner confirms applicability and records the outcome.")))))));
}
function reviews() {
  const runs = state.data.runs || [];
  return el("div", {}, heading("Reviews", "Deliberate review. Traceable results.", "Each run preserves its source snapshots, jurisdiction profile, and review date.", button("＋ New review", newRun, "primary")),
    coverageNote(), el("div", { class: "run-list section-gap" }, runs.length ? runs.map((run) => el("article", { class: "panel run-card" }, el("div", { class: "row-meta" }, badge(run.analysis_method || "manual"), el("span", { class: "helper" }, `As of ${date(run.as_of)}`)), el("h3", {}, run.title), el("p", {}, run.coverage_note || "Coverage is unverified. Review only the sources pinned to this run."), el("div", { class: "helper" }, `${run.source_ids?.length ?? run.sources?.length ?? "—"} source snapshots · Created ${date(run.created_at)}`), el("div", { class: "run-actions" }, button("Open review →", () => openRun(run.id), "secondary"), button(advanced() ? "Export evidence" : "Export brief", () => advanced() ? exportRun(run.id) : exportBrief(run.id), "quiet")))) : el("div", { class: "panel" }, empty("No reviews yet", "Import at least one internal instrument and one external source, then create a review."))));
}
async function openRun(id) { const workspaceId = state.session?.workspace?.id; try { const [run, insights] = await Promise.all([api(`/runs/${encodeURIComponent(id)}`), api(`/insights?run_id=${encodeURIComponent(id)}`)]); if (workspaceId !== state.session?.workspace?.id) return; state.run = run; state.analysisRunId = id; state.insights = insights; navigate("run"); } catch (error) { announce(errorMessage(error), true); } }
function runDetail() {
  const run = state.run;
  if (!run) return reviews();
  const items = run.findings || findings().filter((finding) => finding.run_id === run.id);
  const runSources = run.sources || (state.data.sources || []).filter((source) => run.source_ids?.includes(source.id));
  const reviewRecord = panel("Review record", el("div", { class: "panel-body" },
    definitions([["Review date", date(run.as_of)], ["Preserved sources", runSources.length], ...(advanced() ? [["Analysis method", run.analysis_method || "manual"], ["Profile hash", el("span", { class: "hash" }, (run.profile_hash || "").slice(0, 16) + "…")]] : [])]),
    el("p", { class: "helper section-gap" }, run.coverage_note || "Coverage has not been verified."),
    el("div", { class: "action-group" }, button("↓ Export brief", () => exportBrief(run.id), "secondary"), advanced() ? button("Full evidence JSON", () => exportRun(run.id), "quiet") : null)));
  const pinnedSources = panel("Preserved sources", el("div", { class: "panel-body" }, runSources.map((source) => el("div", { class: "source-ref" }, badge(source.kind), el("p", { class: "helper" }, source.title), el("span", { class: advanced() ? "hash" : "helper" }, advanced() ? `v${source.version} · ${(source.hash || "").slice(0, 12)}…` : `Version ${source.version}`)))));
  return el("div", {}, back("All reviews", () => navigate("reviews")),
    heading("Review", run.title, `Review date: ${date(run.as_of)} · Sources are preserved as they were when this review began.`, el("div", { class: "action-group" }, analyzeButton(run.id), button("＋ Add finding", () => newFinding(run), "secondary"))),
    el("div", { class: "two-column" },
      panel("Findings", el("div", {}, items.length ? items.map(findingRow) : empty("Ready for your first finding", "Compare the pinned sources and add a finding with exact excerpts. This foundation does not generate findings automatically."))),
      el("div", { class: "stack" }, reviewRecord, pinnedSources)), state.insights?.latest?.run_id === run.id ? el("div", { class: "section-gap" }, reviewResults(state.insights.latest)) : null);
}
function findingDetail() {
  const finding = currentFinding();
  if (!finding) return reviews();
  const applicability = finding.applicability || { determination: "unknown" };
  const originalEvidence = el("div", {}, (finding.evidence || []).map((evidence) => el("article", { class: "evidence-card" }, badge(evidence.kind), el("h3", {}, evidence.title || "Source snapshot"), el("blockquote", {}, evidence.quote), el("div", { class: "evidence-location" }, `Location: ${evidence.location || "Not supplied"}`))));
  const evidencePanel = advanced() ? originalEvidence : el("details", { class: "progressive-evidence" }, el("summary", {}, "Read the original evidence"), originalEvidence);
  return el("div", {}, back("Review queue", () => navigate("overview")), el("div", { class: "page-heading" }, el("div", {}, el("div", { class: "row-meta" }, badge(finding.severity), badge(findStatus(finding)), badge(finding.category)), el("h1", { class: "detail-title" }, finding.summary), el("p", { class: "subtitle" }, runTitle(finding.run_id))), button(advanced() ? "Export review evidence" : "Export review brief", () => advanced() ? exportRun(finding.run_id) : exportBrief(finding.run_id), "secondary")),
    el("div", { class: "two-column" }, el("div", { class: "stack single-column" }, panel("Why this needs review", el("div", { class: "panel-body" }, el("p", { class: "prose" }, finding.rationale))), panel("Supporting evidence", el("div", { class: "panel-body" }, evidencePanel)), panel("Assignment and follow-up", el("div", { class: "panel-body" }, assignmentForm(finding)))),
      el("div", { class: "stack single-column" }, panel("Applicability", el("div", { class: "panel-body" }, el("div", { class: "row-meta" }, badge(applicability.determination)), el("p", { class: "form-note" }, "Legal applicability is reviewed separately from severity. A score cannot create an obligation."), applicability.rationale ? el("p", { class: "prose" }, applicability.rationale) : null, applicability.reviewed_at ? el("p", { class: "helper" }, `Reviewed ${date(applicability.reviewed_at)}`) : null, isOwner() ? applicabilityForm(finding) : el("div", { class: "notice" }, "A policy owner must confirm applicability."))),
        panel("Policy-owner decision", el("div", { class: "panel-body" }, isOwner() ? decisionForm(finding) : el("div", { class: "notice" }, "You can review and add findings. Acceptance and rejection require a policy-owner account."), el("p", { class: "helper section-gap" }, "Decisions preserve the person, outcome, rationale, and time in the review trail."))))));
}
function applicabilityForm(finding) {
  const form = el("form", { class: "inline-form section-gap" });
  const determination = field("select", "determination", "Determination", { options: [["unknown", "Unknown / needs review"], ["binding", "Binding within reviewed scope"], ["conditional", "Conditional"], ["persuasive", "Persuasive / nonbinding"], ["not_applicable", "Not applicable"]], value: finding.applicability?.determination || "unknown" });
  const rationale = field("textarea", "rationale", "Applicability rationale", { required: true, minLength: 10, placeholder: "Explain scope, conditions, dates, and the supporting authority." });
  form.append(determination.node, rationale.node); bindForm(form, async (values) => { await api(`/findings/${encodeURIComponent(finding.id)}/applicability`, { method: "POST", body: values }); await refresh(); announce("Applicability recorded with policy-owner attribution."); }, "Record applicability");
  return form;
}
function decisionForm(finding) {
  const form = el("form", { class: "inline-form" });
  const outcome = field("select", "outcome", "Outcome", { options: [["needs_information", "Request more information"], ["accept", "Accept finding"], ["reject", "Reject finding"]] });
  const rationale = field("textarea", "rationale", "Decision rationale", { required: true, minLength: 10, placeholder: "Explain the decision and any follow-up needed." });
  if (finding.decision && finding.status !== "pending") form.append(el("div", { class: "notice" }, el("strong", {}, `Recorded outcome: ${label(finding.decision.outcome)}`), el("p", { class: "prose" }, finding.decision.rationale), el("div", { class: "helper" }, `${finding.decision.decided_by} · ${date(finding.decision.decided_at)}`)));
  form.append(el("p", { class: "form-note" }, finding.applicability?.determination === "unknown" ? "Confirm applicability before accepting this finding. You can request more information while it is unresolved." : "Record an explicit policy-owner decision on this evidence."), outcome.node, rationale.node);
  bindForm(form, async (values) => { await api(`/findings/${encodeURIComponent(finding.id)}/decisions`, { method: "POST", body: values }); await refresh(); announce("Decision recorded. The review trail has been updated."); }, "Record decision");
  return form;
}
function sources() {
  const items = state.data.sources || [];
  return el("div", {}, heading("Source library", "Start with the source.", "Immutable snapshots keep the original text, provenance, dates, and version attached to your review.", button("＋ Import source", newSource, "primary")), coverageNote(),
    el("div", { class: "source-grid section-gap" }, items.length ? items.map((source) => el("article", { class: "panel source-card" }, el("div", { class: "row-meta" }, badge(source.kind), badge(source.legal_status)), el("h2", {}, source.title), definitions([["Jurisdiction", source.jurisdiction_id], ["Version", source.version], ...(advanced() ? [["Stable source key", source.source_key || "Not supplied"], ["Authority type", label(source.authority_type)], ["Reference access", label(source.reference_scope || "private")], ["Topic tags", (source.topics || []).join(", ") || "Not supplied"]] : []), ["Effective from", date(source.effective_from)], ["Effective to", date(source.effective_to)]]), advanced() ? el("p", { class: "helper hash" }, `SHA-256 · ${source.hash || "—"}`) : null, safeSourceLink(source.source_url), el("details", {}, el("summary", {}, "Read preserved text"), el("pre", { class: "source-text", tabindex: "0" }, source.text)))) : el("div", { class: "panel" }, empty("Build your evidence library", "Import a text file or paste source text to begin. PDF, DOCX, and live-source connectors are not connected."))));
}
function safeSourceLink(url) { if (!url) return null; try { const parsed = new URL(url); if (!["https:", "http:"].includes(parsed.protocol)) return null; return el("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: "helper" }, "View source provenance ↗"); } catch { return null; } }
function activity() {
  const items = state.data.audit || [];
  return el("div", {}, heading("Activity", "Every decision leaves a trail.", "Workspace-scoped events attribute source imports, review creation, and policy-owner actions."), panel("Review trail", items.length ? el("ol", { class: "activity-list" }, items.map((event) => el("li", {}, el("span", { class: "activity-dot", "aria-hidden": "true" }), el("div", { class: "activity-description" }, label(event.action).replaceAll(".", " · "), el("small", {}, `${event.actor_name || "Workspace member"} · ${label(event.entity_type)}`)), el("time", { class: "activity-time", datetime: event.created_at || "" }, date(event.created_at))))) : empty("No events yet", "Actions in this workspace will appear here.")));
}

function checkButton() { return button(state.checking ? "Checking…" : "Check now", checkNow, "primary", { disabled: state.checking }); }
function analyzeButton(id) { return button(state.checking ? "Checking…" : "Analyze sources", () => analyzeRun(id), "primary", { disabled: state.checking }); }
async function checkNow() {
  if (state.checking) return;
  state.analysisRunId = null;
  state.insights = state.workspaceInsights;
  state.checking = true; render(); announce("Checking the latest source versions already in this workspace…");
  try {
    const result = await api("/monitoring/check", { method: "POST", body: {} });
    await refresh();
    if (result.job?.state === "failed") throw new Error(result.job.last_error || "The local check failed. Inspect the job in Monitoring before retrying.");
    if (result.job && result.job.state !== "succeeded") announce("Local check queued. Its status is available in Advanced Monitoring.");
    else announce("Local check completed. Review the results and their supporting evidence; applicability still needs policy-owner judgment.");
  } catch (error) { announce(error.status === 409 ? `${errorMessage(error)} Add an internal policy and an external reference in Sources if either is missing.` : errorMessage(error), true); }
  finally { state.checking = false; render(); }
}
async function analyzeRun(id) {
  if (state.checking) return;
  state.analysisRunId = id; state.checking = true; render();
  try {
    await api(`/runs/${encodeURIComponent(id)}/analyze`, { method: "POST", body: {} });
    state.view = advanced() ? "insights" : "run";
    await refresh(); announce("Local analysis saved against this review's preserved sources and settings.");
  } catch (error) { announce(errorMessage(error), true); }
  finally { state.checking = false; render(); }
}
function guidedHome() {
  const report = state.workspaceInsights?.latest;
  const notices = state.monitoring?.notices || [];
  const pending = findings().filter((finding) => ["pending", "needs_information"].includes(findStatus(finding)));
  const due = findings().filter((finding) => finding.assignment?.due_date && !["accepted", "rejected"].includes(findStatus(finding))).sort((a, b) => a.assignment.due_date.localeCompare(b.assignment.due_date));
  const deadlines = (report?.features?.deadlines?.items || []).filter((item) => item.data?.kind === "source_date" && item.data?.date >= today());
  const hasPolicies = (state.data.sources || []).some((source) => source.kind === "instrument");
  const steps = [
    ["1", "Provide your policies", hasPolicies ? "Your office's source documents are ready to review. Add a new version when a policy changes." : "Add your office's policies and the external material you want to check them against.", button(hasPolicies ? "Manage sources" : "Add policies", () => hasPolicies ? navigate("sources") : newSource(), "secondary")],
    ["2", "Check your sources", "Run the checks enabled for your office. These inspect local records; the external database is not connected.", checkButton()],
    ["3", "Review what needs attention", "Read the evidence, resolve questions, and record a policy-owner decision.", button("Review findings", () => navigate("reviews"), "secondary")]
  ];
  return el("div", {}, heading("Your office, at a glance", "Know what needs your attention.", "A guided path from your policies to an informed decision. Advanced detail is available whenever you need it."),
    el("div", { class: "guided-steps" }, steps.map(([number, title, description, action]) => el("article", { class: "panel guided-step" }, el("span", { class: "step-number", "aria-hidden": "true" }, number), el("h2", {}, title), el("p", {}, description), action))),
    el("div", { class: "simple-summary" }, el("p", {}, el("strong", {}, "Last successful check: "), state.monitoring?.last_successful_check ? date(state.monitoring.last_successful_check) : "No successful local check yet"), el("p", {}, el("strong", {}, "Review cues: "), report?.summary?.attention_count ?? "Not checked yet"), el("p", {}, el("strong", {}, "Analysis: "), state.settings?.advanced_analysis ? "Workspace checks enabled" : "Complex checks are switched off"), button("Change analysis settings", () => navigate("settings"), "quiet")),
    report && state.workspaceInsights?.stale ? el("div", { class: "coverage-note section-gap" }, el("strong", {}, "The saved results may be out of date"), "Sources, context, or settings have changed since the last check. Check again to update the results.") : null,
    el("div", { class: "two-column section-gap" }, el("div", { class: "stack single-column" }, panel("Your decision queue", el("div", {}, pending.length ? pending.slice(0, 8).map(findingRow) : empty("No findings awaiting a decision", "Local check results appear below. You can turn an issue into a finding after reviewing its evidence."))), report ? reviewResults(report) : panel("Check results", empty("Ready when you are", "Add the relevant sources and choose Check now. Results remain advisory until a policy owner reviews them."))),
      el("div", { class: "stack single-column" }, panel("Inbox", noticeList(notices.slice(0, 5))), panel("Upcoming and assigned", el("div", { class: "panel-body" }, due.length || deadlines.length ? [...due.slice(0, 5).map((finding) => el("div", { class: "upcoming-item" }, el("strong", {}, date(finding.assignment.due_date)), el("p", {}, finding.summary), el("span", { class: "helper" }, `Assigned to ${finding.assignment.assignee || "Unassigned"}`))), ...deadlines.slice(0, 5).map((item) => el("div", { class: "upcoming-item" }, el("strong", {}, item.title), el("p", {}, item.detail)))] : el("p", { class: "helper" }, "No dates or assignments to show. Add source dates and assign follow-up work when needed."))), panel("What is connected", el("div", { class: "panel-body" }, el("p", { class: "helper" }, "Local source checks are available. The external database and language model are not connected. Notifications stay in this workspace; email is unavailable."), coverageNote())))));
}
function analysisItem(item, feature) {
  const evidence = item.evidence || [];
  const detail = el("div", { class: "analysis-item-body" }, el("p", { class: "prose" }, item.detail), evidence.length ? el("details", { class: "progressive-evidence" }, el("summary", {}, "Read supporting source text"), evidence.map((quote) => el("blockquote", {}, quote.quote, el("cite", {}, quote.location || "Source excerpt")))) : el("p", { class: "helper" }, "This check identifies a data or review need; no supporting quotation was returned."), advanced() && item.data && Object.keys(item.data).length ? el("details", { class: "technical-details" }, el("summary", {}, "Check metadata"), el("pre", { class: "source-text" }, JSON.stringify(item.data, null, 2))) : null);
  return el("details", { class: "analysis-item" }, el("summary", {}, el("span", { class: "analysis-item-title" }, item.title), el("span", { class: "row-meta" }, badge(item.severity || "info"), feature ? el("span", { class: "helper" }, FEATURES[feature]?.[0] || label(feature)) : null)), detail);
}
function reviewResults(report) {
  const candidates = Object.entries(report.features || {}).flatMap(([key, feature]) => feature.enabled ? (feature.items || []).map((item) => ({ item, feature: key })) : []);
  const rank = { urgent: 0, review: 1, info: 2 };
  candidates.sort((a, b) => (rank[a.item.severity] ?? 2) - (rank[b.item.severity] ?? 2));
  return panel("What the checks found", el("div", {}, el("div", { class: "panel-body results-intro" }, el("p", { class: "helper" }, `Checked ${date(report.created_at)}. Local rules surface review cues; they do not decide legal applicability.`), ...(report.warnings || []).map((warning) => el("p", { class: "helper warning-text" }, warning))), candidates.length ? candidates.slice(0, 12).map(({ item, feature }) => analysisItem(item, feature)) : empty("No review cues returned", "This does not establish compliance or complete coverage. Check the selected sources and workspace settings."), candidates.length > 12 ? el("p", { class: "helper panel-body" }, `${candidates.length - 12} additional items are available in the Advanced Insights view.`) : null, report.run_id ? el("div", { class: "panel-body" }, button("Open this review →", () => openRun(report.run_id), "secondary")) : null));
}
function noticeList(notices) {
  return notices.length ? el("div", { class: "notice-list" }, notices.map((notice) => el("article", { class: `inbox-item ${notice.read_at ? "is-read" : ""}` }, el("div", { class: "row-meta" }, badge(notice.kind || "notice"), !notice.read_at ? el("span", { class: "helper" }, "Unread") : null), el("h3", {}, notice.title), el("p", {}, notice.body || notice.message || ""), notice.stale ? el("p", { class: "warning-text" }, "Newer changes have not been checked. Run a fresh check before relying on this summary.") : null, el("div", { class: "helper" }, date(notice.created_at)), !notice.read_at ? button("Mark read", async () => { try { await api(`/notices/${encodeURIComponent(notice.id)}/read`, { method: "POST", body: {} }); await refresh(); announce("Notification marked as read."); } catch (error) { announce(errorMessage(error), true); } }, "quiet", { class: "button button-quiet small" }) : null))) : empty("You're up to date", "Check results and local monitoring notices will appear here. No email is sent.");
}
function insightsView() {
  const report = state.insights?.latest;
  const workload = state.insights?.workload || {};
  const scope = el("div", { class: "notice analysis-scope" }, el("span", {}, el("strong", {}, state.analysisRunId ? "Scope: this review. " : "Scope: office-wide results. "), state.analysisRunId ? state.insights.review_title || runTitle(state.analysisRunId) : "Latest saved check of the office's current source selection."), state.analysisRunId ? button("Office-wide results", officeWideResults, "quiet") : null);
  if (!report) return el("div", {}, heading("Insights", "Inspect the analysis behind your review.", "Nine focused checks, with preserved evidence and execution settings.", checkButton()), scope, panel("No analysis saved", empty(state.analysisRunId ? "This review has not been analyzed" : "Start with a local check", state.analysisRunId ? "Open this review and choose Analyze sources to inspect its preserved inputs." : "Import the required sources, enable the checks you need in Settings, and choose Check now.")));
  const current = report.features?.[state.activeFeature] || { enabled: false, status: "disabled", items: [], summary: "No result for this feature in the saved report." };
  return el("div", {}, heading("Insights", "Inspect the analysis behind your review.", `Saved ${date(report.created_at)} · As of ${date(report.as_of)} · ${report.method || "Local rules"}`, checkButton()),
    scope, state.insights.stale ? el("div", { class: "coverage-note" }, el("strong", {}, "Saved analysis is stale"), state.analysisRunId ? "Analyze this review again to use current settings and context with its preserved sources." : "Run another check to include changes to sources, context, or settings.") : null,
    el("div", { class: "simple-summary" }, el("p", {}, el("strong", {}, "Review cues: "), report.summary?.attention_count ?? "—"), el("p", {}, el("strong", {}, "Recorded decisions: "), workload.decision_count ?? 0), el("p", {}, el("strong", {}, "Median review time: "), workload.median_review_hours == null ? "Not enough data" : `${workload.median_review_hours} hours`)),
    el("div", { class: "feature-tabs", role: "group", "aria-label": "Analysis sections" }, Object.entries(FEATURES).map(([key, [title]]) => button(title, () => { state.activeFeature = key; render(); }, "secondary", { class: `feature-tab ${state.activeFeature === key ? "active" : ""}`, "aria-pressed": state.activeFeature === key ? "true" : "false" }))),
    panel(FEATURES[state.activeFeature][0], el("div", {}, el("div", { class: "panel-body" }, el("div", { class: "row-meta" }, badge(current.status), badge(current.enabled ? "enabled" : "disabled")), el("p", { class: "prose" }, current.summary || FEATURES[state.activeFeature][1])), (current.items || []).map((item) => analysisItem(item)), !(current.items || []).length ? empty(current.enabled ? "No items returned" : "This check was not run", current.status === "needs_input" ? "Add the missing inputs described above and run another check." : "Check the saved settings and available source coverage before drawing a conclusion.") : null)),
    el("details", { class: "panel snapshot-details section-gap" }, el("summary", {}, "Saved settings and context for this analysis"), el("p", { class: "helper" }, "These are the inputs used for the saved result, even if current workspace settings have since changed."), el("pre", { class: "source-text" }, JSON.stringify({ settings: report.settings_snapshot, context: report.context_snapshot }, null, 2))),
    el("div", { class: "notice section-gap" }, "The external database and language model are not connected. Coverage remains unverified. No compliance percentage or model confidence is inferred."));
}
async function officeWideResults() { state.analysisRunId = null; state.insights = state.workspaceInsights; state.view = "insights"; try { await refresh(); announce("Showing office-wide results. No new analysis was started."); } catch (error) { announce(errorMessage(error), true); } }
function monitoringView() {
  const monitoring = state.monitoring || {};
  const controls = monitoring.settings?.monitoring || monitoring.settings || {};
  const jobs = monitoring.jobs || [];
  const table = el("div", { class: "table-scroll" }, el("table", { class: "data-table" }, el("caption", {}, "Local check history"), el("thead", {}, el("tr", {}, ["Trigger", "State", "Attempts", "Updated", "Action"].map((title) => el("th", { scope: "col" }, title)))), el("tbody", {}, jobs.map((job) => el("tr", {}, el("td", {}, label(job.trigger), job.last_error ? el("p", { class: "table-error" }, job.last_error) : null), el("td", {}, badge(job.state)), el("td", {}, `${job.attempts} / ${job.max_attempts ?? 3}`), el("td", {}, date(job.updated_at || job.created_at)), el("td", {}, job.state === "failed" && isOwner() ? retryJobButton(job) : job.run_id ? button("Open review", () => openRun(job.run_id), "quiet", { class: "button button-quiet small" }) : "—"))))));
  return el("div", {}, heading("Monitoring", "Track checks and follow up.", "Local jobs and in-app notifications for sources already in your workspace.", checkButton()),
    el("div", { class: "simple-summary" }, el("p", {}, el("strong", {}, "Last successful check: "), monitoring.last_successful_check ? date(monitoring.last_successful_check) : "Not yet"), el("p", {}, el("strong", {}, "Scheduled local checks: "), controls.enabled ? "Enabled" : "Off"), button("Monitoring settings", () => navigate("settings"), "quiet")),
    el("div", { class: "coverage-note" }, el("strong", {}, "Local monitoring only"), "The external database and email delivery are not connected. Notifications remain in this workspace; changes on external websites are not being watched."),
    el("div", { class: "section-gap" }, panel("Check jobs", jobs.length ? table : empty("No jobs yet", "Choose Check now to inspect the latest source versions in this workspace."))), el("div", { class: "section-gap" }, panel("Notifications", noticeList(monitoring.notices || []))));
}
function retryJobButton(job) {
  if (job.attempts >= (job.max_attempts ?? 3)) return button("Restart check", () => {
    const form = el("form");
    form.append(field("textarea", "rationale", "Describe the issue resolved before retrying", { required: true, minLength: 5, maxLength: 2000, help: "The restart is attributed to you. Previous attempts and their audit history are retained." }).node);
    bindForm(form, async (values) => { await api(`/jobs/${encodeURIComponent(job.id)}/retry`, { method: "POST", body: { reset: true, rationale: values.rationale } }); await refresh(); announce("Check restarted with your rationale recorded."); }, "Restart check", { dialogForm: true });
    showDialog("Restart a failed check", "The automatic retry limit has been reached. Explain what has changed before starting another bounded attempt cycle.", form);
  }, "secondary", { class: "button button-secondary small" });
  return button("Retry", async () => { try { await api(`/jobs/${encodeURIComponent(job.id)}/retry`, { method: "POST", body: {} }); await refresh(); announce("Retry requested."); } catch (error) { announce(errorMessage(error), true); } }, "secondary", { class: "button button-secondary small" });
}
function scheduleMonitoringPoll() {
  clearTimeout(state.pollTimer); state.pollTimer = null;
  if (state.view !== "monitoring" || !(state.monitoring?.jobs || []).some((job) => ["queued", "running"].includes(job.state))) return;
  state.pollTimer = setTimeout(async () => { if (state.view !== "monitoring") return; try { state.monitoring = await api("/monitoring"); if (state.view === "monitoring") render(); } catch (error) { announce(errorMessage(error), true); } }, 5000);
}
function assignmentForm(finding) {
  const assignment = finding.assignment || {};
  if (!isOwner()) return definitions([["Assigned to", assignment.assignee || "Unassigned"], ["Due", date(assignment.due_date)]]);
  const form = el("form", { class: "inline-form" });
  form.append(field("text", "assignee", "Assigned to", { required: true, maxLength: 200, value: assignment.assignee || "", placeholder: "Person or team responsible" }).node, field("date", "due_date", "Follow-up due date", { value: assignment.due_date || "" }).node);
  bindForm(form, async (values) => { await api(`/findings/${encodeURIComponent(finding.id)}/assignment`, { method: "PUT", body: { assignee: values.assignee, due_date: values.due_date || null } }); await refresh(); announce("Assignment and follow-up date saved."); }, "Save assignment");
  return form;
}
function toggle(name, title, description, checked, disabled = false) {
  const input = el("input", { type: "checkbox", name, checked, disabled });
  return { input, node: el("label", { class: "toggle-line" }, el("span", {}, el("strong", {}, title), el("small", {}, description)), input) };
}
function settingsView() {
  const settings = state.settings;
  if (!settings) return empty("Settings unavailable", "Reload the workspace to try again.");
  return el("div", {}, heading("Settings", "Keep the workflow simple. Choose the depth.", "Your view changes what you see. Workspace settings change which checks actually run."),
    el("div", { class: "notice" }, el("strong", {}, `Your personal view is ${label(state.mode)}. `), "Use the Simple / Advanced control at the top of the page. It is saved for your account and does not change analysis for other people."),
    el("div", { class: "settings-layout" }, panel("Workspace analysis", workspaceSettingsForm(settings), "These settings apply to future checks for this office."), panel("Target your review", contextForm(), "Tell COMPASS which topics, programs, and assets matter to your office.")));
}
function workspaceSettingsForm(settings) {
  const form = el("form", { class: "panel-body" });
  const group = el("fieldset", { class: "plain-fieldset", disabled: !isOwner() });
  const master = toggle("advanced_analysis", "Enable complex analysis", "Switch terminology, impact, language, and peer research checks together. Other selected checks continue. Existing results and decisions are retained.", settings.advanced_analysis);
  const featureInputs = {};
  const featureNodes = Object.entries(FEATURES).map(([key, [title, description]]) => { const control = toggle(key, title, description, settings.features?.[key], !settings.advanced_analysis && COMPLEX_FEATURES.has(key)); featureInputs[key] = control.input; return control.node; });
  master.input.addEventListener("change", () => Object.entries(featureInputs).forEach(([key, input]) => { input.disabled = !master.input.checked && COMPLEX_FEATURES.has(key); }));
  const horizon = field("number", "horizon_days", "Upcoming-date horizon (days)", { required: true, value: settings.horizon_days, min: 1, max: 365 });
  const monitoring = settings.monitoring || {};
  const monitorEnabled = toggle("monitoring_enabled", "Enable scheduled local checks", "Use local source, context, and effective-date triggers while the service is running. No external feed or email is connected.", monitoring.enabled);
  const sourceChanges = toggle("source_changes", "Source changes", "Check when a new version of a workspace source is imported.", monitoring.source_changes);
  const contextChanges = toggle("context_changes", "Context changes", "Check when review scope or asset information changes.", monitoring.context_changes);
  const effectiveDates = toggle("effective_dates", "Effective dates", "Check for date transitions in the sources you supplied.", monitoring.effective_dates);
  const interval = field("number", "check_interval_hours", "Check interval (hours)", { required: true, value: monitoring.check_interval_hours || 24, min: 1, max: 168 });
  const digest = field("number", "digest_interval_days", "In-app digest interval (days)", { required: true, value: monitoring.digest_interval_days || 7, min: 1, max: 30 });
  const timezone = field("text", "timezone", "Monitoring timezone", { required: true, value: monitoring.timezone || "America/New_York", help: "IANA timezone, such as America/New_York. Dates remain calendar dates; event times show Eastern time in this interface." });
  group.append(master.node, el("details", { class: "settings-details", open: advanced() ? "" : null }, el("summary", {}, "Choose individual checks"), featureNodes), horizon.node, el("div", { class: "notice" }, "Language-model analysis is unavailable. Enabled checks use local rules and explicit source metadata; they do not resolve legal applicability."), el("h3", { class: "section-gap" }, "Local monitoring"), monitorEnabled.node, sourceChanges.node, contextChanges.node, effectiveDates.node, el("div", { class: "field-grid" }, interval.node, digest.node), timezone.node);
  form.append(group);
  if (isOwner()) bindForm(form, async () => {
    const payload = { advanced_analysis: master.input.checked, features: Object.fromEntries(Object.entries(featureInputs).map(([key, input]) => [key, input.checked])), horizon_days: Number(horizon.input.value), monitoring: { enabled: monitorEnabled.input.checked, source_changes: sourceChanges.input.checked, context_changes: contextChanges.input.checked, effective_dates: effectiveDates.input.checked, check_interval_hours: Number(interval.input.value), digest_interval_days: Number(digest.input.value), timezone: timezone.input.value.trim() } };
    await api("/settings", { method: "PUT", body: payload }); await refresh(); announce("Workspace analysis settings saved. Run a new check to use them; your personal view is unchanged.");
  }, "Save analysis settings");
  else form.append(el("p", { class: "helper" }, "A policy owner can change workspace analysis and monitoring settings."));
  return form;
}
function contextForm() {
  const context = state.context || { topics: [], programs: [], funding_conditions: [], assets: [] };
  const form = el("form", { class: "panel-body" });
  const group = el("fieldset", { class: "plain-fieldset", disabled: !isOwner() });
  const topics = field("textarea", "topics", "Topics to review", { value: (context.topics || []).join("\n"), rows: 3, help: "One topic per line. Add matching topic tags when importing sources." });
  const programs = field("textarea", "programs", "Programs in scope", { value: (context.programs || []).join("\n"), rows: 3, help: "One agency program or business area per line." });
  const funding = field("textarea", "funding_conditions", "Known funding conditions", { value: (context.funding_conditions || []).join("\n"), rows: 3, help: "Record known facts and unresolved conditions. These entries do not themselves establish legal applicability." });
  const assetArea = el("div", { class: "asset-editors" });
  const assetEditors = [];
  const available = [...new Map((state.data.sources || []).map((source) => [source.source_key || source.id, source])).values()];
  const addAsset = (asset = {}) => {
    const name = field("text", "asset_name", "Asset or system name", { required: true, value: asset.name || "" });
    const program = field("text", "asset_program", "Program", { value: asset.program || "" });
    const owner = field("text", "asset_owner", "Responsible owner", { value: asset.owner || "" });
    const choices = [...available];
    for (const key of asset.source_keys || []) if (!choices.some((source) => (source.source_key || source.id) === key)) choices.push({ source_key: key, title: `${key} (source not imported)` });
    const keys = choices.map((source) => { const key = source.source_key || source.id; return { key, input: el("input", { type: "checkbox", checked: (asset.source_keys || []).includes(key) }), title: source.title }; });
    const editor = { id: asset.id || crypto.randomUUID(), name, program, owner, keys, removed: false };
    const card = el("div", { class: "asset-editor" }, name.node, el("div", { class: "field-grid" }, program.node, owner.node), el("fieldset", { class: "source-checkboxes" }, el("legend", {}, "Related source identifiers"), keys.length ? el("div", { class: "checkbox-list" }, keys.map(({ input, title }) => el("label", { class: "checkbox-item" }, input, el("span", {}, title)))) : el("p", { class: "helper" }, "Import sources before linking an asset to a source.")), isOwner() ? button("Remove asset", () => { editor.removed = true; card.remove(); }, "quiet", { class: "button button-quiet small" }) : null);
    assetEditors.push(editor); assetArea.append(card);
  };
  (context.assets || []).forEach(addAsset);
  group.append(topics.node, programs.node, funding.node, el("h3", {}, "Assets and systems"), el("p", { class: "helper" }, "No impact count is inferred without asset data and explicit source relationships."), assetArea, !(context.assets || []).length ? el("p", { class: "helper" }, "No assets have been supplied. Add relevant systems or services to make impact checks useful.") : null, isOwner() ? button("＋ Add asset", () => addAsset(), "secondary") : null);
  form.append(group);
  if (isOwner()) bindForm(form, async () => {
    const payload = { topics: lines(topics.input.value), programs: lines(programs.input.value), funding_conditions: lines(funding.input.value), assets: assetEditors.filter((editor) => !editor.removed).map((editor) => ({ id: editor.id, name: editor.name.input.value.trim(), program: editor.program.input.value.trim(), owner: editor.owner.input.value.trim(), source_keys: editor.keys.filter(({ input }) => input.checked).map(({ key }) => key) })) };
    await api("/context", { method: "PUT", body: payload }); await refresh(); announce("Office context saved. Run a new check to use the updated scope and asset relationships.");
  }, "Save office context");
  else form.append(el("p", { class: "helper" }, "A policy owner can update office context and assets."));
  return form;
}

let fieldCounter = 0;
function field(type, name, title, options = {}) {
  const id = `field-${name}-${++fieldCounter}`;
  const attrs = { id, name, required: options.required, placeholder: options.placeholder, minlength: options.minLength, maxlength: options.maxLength, min: options.min, max: options.max, step: options.step, accept: options.accept };
  let input;
  if (type === "select") { input = el("select", attrs, (options.options || []).map(([value, text]) => el("option", { value }, text))); if (options.value !== undefined) input.value = options.value; }
  else if (type === "textarea") { input = el("textarea", { ...attrs, rows: options.rows || 4 }); if (options.value !== undefined) input.value = options.value; }
  else input = el("input", { ...attrs, type, value: options.value ?? "" });
  const description = options.help ? el("p", { id: `${id}-help`, class: "helper" }, options.help) : null;
  if (description) input.setAttribute("aria-describedby", description.id);
  return { node: el("div", { class: "field" }, el("label", { for: id }, title, options.required ? " *" : ""), input, description), input };
}
function showDialog(title, description, content) {
  dialogContent.replaceChildren(el("div", { class: "dialog-titlebar" }, el("div", {}, el("h2", { id: "dialog-title" }, title), el("p", {}, description)), button("×", () => dialog.close(), "quiet", { class: "close-button", "aria-label": "Close dialog" })), content);
  dialog.showModal();
}
function bindForm(form, submit, submitLabel, { dialogForm = false, transform = (value) => value } = {}) {
  const error = el("div", { class: "form-error", role: "alert", tabindex: "-1" });
  const submitButton = el("button", { type: "submit", class: "button button-primary" }, submitLabel);
  form.append(error, el("div", { class: "form-actions" }, dialogForm ? button("Cancel", () => dialog.close(), "secondary") : null, submitButton));
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); error.textContent = ""; submitButton.disabled = true; submitButton.textContent = "Saving…";
    try { const values = Object.fromEntries(new FormData(form)); await submit(transform(values, form)); if (dialogForm) dialog.close(); }
    catch (caught) { error.textContent = errorMessage(caught); error.focus(); }
    finally { submitButton.disabled = false; submitButton.textContent = submitLabel; }
  });
}
function newSource() {
  const form = el("form");
  const kind = field("select", "kind", "Source role", { options: [["instrument", "Internal instrument"], ["external", "External reference"]] });
  const jurisdiction = field("text", "jurisdiction_id", "Jurisdiction ID", { required: true, value: state.session.workspace.jurisdiction_id, help: "Use the workspace jurisdiction for internal instruments; external references may use another jurisdiction." });
  const title = field("text", "title", "Source title", { required: true, maxLength: 200 });
  const preservedText = field("textarea", "text", "Preserved source text", { required: true, rows: 8, maxLength: 200000, help: "Paste exact text or choose a .txt file. Imports preserve a new version; they do not overwrite older evidence." });
  const file = field("file", "text_file", "Choose a text file (optional)", { accept: ".txt,text/plain", help: "Plain text only, up to 200 KB. PDF and DOCX conversion are not connected." });
  file.input.addEventListener("change", async () => { const selected = file.input.files?.[0]; if (!selected) return; try { if (selected.size > 200000) throw new Error("Choose a text file smaller than 200 KB."); if (!selected.name.toLowerCase().endsWith(".txt")) throw new Error("Choose a .txt file. PDF and DOCX conversion are not connected."); preservedText.input.value = await selected.text(); if (!title.input.value) title.input.value = selected.name.replace(/\.txt$/i, ""); } catch (error) { announce(errorMessage(error), true); file.input.value = ""; } });
  const sourceKey = field("text", "source_key", "Stable source identifier (optional)", { maxLength: 200, help: "Use the same identifier across revisions so change detection can connect them." });
  const replaces = field("select", "replaces_source_id", "Replaces an earlier source version (optional)", { options: [["", "No earlier version"], ...(state.data.sources || []).map((source) => [source.id, `${source.title} · v${source.version}`])] });
  replaces.input.addEventListener("change", () => { const previous = (state.data.sources || []).find((source) => source.id === replaces.input.value); if (previous) sourceKey.input.value = previous.source_key || previous.id; });
  const metadata = el("details", { class: "settings-details", open: advanced() ? "" : null }, el("summary", {}, "Dates, authority, and analysis metadata"),
    el("div", { class: "field-grid" }, jurisdiction.node, field("url", "source_url", "Authoritative source URL (optional)", { placeholder: "https://…" }).node),
    el("div", { class: "field-grid" }, field("select", "authority_type", "Authority type", { options: [["internal_policy", "Internal policy"], ["statute", "Statute"], ["regulation", "Regulation"], ["executive_order", "Executive order"], ["adopted_standard", "Adopted standard"], ["voluntary_standard", "Voluntary standard"], ["guidance", "Guidance"], ["research", "Research"], ["other", "Other / unconfirmed"]] }).node, field("select", "legal_status", "Legal status", { options: [["unknown", "Unknown / unconfirmed"], ["in_force", "In force"], ["adopted_not_effective", "Adopted, not effective"], ["draft", "Draft"], ["guidance", "Guidance"], ["research", "Research"], ["repealed", "Repealed"]] }).node),
    el("div", { class: "field-grid" }, field("date", "effective_from", "Effective from (optional)", { help: "Required before a binding determination can be confirmed." }).node, field("date", "effective_to", "Effective to (optional)", { help: "The end date is exclusive." }).node), field("text", "adoption_reference", "Adoption reference and scope (if applicable)", { maxLength: 2000, help: "An adopted standard needs the adopting authority, exact version, and scope before a binding determination." }).node,
    sourceKey.node, replaces.node, field("textarea", "reference_keys", "Referenced source identifiers", { rows: 3, help: "One identifier per line. Include the sources this document cites." }).node, field("textarea", "topics", "Topic tags", { rows: 3, help: "One topic per line. Match your office's topic list for targeted coverage checks." }).node, field("select", "reference_scope", "Reference scope", { options: [["private", "Private workspace material"], ["public", "Public reference, eligible for peer research"]], help: "Mark only genuinely public external material as public. This does not grant access to another office's private records." }).node);
  form.append(kind.node, title.node, field("text", "version", "Source version", { required: true, value: "1.0", maxLength: 80 }).node, file.node, preservedText.node, metadata);
  bindForm(form, async (values) => { await api("/sources", { method: "POST", body: values }); state.view = "sources"; await refresh(); announce("Source version imported and preserved. Check now to include it in a new review."); }, "Import snapshot", { dialogForm: true, transform: (values) => { delete values.text_file; return { ...values, source_url: values.source_url || null, effective_from: values.effective_from || null, effective_to: values.effective_to || null, adoption_reference: values.adoption_reference || null, source_key: values.source_key || null, replaces_source_id: values.replaces_source_id || null, reference_keys: lines(values.reference_keys), topics: lines(values.topics) }; } });
  showDialog("Add a source version", "Provide policy text or an external reference. Dates and analysis metadata are optional; missing inputs stay visible in the results.", form);
}
function newRun() {
  const available = state.data.sources || [];
  if (!available.some((source) => source.kind === "instrument") || !available.some((source) => source.kind === "external")) { announce("Import at least one internal instrument and one external reference before creating a review.", true); navigate("sources"); announce("Import at least one internal instrument and one external reference before creating a review.", true); return; }
  const form = el("form");
  form.append(field("text", "title", "Review title", { required: true, maxLength: 200, placeholder: "e.g., Quarterly AI policy review" }).node, field("date", "as_of", "Review as-of date", { required: true, value: today() }).node,
    el("fieldset", { class: "source-checkboxes" }, el("legend", {}, "Pinned source snapshots *"), el("p", { class: "helper" }, "Select at least one internal instrument and one external reference."), el("div", { class: "checkbox-list" }, available.map((source) => el("label", { class: "checkbox-item" }, el("input", { type: "checkbox", name: "source_ids", value: source.id, checked: true }), el("span", {}, source.title, el("small", {}, `${label(source.kind)} · v${source.version}`)))))),
    field("textarea", "coverage_note", "Coverage limitations", { required: true, minLength: 10, value: "Coverage is unverified. This manual review considers only the selected source snapshots.", help: "Make missing material, review scope, and uncertainty visible." }).node);
  bindForm(form, async (values) => { const created = await api("/runs", { method: "POST", body: values }); state.run = await api(`/runs/${encodeURIComponent(created.id)}`); state.view = "run"; await refresh(); announce("Review created with pinned sources and profile. Add findings manually from the evidence."); }, "Create review", { dialogForm: true, transform: (values, target) => ({ ...values, source_ids: new FormData(target).getAll("source_ids") }) });
  showDialog("Create a review", "This starts a manual, evidence-led review. It does not run automated legal analysis.", form);
}
function newFinding(run) {
  const pinned = run.sources || (state.data.sources || []).filter((source) => run.source_ids?.includes(source.id));
  const internal = pinned.filter((source) => source.kind === "instrument");
  const external = pinned.filter((source) => source.kind === "external");
  const form = el("form");
  form.append(field("text", "summary", "Finding summary", { required: true, minLength: 5, maxLength: 300 }).node,
    el("div", { class: "field-grid" }, field("select", "category", "Category", { options: [["missing_obligation", "Potential uncovered obligation"], ["conflict", "Potential conflict"], ["stale_reference", "Stale reference"], ["public_commitment", "Unsupported public commitment"], ["opportunity", "Optional improvement"]] }).node, field("select", "severity", "Issue severity", { options: [["low", "Low"], ["medium", "Medium"], ["high", "High"], ["critical", "Critical"]] }).node),
    field("textarea", "rationale", "Analysis rationale", { required: true, minLength: 10, help: "Explain the issue, scope, exceptions, and any counterevidence. Applicability is reviewed separately." }).node,
    field("select", "instrument_source_id", "Internal instrument", { options: internal.map((source) => [source.id, source.title]), required: true }).node,
    field("textarea", "instrument_quote", "Exact instrument excerpt", { required: true, help: "The excerpt must appear exactly in the selected source. Find preserved text in the source library." }).node,
    field("text", "instrument_location", "Instrument location", { required: true, placeholder: "e.g., Section 2, paragraph 1" }).node,
    field("select", "external_source_id", "External reference", { options: external.map((source) => [source.id, source.title]), required: true }).node,
    field("textarea", "external_quote", "Exact external excerpt", { required: true }).node,
    field("text", "external_location", "External source location", { required: true, placeholder: "e.g., Section 3, paragraph 2" }).node);
  bindForm(form, async (values) => { const created = await api(`/runs/${encodeURIComponent(run.id)}/findings`, { method: "POST", body: values }); state.finding = created; state.view = "finding"; await refresh(); announce("Finding recorded with exact supporting excerpts. Applicability remains unconfirmed until reviewed."); }, "Record finding", { dialogForm: true });
  showDialog("Add an evidence-linked finding", "Record analysis against this review’s pinned inputs. This is a manual proposal, not an automated legal determination.", form);
}
async function exportRun(id) {
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}/export`, { credentials: "same-origin" });
    if (!response.ok) { await api(`/runs/${encodeURIComponent(id)}/export`); return; }
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = el("a", { href: url, download: `compass-review-${id}.json` }); document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    announce("Evidence bundle exported. It contains the preserved review inputs and recorded decisions.");
  } catch (error) { announce(errorMessage(error), true); }
}
async function exportBrief(id) {
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}/brief`, { credentials: "same-origin" });
    if (!response.ok) { await api(`/runs/${encodeURIComponent(id)}/brief`); return; }
    const url = URL.createObjectURL(await response.blob());
    const anchor = el("a", { href: url, download: `compass-review-${id}.txt` }); document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    announce("Accessible review brief exported.");
  } catch (error) { announce(errorMessage(error), true); }
}
async function loginScreen() {
  clearTimeout(state.pollTimer); state.pollTimer = null;
  document.getElementById("view-control").hidden = true;
  document.getElementById("logout").hidden = true;
  document.querySelectorAll(".nav-item").forEach((node) => { node.disabled = true; });
  let personas;
  try { personas = (await api("/demo/personas")).personas; }
  catch (error) { main.replaceChildren(el("section", { class: "login-card" }, el("div", { class: "eyebrow" }, "Development foundation"), el("h1", {}, "Sign-in is not configured."), el("p", { class: "subtitle" }, "Production identity integration is not included in this milestone. Start the documented local demo to explore synthetic workspaces."), el("p", { class: "helper" }, error.status === 404 ? "Demo sign-in is disabled on this server." : errorMessage(error)))); return; }
  main.replaceChildren(el("section", { class: "login-card" }, el("div", { class: "eyebrow" }, "Welcome to COMPASS"), el("h1", {}, "Explore a review workspace."), el("p", { class: "subtitle" }, "Choose a synthetic demo persona to try source imports, evidence-linked review, and policy-owner decisions."), el("div", { class: "persona-list" }, (personas || []).map((persona) => el("button", { type: "button", class: "persona", onClick: async (event) => { const target = event.currentTarget; target.disabled = true; try { await api("/demo/session", { method: "POST", body: { persona: persona.id } }); await loadSession(); announce("Synthetic demo workspace opened."); } catch (error) { announce(errorMessage(error), true); target.disabled = false; } } }, el("span", {}, el("strong", {}, persona.name), el("small", {}, `${typeof persona.workspace === "string" ? persona.workspace : persona.workspace?.name || "Demo workspace"} · ${label(persona.role)}`)), el("span", { class: "arrow", "aria-hidden": "true" }, "→")))), el("div", { class: "coverage-note" }, el("strong", {}, "A working foundation, with synthetic evidence"), "Demo personas are local development access, not production authentication. The external source database, identity provider, and real state instruments are not connected.")));
}
async function loadSession() {
  state.session = await api("/session");
  state.mode = (await api("/preferences")).view_mode;
  const workspace = state.session.workspace;
  document.getElementById("account-label").replaceChildren(document.createTextNode(state.session.user.name), el("small", {}, `${workspace.name} · ${label(workspace.role)}`));
  document.getElementById("logout").hidden = false;
  document.querySelectorAll(".nav-item").forEach((node) => { node.disabled = false; });
  state.view = "overview"; state.run = null; state.finding = null; state.analysisRunId = null; await refresh();
}
document.getElementById("navigation").addEventListener("click", (event) => { const target = event.target.closest("[data-view]"); if (target && state.session) navigate(target.dataset.view); });
document.getElementById("view-mode").addEventListener("change", async (event) => {
  const control = event.currentTarget; const previous = state.mode; control.disabled = true;
  try { const preferences = await api("/preferences", { method: "PUT", body: { view_mode: control.value } }); state.mode = preferences.view_mode; if (!advanced() && ["insights", "monitoring", "activity"].includes(state.view)) state.view = "overview"; render(); announce(`${label(state.mode)} view saved for your account. Workspace analysis settings have not changed.`); }
  catch (error) { control.value = previous; announce(errorMessage(error), true); }
  finally { control.disabled = false; }
});
document.getElementById("logout").addEventListener("click", async () => { try { await api("/logout", { method: "POST" }); state.session = null; state.data = null; state.run = null; state.finding = null; announce(); document.getElementById("account-label").textContent = "Local development"; await loginScreen(); } catch (error) { announce(errorMessage(error), true); } });
loadSession().catch(async (error) => { if (error.status !== 401) announce(errorMessage(error), true); await loginScreen(); });
