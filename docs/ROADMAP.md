# Development roadmap

The first release is a shared policy-review service for policy leads at state government offices. It must support multiple states. Amendment drafting is deferred. The external policy database is planned but not yet available. Uploaded prompts, registers, instruments, and BASE-1 are organized in the [Georgia case study](../case-studies/georgia/README.md); neutral adaptations live in the [reusable method](../method/README.md). Their presence does not establish legal currency or independently validated findings.

The local application now combines an evidence-linked review workflow, nine standard-library rule-based review aids, personal Simple/Advanced views, workspace controls, assignment and local monitoring. It uses synthetic sample data. This is a foundation for the shared service, not a claim of legal accuracy or production readiness. Detailed check behavior and limitations are in [ANALYSIS.md](ANALYSIS.md).

## Five checks for every change

1. **Need:** identify the policy lead's task and measurable benefit. An idea without a demonstrated need stays deferred.
2. **Reuse:** inspect existing code, uploaded prompts/registers, source-system capabilities and established application paths before creating another implementation.
3. **Standard/native:** prefer standard dates, JSON, hashing, database transactions and constraints, native form controls and semantic HTML when sufficient.
4. **Installed dependency:** check manifests and existing libraries before adding a package. Reuse a supported dependency rather than creating a custom substitute.
5. **Minimum:** choose the smallest clear implementation and a meaningful acceptance check. A module is preferable to a new service unless independent operation is required. Legal judgment must not be reduced to numeric arithmetic for convenience.

## Initial implementation choices

| Choice | Reason | Boundary |
|---|---|---|
| One FastAPI application | Reuses available tooling and supports a typed API without separate pipeline services | Hosting architecture remains open |
| Python standard-library SQLite store | Transactions and a runnable local development environment without another service | Not the selected shared production database; production migration and isolation review remain required |
| Native HTML/CSS/JavaScript | Adequate for forms, evidence review and navigation; avoids an unnecessary frontend framework | Validate keyboard, screen-reader and export use as the UI grows |
| Curated text files/paste and explicit source versions | Proves evidence handling without pretending that rich document ingestion or the future database already works | PDF/DOCX parsers/OCR and a live source adapter are later increments |
| Local demo personas and synthetic examples | Enables development and isolation tests without fabricated real customer data or a custom production identity system | Demo login must not be exposed as production authentication |
| Deterministic rule-based review aids | Reuses standard-library text differences, regex, dates and explicit mappings to surface bounded candidates | No LLM, embeddings, semantic legal inference or external-source collection |
| Human-entered findings and policy-lead review | Keeps review suggestions separate from attributed applicability and decisions | Analysis controls never bypass approval; amendment generation remains deferred |
| Durable local database jobs | Supports retryable source/context/date checks, opt-in periodic checks and in-app digests without a broker | A running local CLI worker is required; this does not connect a remote feed or email |
| Personal view mode separate from workspace controls | Users can simplify the interface without changing which checks the office runs | Only owners change analysis settings and context; evidence is available in both views |

Customer isolation and legal scope are different: an office workspace owns private records, while jurisdiction describes an analysis. Test two workspaces in the same jurisdiction as well as different jurisdictions. Explicitly permitted public peer evidence is not a leak.

## Phases and acceptance gates

