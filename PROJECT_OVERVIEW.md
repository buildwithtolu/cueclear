# 🎬 CueClear — Project Overview & Technical Handoff Document

> **Project Name:** CueClear  
> **Repository Path:** `C:\Projects\cueclear`  
> **Hackathon Event:** Google Cloud "Agentic Cinema" Summer Blockbuster Hackathon  
> **Selected Partner Track:** Parallel Partner Track  
> **Primary Technologies:** Google Cloud Agent Development Kit (`google-adk` 2.7.0, Gemini 3.6 Flash / flash-latest), Parallel Search & Extraction API (`parallel-web`), FastAPI, Python 3.11+, Vanilla HTML5/CSS/JS

---

## 1. Executive Summary & Core Concept

**CueClear** is an autonomous post-production agent that transforms raw video editing timelines into certified, broadcast-standard music cue sheets and legal clearance manifests.

### The Real-World Industry Problem
In professional film, television, and commercial production, one of the most tedious and legally critical bottlenecks is **music cue sheet creation and rights reconciliation**:
* When a picture edit is locked, assistant editors and music supervisors must scrub the entire timeline to catalog every piece of commercial music, original score, and sound design.
* For each track, they must manually search Performing Rights Organization (PRO) databases (such as **ASCAP**, **BMI**, **SESAC**, and **PRS**) to discover official Work IDs, ISWC codes, songwriters, and publishers.
* They must verify that writer shares equal **100%** and publisher shares equal **100%**, then format the results into strict broadcast network templates (for Netflix, HBO, EBU, etc.).
* Missing, unrepresented, or mismatched publisher splits delay distribution, risk copyright strikes, and block royalty payouts to composers.

### How CueClear Solves It
CueClear replaces days of manual spreadsheet entry with a single clearance workflow:
1. **Ingests** industry-standard timeline files (CMX 3600 `.edl` and Final Cut Pro / Premiere `.xml`) across standard industry framerates (23.976p, 24p, 25p PAL, 29.97 NDF/DF) with video cut filtering and stereo pair deduplication.
2. **ADK tool-calls Parallel Search** via `google-adk` `Runner` (`parallel_pro_search_tool` → official `parallel-web` Search + Extract).
3. **Grounds rights** with Gemini structured outputs (`ExtractedPROData`) from Parallel excerpts only, assigning `share: None` when percentages are undisclosed.
4. **ADK tool-calls split audit** via `audit_and_reconcile_splits_tool` (Case A confirmed / Case B undisclosed pending sign-off / Case C partial), with the same deterministic reconciler math underneath.
5. **Exports** PMA/Network Excel (`.xlsx`), CISAC Audio-Visual Cue XML (`.xml`), and audit JSON (`.json`).

---

## 2. Software Architecture & System Topology

```
┌─────────────────────────────────────────────────────────────┐
│                 Cinematic Studio Web Console                │
│    (Timeline Dropzone | Real-time Trace | Master Grid)       │
└──────────────────────────────┬──────────────────────────────┘
                               │ (HTTP / SSE Stream)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 FastAPI Gateway & Parsers                   │
│   • CMX 3600 EDL Parser (Audio filter & Drop-Frame math)    │
│   • Premiere / Final Cut Pro XML Parser (Stereo Dedup)      │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────────┐  ┌───────────────────────────┐
│     Google Cloud ADK Agent   │  │     Parallel Web Tool     │
│   (google-adk + Gemini)      │  │ (Search + Extract SDK)    │
│ • parallel_pro_search_tool   │  │ • Official parallel-web   │
│ • audit_and_reconcile_splits │  │ • Search ID / Extract ID  │
│ • Gemini extract (explicit)  │  │ • PRO URL deep-read       │
└──────────────┬───────────────┘  └────────────┬──────────────┘
               │                               │
               └───────────────┬───────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Broadcast Output Engines                   │
│   • Network-Standard Excel (.xlsx) via openpyxl             │
│   • Global CISAC AVCS Cue XML (.xml)                        │
│   • Clearance Audit Manifest (.json)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Five-Phase Hardened Architecture

### Phase 1: Ingestion & Parser Hardening (`backend/parsers/`)
* **EDL Video Cut Filtering:** In `backend/parsers/edl_parser.py`, non-audio tracks (`V`, `V1`, `V2`, `VA/V`) are cleanly filtered out, ensuring only audio events are processed.
* **XML Stereo Deduplication:** In `backend/parsers/xml_parser.py`, dual-channel stereo tracks sharing the same timecode boundaries and clean clip name are deduplicated into a single cue.
* **SMPTE 29.97 Drop-Frame Math:** Exact frame-to-timecode translation dropping frames :00 and :01 except every 10th minute.

### Phase 2: Dynamic Parallel PRO Search Tool Hardening (`backend/agent/parallel_tool.py`)
* **Endpoint:** `https://api.parallel.ai/v1/search`
* **Exponential Backoff:** Up to 3 retry attempts for HTTP 429 rate limits and 5xx network errors.
* **Query Normalization:** `clean_music_search_terms()` strips file extensions (`.wav`, `.mp3`), versioning (`_v2`, `_final`), and bracketed tokens (`[Remix]`, `(feat. XYZ)`).
* **Raw Excerpt Capture:** Returns `excerpts: List[str]` containing raw web text snippets alongside `search_id`, `latency_ms`, and `is_live_hit`.
* **Offline Resilience:** Preserves `KNOWN_PRO_CATALOG` when API keys are absent or network is unavailable.

