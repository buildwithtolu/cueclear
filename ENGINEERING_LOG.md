# CueClear — Living Engineering Log

> Active source of truth for hackathon hardening. Updated as issues are identified and fixed.

**Track:** Parallel (Google Cloud Agentic Cinema)  
**Last updated:** 2026-09-05 (ADK audit tool wiring)

---

## 1. Original Problem

After picture lock, assistant editors and music supervisors must manually build music cue sheets: scrub timelines, look up ASCAP/BMI/PRS work IDs and rights holders, verify that writer shares and publisher shares each sum to 100%, and deliver network-ready Excel / CISAC XML. Missing or mismatched splits delay distribution and block royalties.

## 2. Core Solution

CueClear is a single-workflow agentic product:

1. Ingest CMX 3600 EDL or Premiere/FCP XML timelines  
2. Query PRO / web sources via Parallel Search  
3. Ground writers, publishers, and shares with Gemini structured extraction  
4. Dual-sided split audit (Case A confirmed / Case B undisclosed / Case C partial)  
5. Export PMA Excel, CISAC AVCS XML, and audit JSON  

**Target user:** music supervisors, assistant editors, post-production legal / delivery teams.  
**Core value:** turns days of manual PRO lookups into a traceable, auditable clearance pass with honest compliance scoring (undisclosed splits do not count as cleared).

## 3. Current Architecture

```
Frontend (studio console, SSE terminal, cue matrix, inspect/sign-off modal)
    → FastAPI (upload, stream-clearance, export)
        → EDL / XML parsers
        → CueClearADKOrchestrator (main path)
            → Parallel Search tool
            → Gemini ExtractedPROData extraction
            → split_reconciler (3-tier)
        → Excel / CISAC / JSON exporters
```

**Important notes:**
- This is a Web2 / Google Cloud + Parallel agent product. There is no Web3 / wallet / chain component, and none is planned.
- Submission deliverables (public GitHub, hosted demo, demo video) are in progress separately and are not treated as product defects in this log.

## 4. Mentor/Judge Feedback (condensed)

1. ADK `Agent`/`Runner` constructed but never executed — scripted tool loop wearing ADK branding.  
2. Parallel called via raw `httpx`, not official `parallel-web` SDK / grounding / MCP.  
3. Health/docs claim “Parallel MCP” without MCP.  
4. Fabricated Work IDs / ISWCs / 100% shares for unknown tracks destroy trust.  
5. `SplitStatus` used in ADK orchestrator without import — Case B path can crash.  
6. `requirements.txt` missing `google-adk` (and should include `parallel-web`).  
7. Supervisor sign-off is client-only and does not update export manifest.  
8. Hero / marketing copy dilutes the product (“15 visual identities”).  
9. Keep one problem: locked edit → cleared cue sheet. Do not expand into unrelated products.

## 5. Identified Bottlenecks

| ID | Issue | Priority | Status |
|---|---|---|---|
| B01 | `SplitStatus` NameError in ADK Case B messaging | P0 | Done |
| B02 | `requirements.txt` incomplete vs claimed stack | P0 | Done |
| B03 | Fabricated PRO identities for unknown tracks | P0 | Done |
| B04 | False `parallel_mcp_active` / MCP claims | P0 | Done |
| B05 | Parallel integration not via official SDK | P0 | Done |
| B06 | Supervisor sign-off not persisted to exports | P1 | Done |
| B07 | ADK Runner not driving the clearance loop | P1 | Done |
| B08 | Misleading product copy in UI hero | P2 | Done |
| B09 | Hardcoded duration metadata in frontend | P1 | Done |
| B10 | Dual orchestrators (ADK vs Gemini) confuse runtime path | P2 | Deferred (DO NOT TOUCH risk) |
| F01 | `IDENTITY ARCHETYPES (15)` leftover UI copy | P0 | Done |
| F02 | Silent ADK fallback hides demo integrity risk | P0 | Done |
| F03 | Demo script lacks non-catalog / pending path | P0 | Done |
| F04 | Live Parallel hits merge catalog rights under live label | P1 | Done |
| F05 | Parallel Search-only; no Extract depth | P1 | Done |
| F06 | Audit modal missing search_id / excerpts / invoke_mode | P1 | Done |