| Phase | Work | Exit gate |
|---|---|---|
| 0. Inputs and contracts | Record customer scope and missing inputs; inspect old materials; agree authoritative source/version, applicability and evaluation contracts; select a second-state partner/corpus. | [Input register](INPUTS.md) has owners and known gaps; the team has enough real material to test a bounded review and a defined customer access boundary. |
| 1. Shared foundation and local review aids | Implemented paths include isolated office workspaces, versioned sources, pinned review inputs, evidence-linked findings, policy-lead decisions, assignments, brief/evidence exports, nine rule-based checks, controls and durable local monitoring. Use synthetic examples to validate the implementation. | A complete local case works. Tests reject cross-workspace reads/writes and unprivileged approvals; quotations trace to pinned source text; report snapshots, decision attribution, monitoring retries and historical evidence survive inspection/export. This is not a production launch gate. |
| 2. Two-state proof | Run the same workflow on approved real inputs from Georgia and a structurally different state. Preserve definitions and exceptions; use configuration for jurisdiction-specific facts. | Both offices can review evidence without state-specific code branches. Private material stays isolated, permitted public references work, and expert review identifies model/data gaps explicitly. |
| 3. Reliable external ingestion and operational monitoring | Integrate the future source database through an adapter. Extend existing local source/context/date checks with verified provider snapshot/cursor/replay behavior. Add only required formats and preserve manual corrections. | Provider imports and retries are idempotent; effective-date changes work without feed updates; corrections/supersession and new-state catch-up work; failed or incomplete work remains visible. Existing local jobs alone do not satisfy external-feed reliability. |
| 4. Evaluated analytical expansion | Evaluate the current rule-based checks with real cases. Add model-assisted extraction, retrieval or comparison only where existing methods demonstrably miss useful evidence or consume material reviewer effort. Measure support, scope, exceptions, missed issues and reviewer burden. | Held-out independently reviewed cases meet agreed quality, effort, latency and cost thresholds. Uncertain applicability is visible and cannot silently become a binding claim. |
| 5. Shared production release | Integrate an appropriate identity provider and production database; verify isolation and job behavior, retention, backup/restore, operational alerts, cost limits and accessibility. Pilot with policy leads in two real states. | Quality, authorization, recovery, source freshness and usability gates pass under the expected first-release workload. Ownership and incomplete-run handling are documented. |

The local SQLite application, synthetic cases, rule outputs and demo personas do not satisfy Phase 5. Shared production remains the release goal; the local implementation is a development milestone. Estimate calendar dates after representative inputs, staffing and provider contracts are available.

## Domain rules to preserve

- Determine applicability from authority, scope, conditions, status, dates and reviewed evidence. A high weight does not make a source binding, and a low one cannot remove an obligation.
- Keep applicability, severity, evidence quality and optional ranking separate. Retain `unknown` when essential facts are missing.
- Preserve source text, versions, locations, profile content, inputs and actual outputs. Promise inspectable historical evidence, not identical regeneration of nondeterministic model text.
- Require an explicit attributed action by an authorized policy lead for a production decision. The planning assumption of approved suggestions is not an application audit event.
- Distinguish supported obligation findings from optional peer-practice or research recommendations. Missing coverage and unfinished work must remain visible.
- Treat retrieved documents as evidence, not instructions or permission for tools and approvals.

## Evaluation

Start with independently reviewed positive and negative cases. Include exceptions, conflicting definitions, future-effective provisions, conditional obligations, repeal/supersession, unavailable evidence, legitimate public peer references and unauthorized private references. Report missed important issues and unsupported findings separately; an aggregate percentage must not hide severe errors.

Test meaningful behaviors: tenant and role boundaries; immutable run/source evidence; exact quotation support; date/status constraints; decision attribution; import replay/recovery when implemented; and actual user navigation/output. Old model outputs are regression candidates, not correctness labels. Automated accessibility checks complement keyboard and assistive-technology review.

## Deferred work

- Amendment drafting and a document editor.
- A universal ten-stage onboarding service, OCR for absent formats and a general-purpose rules language.
- Numeric authority-weight tables, unexplained confidence scores and automatic legal approval.
- Independent profile services, distributed orchestration, a dedicated vector database or infrastructure beyond measured first-release needs.
- State-specific encryption keys or separate database schemas without a confirmed requirement. Production encryption and access controls remain required.

## Next inputs

The full checklist and proposed external-source contract are in [INPUTS.md](INPUTS.md). Next priorities are reconciliation of the uploaded Georgia pack, authoritative source/version confirmation, an external database sample/design, a second-state partner, and a small independently reviewed evaluation set. File organization is complete; the [Georgia review backlog](../case-studies/georgia/REVIEW-STATUS.md) identifies content checks still pending.