### Phase 3: Gemini Structured Output Extraction (`backend/agent/gemini_orchestrator.py` & `adk_orchestrator.py`)
* **Schema Definition:** `ExtractedPROData` Pydantic model (`work_id`, `iswc`, `writers`, `publishers`, `confidence_notes`).
* **Strict Grounded Extraction:** Gemini ingests raw Parallel search excerpts with `response_mime_type="application/json"` and `response_schema=ExtractedPROData`.
* **No Synthetic Splits:** If percentage numbers are not explicitly published in the excerpt, Gemini assigns `share = None`, allowing the reconciler to flag the track rather than fabricating numbers.

### Phase 4: CISAC XML & Broadcast Excel Exporter Hardening (`backend/exporters/`)
* **`TypeError` Resilience:** Safe ternary formatting when `w.share` or `p.share` is `None` (e.g. `f"{w.share:.0f}%" if w.share is not None else "Undisclosed"`).
* **Excel Exporter (`excel_exporter.py`):** Outputs `"CLEARED"` vs `"ACTION REQUIRED (Undisclosed / Incomplete)"` with styled status colors and auto-fit column widths.
* **CISAC XML Exporter (`cisac_xml.py`):** Outputs `"<Share>UNDISCLOSED</Share>"` with standard nodes `<Sender>`, `<WorkOrigin>`, `<WorkTitle>`, and `<ISWC>`.

### Phase 5: Studio UI & Telemetry (`frontend/`)
* **3-Tier Split Classification:**
  * **Case A (`CONFIRMED_PUBLIC_SPLIT`):** 🟢 **CLEARED** (100% writer + 100% publisher).
  * **Case B (`PRO_REGISTERED_SPLIT_UNDISCLOSED`):** 🟡 **PENDING SIGN-OFF** (0% compliance numerator; informational equal distribution note requiring Music Supervisor sign-off).
  * **Case C (`PARTIAL_PUBLISHER_CLAIM_FLAGGED`):** 🔴 **PARTIAL CLAIM** (0% compliance numerator; publisher sum < 100%).
* **Live vs. Cached Badges:** Real-time indicator displaying `🌐 LIVE PARALLEL (214.5ms)` with search ID versus `⚠️ CACHED DEMO ARCHIVE`.
* **Real-Time Stream:** Live SSE reasoning stream and interactive cue detail inspection modal.

---

## 4. Complete Repository File Structure

```
C:\Projects\cueclear\
├── backend/
│   ├── main.py                     # FastAPI REST API & SSE streaming server
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py              # Pydantic schemas (SplitStatus, ExtractedPROData, ResolvedCue, Manifest)
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── edl_parser.py           # CMX 3600 EDL parser (video filtering & drop-frame math)
│   │   └── xml_parser.py           # Final Cut Pro / Premiere XML parser (stereo deduplication)
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── parallel_tool.py        # Parallel Search API tool (exponential backoff & excerpt capture)
│   │   ├── split_reconciler.py     # 3-Tier Split Reconciliation Engine & Compliance Scorer
│   │   ├── adk_orchestrator.py     # Native Google ADK Agent & Runner orchestration loop
│   │   └── gemini_orchestrator.py  # Grounded Gemini structured output extractor
│   └── exporters/
│       ├── __init__.py
│       ├── excel_exporter.py       # PMA / CISAC broadcast Excel (.xlsx) builder
│       └── cisac_xml.py            # CISAC Audio-Visual Cue Sheet XML (.xml) builder
├── frontend/
│   ├── index.html                  # Obsidian dark-mode studio single-page layout
│   ├── css/
│   │   └── studio.css              # Custom studio CSS (glass cards, neon accents, source badges)
│   └── js/
│       └── app.js                  # SSE streaming listener, drag-and-drop, table & modal
├── samples/
│   ├── sample_trailer.edl          # Real trailer EDL (M83, Hans Zimmer, Daft Punk, SFX)
│   └── sample_indie_reel.xml       # Real indie XML (Ludovico Einaudi, Radiohead)
├── tests/
│   ├── test_parser.py              # Phase 1: Video filtering & stereo deduplication tests
│   ├── test_parallel.py            # Phase 2: Query cleaning, excerpt capture & backoff retry tests
│   ├── test_agent.py               # Phase 3: Structured Gemini extraction (Case A/B/C) tests
│   ├── test_domain_accuracy.py     # Domain rigor: 3-tier classification & 0% backfill tests
│   ├── test_exporters.py           # Phase 4: Excel & CISAC XML TypeError resilience tests
│   ├── test_api.py                 # FastAPI endpoints & static frontend serving tests
│   └── test_live_services.py       # Live network test for real API keys
├── package.json                    # npm script runner
├── requirements.txt                # Python dependencies (includes google-adk)
├── pytest.ini                      # Test runner configuration
├── .gitignore                      # Strict security ignore file (protects .env and keys)
├── LICENSE                         # MIT Open Source License
├── .env.example                    # Template environment variables
├── .env                            # Active API keys (strictly gitignored)
├── README.md                       # Public repository documentation
└── PROJECT_OVERVIEW.md             # This comprehensive handoff document
```