### Final Pass Protected Areas (DO NOT TOUCH)
- Case A/B/C split reconciler math
- EDL/XML parsers
- Excel/CISAC exporters (except provenance display if needed)
- Core ingest → clear → export journey shape
- Swiss studio visual system as a whole

## 6. Active Fixes

_Final Improvement Pass complete for product P0/P1. Submission deliverables (repo/hosting/video) remain separate._

## 7. Completed Fixes

### F01–F06 / B09 — Final Improvement Pass (P0/P1) — DONE

**Issues:** Leftover archetype UI copy; silent ADK fallback; weak demo path for Case B/non-catalog; live+catalog rights merge; Search-only Parallel depth; thin audit modal; hardcoded durations.  
**Root cause:** Prior hardening stopped short of Parallel Extract and a few credibility/demo gaps.  
**Fix:**
- Replaced `IDENTITY ARCHETYPES (15)` with cue-sheet status filters.
- ADK fallback now emits `[ADK_FALLBACK]` SSE with reason.
- Added `sample_mixed_clearance.edl` + Reel 03 UI + README demo script covering Case A/B/non-catalog.
- Live Parallel path no longer injects catalog rights; provenance is explicit.
- Live path now runs `AsyncParallel.search` then `AsyncParallel.extract` on top PRO URLs before Gemini grounding.
- Audit modal shows provenance, invoke_mode, search_id, extract_id, URLs, excerpts, confidence, fallback reason.
- Sequence duration/FPS derived from parsed clips.
**Verification:** 22 core tests passed. Offline mixed-clearance e2e showed visible ADK fallback, Case B pending, unresolved unknown cue, and provenance fields.  
**Impact:** Stronger demo integrity and Parallel depth without changing the core problem.  
**Hackathon impact:** Improves Technological Implementation and Design; makes Parallel contribution visible and removable-only-at-cost.  
**Parallel relevance:** Parallel is now the web-truth layer (Search discovers PRO sources; Extract deep-reads them; Gemini grounds shares from that text). Removing Parallel collapses live clearance quality to offline catalog/unresolved.

### B08 — Misleading hero copy (P2) — DONE

**Issue:** Hero claimed “15 divergent visual identities,” diluting the clearance product.  
**Implementation:** Replaced with timeline → Parallel → Gemini → cue sheet messaging. Terminal bootstrap text updated to ADK tool-call + `parallel-web`.  
**Verification:** Static HTML review.  
**Hackathon impact:** Faster judge comprehension of the core product.

### B07 — ADK Runner honesty / hybrid tool-calling (P1) — DONE

**Issue:** ADK `Agent`/`Runner` were constructed but never executed; Parallel was called directly while UI claimed an ADK loop.  
**Evidence:** `adk_orchestrator.py` never called `runner.run_async`.  
**Root cause:** Prototyping speed vs agent framework integration.  
**Impact:** Credibility hit on Technological Implementation if judges read the orchestrator.  
**Implementation:** Hybrid path — ADK Runner invokes `parallel_pro_search_tool` per cue when Gemini is available; Gemini structured extract + split audit stay deterministic. Direct tool fallback when Gemini/ADK unavailable, labeled in SSE as `invoke_mode`. Agent instruction/tools limited to Parallel search. Model pinned to `gemini-3.6-flash`.  
**Verification:** Offline fallback path cleared Midnight City with `direct_tool_fallback`. Mocked Runner returned `adk_runner` mode from `function_response`. Regression: 19 tests passed.  
**Hackathon impact:** Real google-adk runtime use without sacrificing demo reliability.  
**Remaining limitations:** Full multi-tool autonomous planning still not used (intentional for stability).

### B06 — Supervisor sign-off persistence (P1) — DONE

