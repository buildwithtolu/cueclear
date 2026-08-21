# 🎬 CueClear — Autonomous Music Rights Clearance & Cue Sheet Agent

> **Built for the Google Cloud "Agentic Cinema" Summer Blockbuster Hackathon**  
> **Track:** Parallel Partner Track  
> **Core Technologies:** Google ADK (`google-adk`) + Gemini + Parallel Search (`parallel-web`) + FastAPI + Python 3.11+

---

## 🌟 Overview

**CueClear** solves one of the most universally dreaded bottlenecks in film, TV, and commercial post-production: **manual music cue sheets and rights clearance spreadsheets**.

When an edit is locked, assistant editors and music supervisors spend days scrubbing timelines to find song titles, manually searching PRO databases (ASCAP Repertory, BMI Songview, PRS, SESAC), cross-referencing composer splits and publisher ownership percentages, and formatting compliant delivery spreadsheets.

**CueClear completely automates this workflow:**
1. **Ingests** standard NLE timeline exports (`.edl` CMX 3600, Premiere/FCP `.xml`) across standard industry framerates (23.976p, 24p, 25p PAL, 29.97 NDF/DF).
2. **Orchestrates** Parallel PRO discovery through **Google ADK Runner tool-calling** (`google-adk`), then grounds rights with Gemini structured extraction.
3. **Queries and deep-reads** PRO / web sources using the official **`parallel-web`** SDK (`AsyncParallel.search` + `AsyncParallel.extract`), returning Search IDs, Extract IDs, and grounded page excerpts for Gemini.
4. **Reconciles Splits Dual-Sidedly** enforcing that writer shares sum to 100.0% AND publisher shares sum to 100.0%. Any undisclosed split is flagged as `PENDING_LEGAL_CONFIRMATION` (0% compliance).
5. **Exports Certified Delivery Assets**: Broadcast-standard Excel (`.xlsx`), CISAC Audio-Visual Cue XML (`.xml`), and raw clearance manifests (`.json`).

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│              Cinematic Studio Web Console                │
│    (Timeline Dropzone | Real-time Trace | Master Grid)    │
└────────────────────────────┬─────────────────────────────┘
                             │
                    (HTTP / SSE Stream)
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│              CueClear FastAPI Gateway Engine             │
│   • CMX 3600 & FCPXML Timeline Parsers                   │
│   • Timecode Math Engine (23.976 / 24 / 25 / 29.97 FPS)  │
└──────────────┬────────────────────────────┬──────────────┘
               │                            │
               ▼                            ▼
┌──────────────────────────────┐ ┌───────────────────────────┐
│     Google Cloud ADK Agent   │ │ Parallel Search + Extract │
│  (google-adk, Gemini)        │ │ (ASCAP, BMI, MusicBrainz) │
│ • ADK tool-call for Search   │ │ • Search IDs + Extract IDs│
│ • Dual-sided split audit     │ │ • Page excerpts for Gemini│
└──────────────┬───────────────┘ └──────────┬────────────────┘
               │                            │
               └─────────────┬──────────────┘
                             ▼
┌──────────────────────────────────────────────────────────┐
│                 Broadcast Format Exporters               │
│   • PMA / Network Standard Excel Workbook (.xlsx)        │
│   • CISAC Audio-Visual Cue Sheet XML (.xml)              │
│   • Audit-Ready Clearance Manifest (.json)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.11+ or Python 3.13
- Pip or npm

### 2. Clone & Install
```bash
# TODO: replace with your real public repo URL before submission
git clone https://github.com/<YOUR_GITHUB_USERNAME>/cueclear.git
cd cueclear

# Create virtual environment (optional)
python -m venv venv
source venv/bin/activate  # Or on Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment
Copy `.env.example` to `.env` (strictly gitignored):
```bash
cp .env.example .env
```
Fill in your live API keys:
```env
GEMINI_API_KEY=your_gemini_api_key
PARALLEL_API_KEY=your_parallel_api_key
```

### 4. Run the Studio Server
```bash
# Using npm:
npm run dev

# Or using Python directly:
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **`http://127.0.0.1:8000`** in your browser.

---

## 🧪 Automated Test Suite

Run the full automated test suite:
```bash
pytest
```

Run dedicated live network integration tests against Parallel & Gemini:
```bash
pytest tests/test_live_services.py -s
```

---

## 🎬 3-Minute Live Demo Script

1. **The Problem (0:00 - 0:30):** Show why locked-picture cue sheets fail without verified writer/publisher splits (distribution delay + royalty risk).
2. **The Ingestion (0:30 - 0:50):** Load **Reel 03: Mixed Clearance** (`sample_mixed_clearance.edl`) so judges see Case A, Case B, and a non-catalog cue in one pass.
3. **Agent in Action (0:50 - 1:40):** Click Resolve Timeline Rights. Point to ADK invoking Parallel Search, Parallel Extract on PRO URLs, Gemini grounding, then split audit. Call out Search ID + Extract ID in the terminal.
4. **Interactive Audit (1:40 - 2:20):** Inspect Midnight City (cleared or grounded), Exit Music (pending sign-off), and the unknown needle-drop (unresolved / live-extracted). Open the audit modal and show provenance, excerpts, and IDs. Sign off the Case B cue.
5. **One-Click Export (2:20 - 3:00):** Export Excel + CISAC. Confirm supervisor-signed cues show `CLEARED (SUPERVISOR SIGN-OFF)` and unresolved cues remain action-required.

---

## 📄 License

This project is open-sourced under the [MIT License](LICENSE).