---

## 5. Automated Verification & Test Results (32 Tests)

```bash
rootdir: C:\Projects\cueclear
collected 32 items

tests/test_agent.py::test_split_reconciler_valid PASSED                  [  3%]
tests/test_agent.py::test_split_reconciler_invalid PASSED                [  6%]
tests/test_agent.py::test_gemini_extraction_case_a_explicit PASSED       [  9%]
tests/test_agent.py::test_gemini_extraction_case_b_undisclosed PASSED    [ 12%]
tests/test_agent.py::test_agent_orchestrator_end_to_end PASSED           [ 15%]
tests/test_api.py::test_health_route PASSED                              [ 18%]
tests/test_api.py::test_sample_timelines_route PASSED                    [ 21%]
tests/test_api.py::test_upload_and_clearance_lifecycle PASSED            [ 25%]
tests/test_api.py::test_frontend_static_serving PASSED                   [ 28%]
tests/test_domain_accuracy.py::test_case_a_confirmed_public_splits PASSED [ 31%]
tests/test_domain_accuracy.py::test_case_b_pro_registered_undisclosed_splits PASSED [ 34%]
tests/test_domain_accuracy.py::test_case_c_partial_publisher_claim PASSED [ 37%]
tests/test_domain_accuracy.py::test_overall_manifest_compliance_scoring_rigor PASSED [ 40%]
tests/test_exporters.py::test_excel_export PASSED                        [ 43%]
tests/test_exporters.py::test_cisac_xml_export PASSED                    [ 46%]
tests/test_live_services.py::test_live_parallel_api_connection PASSED    [ 50%]
tests/test_live_services.py::test_live_gemini_api_connection SKIPPED     [ 53%]
tests/test_live_services.py::test_live_end_to_end_agent_pipeline PASSED  [ 56%]
tests/test_parallel.py::test_clean_music_search_terms PASSED             [ 59%]
tests/test_parallel.py::test_parallel_search_known_commercial_tracks PASSED [ 62%]
tests/test_parallel.py::test_parallel_search_film_score PASSED           [ 65%]
tests/test_parallel.py::test_parallel_search_custom_library_cue PASSED   [ 68%]
tests/test_parallel.py::test_parallel_exponential_backoff_and_retry PASSED [ 71%]
tests/test_parser.py::test_timecode_math PASSED                          [ 75%]
tests/test_parser.py::test_edl_parser_with_sample PASSED                 [ 78%]
tests/test_parser.py::test_xml_parser_with_sample PASSED                 [ 81%]
tests/test_parser.py::test_edl_parser_video_filtering PASSED             [ 84%]
tests/test_parser.py::test_xml_parser_stereo_deduplication PASSED        [ 87%]
tests/test_stress_audit.py::test_scenario_1_arbitrary_and_noisy_timeline_ingestion PASSED [ 90%]
tests/test_stress_audit.py::test_scenario_2_stream_fault_isolation_and_rate_limit_retries PASSED [ 93%]
tests/test_stress_audit.py::test_scenario_3_domain_split_precision_cases PASSED [ 96%]
tests/test_stress_audit.py::test_scenario_4_export_deliverable_resilience_mixed_manifest PASSED [100%]

============ 31 passed, 1 skipped, 2 warnings in 230.09s (0:03:50) ============
```

---

## 6. How to Run & Experience the App

```powershell
# 1. Navigate to project root
cd C:\Projects\cueclear

# 2. Start the FastAPI development server
C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser at **`http://127.0.0.1:8000`**.

---

## 7. Hackathon 3-Minute Demo Video Script

* **0:00 – 0:30 (The Problem):** Show an unorganized Premiere/DaVinci timeline with multiple music tracks. Explain that generating cue sheets requires days of manual database searches, risking unrepresented publisher splits and copyright rejection.
* **0:30 – 0:50 (The Ingest):** Open the CueClear Studio Console. Drag and drop `sample_trailer.edl`. Show the detected audio cues.
* **0:50 – 1:40 (ADK Agent in Action):** Click **Run rights clearance**. Point to the live terminal: ADK invokes `parallel_pro_search_tool` (Parallel Search ID + Extract ID) → Gemini grounds writers/publishers from Parallel text → ADK invokes `audit_and_reconcile_splits_tool` for dual-sided 100% checks.
* **1:40 – 2:20 (The Audit Modal & 3-Tier Classification):** Click on *Midnight City (M83)* (Emerald 100% Cleared) vs *Exit Music (Radiohead)* (Amber Pending Sign-Off) to demonstrate the industry-accurate 3-tier split model.
* **2:20 – 3:00 (The Export):** Click **"⬇ Export Cue Sheet"** $\rightarrow$ open the downloaded **Excel (`.xlsx`)** workbook and **CISAC XML** file to prove delivery readiness.