**Issue:** UI sign-off mutated browser state only; Excel/CISAC still used uncleared `CURRENT_MANIFEST`.  
**Evidence:** `app.js` `confirmSplitSignOff` was client-only; no `/api/sign-off`.  
**Root cause:** Demo shortcut.  
**Impact:** Broken human-in-the-loop story for Case B, the strongest domain beat.  
**Implementation:** Added `supervisor_signed_off` / `signed_off_at` / `signed_off_by` fields; `apply_supervisor_sign_off()`; `POST /api/sign-off`; frontend posts to API and refreshes from manifest; Excel status shows `CLEARED (SUPERVISOR SIGN-OFF)`.  
**Verification:** Domain + API export tests passed (`test_supervisor_sign_off_*`, `test_sign_off_persists_into_export_manifest`).  
**Hackathon impact:** Complete Case B demo arc into deliverables.

### B05 — Parallel via official SDK (P0) — DONE

**Issue:** Parallel Search was called with raw `httpx` POST, not the official `parallel-web` SDK cited in track rules.  
**Evidence:** `parallel_tool.py` previously posted to `api.parallel.ai/v1/search` via `httpx.AsyncClient`.  
**Root cause:** Fastest integration path during prototyping.  
**Impact:** Weaker Parallel-track Technological Implementation and Stage One ambiguity vs peers using the official package.  
**Implementation:** Live search now uses `AsyncParallel.search(...)` from `parallel-web`, with retry on `RateLimitError` / timeout / 5xx. Updated unit retry test and live connection test to the SDK.  
**Verification:** `tests/test_parallel.py` — 5 passed.  
**Hackathon impact:** Direct Parallel-track requirement alignment.  
**Remaining limitations:** Extract API not yet wired (competitive improvement).

### B04 — False Parallel MCP claims (P0) — DONE

**Issue:** Health endpoint hard-coded `parallel_mcp_active: True` with no MCP. Docs labeled Parallel as MCP.  
**Evidence:** `main.py` health route; README architecture box; ADK docstring.  
**Root cause:** Marketing language ahead of implementation.  
**Impact:** Looks like eligibility padding to technical judges.  
**Implementation:** Health now reports `parallel_search_configured` + `parallel_integration: "search_api"`. README/ADK wording corrected. API test updated.  
**Verification:** `test_health_route` passed.  
**Hackathon impact:** Honesty / Stage One trust.  

### B03 — Fabricated PRO identities (P0) — DONE

**Issue:** Unknown live/offline tracks were given invented Work IDs, ISWCs, and 100% writer/publisher shares.  
**Evidence:** `parallel_tool.py` dynamic live return and offline custom fallback; `gemini_orchestrator.py` default ExtractedPROData.  
**Root cause:** Demo convenience shortcuts presented as cleared rights.  
**Impact:** Judges/domain experts would treat the product as fake clearance. Undermines Impact and trust.  
**Implementation:** Unknown live hits return excerpts only (`NEEDS_EXTRACTION`, empty holders). Offline unknowns return `UNREGISTERED_OR_UNVERIFIED` with empty holders. Gemini fallback returns empty holders with review notes. Updated `test_parallel_search_custom_library_cue`.  
**Verification:** Unit tests passed. Catalog Midnight City still clears; unknown cue flags `UNREGISTERED_WORK_FLAGGED`.  
**Hackathon impact:** Credibility of the core clearance claim.  
**Remaining limitations:** Offline `KNOWN_PRO_CATALOG` remains as an intentional labeled fallback when Parallel is unavailable.

### B02 — Incomplete requirements.txt (P0) — DONE

**Issue:** Docs claimed `google-adk`; Parallel track expects `parallel-web`. Neither was in `requirements.txt`.  
**Evidence:** `requirements.txt` only listed `google-genai` among Google/Parallel packages.  
**Root cause:** Dependencies drifted from architecture claims.  
**Impact:** Fresh installs cannot reproduce the documented stack. Judges cloning the repo hit import failures.  
**Implementation:** Added `google-adk>=2.7.0` and `parallel-web>=1.3.0`; tightened `google-genai>=1.0.0`. Installed `parallel-web` and verified `from parallel import Parallel`.  
**Verification:** `parallel-web` imports successfully. Existing Python 3.13 env already had `google-adk 2.7.0`.  
**Hackathon impact:** Stage One installability and Parallel-track package visibility.  
**Remaining limitations:** Code still calls Parallel via `httpx` until B05.

### B01 — SplitStatus NameError (P0) — DONE

**Issue:** Case B messaging referenced `SplitStatus` without importing it.  
**Evidence:** `adk_orchestrator.py` used `SplitStatus.PRO_REGISTERED_SPLIT_UNDISCLOSED` while schemas import omitted `SplitStatus`.  
**Root cause:** Incomplete import after 3-tier status model was added.  
**Impact:** Demo-critical Case B (undisclosed splits / pending sign-off) could crash mid-stream.  
**Implementation:** Added `SplitStatus` to schemas import in `adk_orchestrator.py`.  
**Verification:** Catalog-only clearance of `Exit Music For A Film` emitted `cue_flagged` with `PRO_REGISTERED_SPLIT_UNDISCLOSED` and sign-off messaging, no `NameError`.  
**Hackathon impact:** Case B is the strongest domain-literacy beat in the demo.  
**Remaining limitations:** None for this bug.

## 8. Remaining P0/P1 Issues

No open product P0/P1 items from the final-pass list.

**Submission track (separate owners):** public repo, hosted URL, demo video, Devpost form.

### Final hackathon requirement check (product-only)

| Requirement | Status |
|---|---|
| Functional Gemini + Google agent SDK (`google-adk` / `google-genai`) | Satisfied |
| Parallel Search at runtime via official `parallel-web` | Satisfied |
| Meaningful Parallel contribution beyond name-drop | Satisfied (Search + Extract → Gemini grounding) |
| Real M&E workflow (cue sheet / rights clearance) | Satisfied |
| Coherent product experience (ingest → clear → audit → export) | Satisfied |
| Hosted URL / public repo / demo video | Hosted URL + public repo satisfied; demo video still in progress |

## 9. Competitive Improvements

- Gemini cue classification (music / score / SFX)  
- Cloud Run deploy notes (submission track)  
- Quarantine unused secondary orchestrator path if docs confuse judges
## 10. Deliberately Excluded Features

| Idea | Why excluded |
|---|---|
| Multi-partner stack (Grafana, ClickHouse, etc.) | Dilutes Parallel-track focus |
| Second product surfaces (budgeting, script coverage, fan chatbot) | Breaks one-problem constraint |
| Auth/SSO theater | Not required for core clearance demo |
| AAF support (for now) | Nice-to-have; EDL/XML covers demo |
| Web3 / on-chain rights | Unrelated to this problem and this hackathon track |

## 11. Demo-Critical Flows

1. Load **Reel 03 Mixed Clearance** → detect 3 audio cues  
2. Run clearance → ADK Parallel Search tool-call → Parallel Extract → Gemini grounding → split audit  
3. Inspect Case A / Case B / non-catalog unresolved with provenance + Search/Extract IDs  
4. Supervisor sign-off updates compliance **and** exported Excel/CISAC  
5. Export Excel + CISAC without crash  
6. If Gemini unavailable, terminal shows `[ADK_FALLBACK]` explicitly  

## 12. Final Submission Checklist

- [x] Public GitHub/GitLab/Bitbucket with MIT license visible  
- [x] Hosted project URL (`https://cueclear.vercel.app/`)  
- [ ] ≤3 min English demo video (in progress separately)  
- [ ] Devpost form + Parallel track selected  
- [ ] README matches real architecture (no MCP/ADK overclaims)  
- [ ] `requirements.txt` installs cleanly  
- [ ] Demo-critical flows verified on hosted build  

---

## Change Records

### 2026-09-05 — ADK split-audit tool + doc honesty

**Issue:** ADK only owned Parallel Search. `audit_and_reconcile_splits_tool` existed but was unused by the Runner. `PROJECT_OVERVIEW.md` overclaimed that ADK invoked Gemini extract and audit tools.

**Fix:**
- Registered `audit_and_reconcile_splits_tool` on the ADK agent alongside `parallel_pro_search_tool`.
- After deterministic Gemini extract, ADK invokes split audit per cue (fresh session; direct fallback labeled `[ADK_FALLBACK]`).
- Cue schema/UI now surface `audit_invoke_mode` / `audit_fallback_reason`.
- Docs/README/demo script aligned to the real hybrid pipeline: ADK Search → Gemini extract → ADK audit.
- Added local run instructions to README.

**Verification:** `test_adk_uses_fresh_session_per_cue` asserts both search and audit `adk_runner` paths (3+3 sessions).

**Hackathon impact:** Stronger Technological Implementation without product drift.

### 2026-09-05 — ADK consistency + live latency + demo polish

**Issues:**
1. Live probe: cue 1 `invoke_mode=adk_runner`, cues 2–3 `direct_tool_fallback` after shared ADK session reuse.
2. Mixed clearance ~152s wall time too slow for judge click-through.
3. README still had placeholder live demo URL; provenance IDs mostly buried in Details modal.

**Root cause (ADK):** `process_timeline_stream` created one `InMemorySessionService` session and reused it for every `runner.run_async`. After cue 1’s tool call sat in history, Gemini often answered in text only for later cues (“call exactly once”), so `_invoke_parallel_via_adk` fell back and emitted `[ADK_FALLBACK]`. Fallback also paid a wasted ADK round-trip before direct Parallel.

**Fix:**
- Fresh ADK session per cue (`{clearance_id}-cue-{n}`), deleted after each invoke.
- Prefetch next cue’s ADK+Parallel search while current cue’s Gemini extract/audit runs.
- ADK model failover on 404/429: `gemini-3.6-flash` → `gemini-flash-latest` → `gemini-3-flash-preview` (env override via `CUECLEAR_ADK_MODEL`).
- Parallel Extract: top 2 PRO URLs (was 3), `max_chars_total=8000`, client timeout 25s; Gemini grounding capped to 8×1500-char excerpts.
- UI: cue-row chips for provenance / invoke_mode / Search ID / Extract ID; Mixed sample marked recommended; mobile 360px reel grid + CTA polish.
- README canonical demo URL `https://cueclear.vercel.app/` + 60s judge path.

**Verification:**
- Unit: `test_adk_uses_fresh_session_per_cue` asserts 3 distinct cue sessions and `invoke_mode=adk_runner` for all music cues (no `[ADK_FALLBACK]`).
- Core regression: 24 passed (`test_agent`, `test_parallel`, `test_stress_audit`, `test_api`).
- Local Mixed Clearance live probe (2026-09-05):
  - Wall time **68.1s** (prior hosted baseline ~**152s**)
  - `invoke_mode`: **adk_runner / adk_runner / adk_runner** (0 `[ADK_FALLBACK]`)
  - Provenance: all `LIVE_PARALLEL_SEARCH_AND_EXTRACT`
  - Outcomes: Midnight City CLEARED · Exit Music PENDING · Unknown UNRESOLVED
  - Prefetch events observed between cues
- Hosted `https://cueclear.vercel.app/` still serves pre-change build until deploy/push.

**Follow-up:** ADK model rotation now also treats Gemini `503` / `UNAVAILABLE` / high-demand errors as retriable (hosted Mixed Clearance had cue 1 fall back on 503 before this).

**Remaining risks before Top 3:**
- Gemini free-tier quotas on `gemini-3.6-flash` (~20/day) can force model rotation or `[ADK_FALLBACK]` during heavy local testing; production/demo keys should be paid or higher-limit.
- Trailer video still missing.

**Hackathon impact:** Direct Technological Implementation fix for ADK honesty + snappier demo; Design/Impact via unmistakable Parallel provenance on the happy path.

### 2026-08-21 — Hardening pass started

Created this log from mentor/judge evaluation. Beginning incremental P0 fixes with B01.
