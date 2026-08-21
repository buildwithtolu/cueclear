import os
import re
import json
import time
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from .models.schemas import (
    ParsedAudioClip,
    CueSheetManifest,
    AgentEvent,
)
from .parsers.edl_parser import EDLParser
from .parsers.xml_parser import XMLParser
from .agent.adk_orchestrator import CueClearADKOrchestrator as CueClearAgent
from .agent.split_reconciler import apply_supervisor_sign_off
from .exporters.excel_exporter import export_cue_sheet_to_excel
from .exporters.cisac_xml import export_cue_sheet_to_cisac_xml

# ---------------------------------------------------------------------------
# Public / local safety defaults
# ---------------------------------------------------------------------------
IS_PUBLIC = os.getenv("CUECLEAR_PUBLIC", "").strip().lower() in ("1", "true", "yes")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_CUES_PER_RUN = int(os.getenv("MAX_CUES_PER_RUN", "40"))
CLEARANCE_RATE_LIMIT = int(os.getenv("CLEARANCE_RATE_LIMIT", "5"))  # per window per IP
CLEARANCE_RATE_WINDOW_SEC = int(os.getenv("CLEARANCE_RATE_WINDOW_SEC", "60"))
SESSION_COOKIE = "cueclear_sid"
SESSION_TTL_SEC = int(os.getenv("SESSION_TTL_SEC", str(24 * 60 * 60)))

_DEFAULT_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]

app = FastAPI(
    title="CueClear API",
    description="Autonomous Post-Production Music Rights Clearance Agent",
    version="1.1.0",
    docs_url=None if IS_PUBLIC else "/docs",
    redoc_url=None if IS_PUBLIC else "/redoc",
    openapi_url=None if IS_PUBLIC else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

agent = CueClearAgent()


@dataclass
class SessionState:
    clips: List[ParsedAudioClip] = field(default_factory=list)
    manifest: Optional[CueSheetManifest] = None
    last_access: float = field(default_factory=time.time)


SESSIONS: Dict[str, SessionState] = {}
_RATE_BUCKETS: Dict[str, List[float]] = {}


class ClearanceRunRequest(BaseModel):
    project_title: str = "Production Sequence"
    clips: List[ParsedAudioClip]


class SignOffRequest(BaseModel):
    cue_number: int
    signed_off_by: str = Field(default="Music Supervisor", max_length=120)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    now = time.time()
    bucket = [t for t in _RATE_BUCKETS.get(ip, []) if now - t < CLEARANCE_RATE_WINDOW_SEC]
    if len(bucket) >= CLEARANCE_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many clearance requests. Please wait a minute and try again.",
        )
    bucket.append(now)
    _RATE_BUCKETS[ip] = bucket


def _purge_stale_sessions(now: Optional[float] = None) -> None:
    ts = now or time.time()
    stale = [sid for sid, state in SESSIONS.items() if ts - state.last_access > SESSION_TTL_SEC]
    for sid in stale:
        SESSIONS.pop(sid, None)


def _get_session(request: Request, response: Response) -> SessionState:
    _purge_stale_sessions()
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid or sid not in SESSIONS:
        sid = secrets.token_urlsafe(24)
        SESSIONS[sid] = SessionState()
        response.set_cookie(
            key=SESSION_COOKIE,
            value=sid,
            httponly=True,
            samesite="lax",
            secure=IS_PUBLIC,
            max_age=SESSION_TTL_SEC,
            path="/",
        )
    state = SESSIONS[sid]
    state.last_access = time.time()
    return state


def safe_filename_part(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (title or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return (cleaned[:80] or "Project")


@app.get("/api/health")
async def health_check():
    if IS_PUBLIC:
        return {"status": "healthy"}
    parallel_key = os.getenv("PARALLEL_API_KEY", "").strip()
    parallel_configured = bool(parallel_key and not parallel_key.startswith("your_"))
    return {
        "status": "healthy",
        "agent": "CueClear v1.1",
        "gemini_active": agent.has_gemini,
        "parallel_search_configured": parallel_configured,
        "parallel_integration": "search_and_extract",
        "public_mode": IS_PUBLIC,
    }


@app.get("/api/sample-timelines")
async def get_sample_timelines():
    samples_dir = os.path.join(os.path.dirname(__file__), "..", "samples")
    sample_files = [
        ("sample_trailer", "Neon Mirage (Trailer Master - CMX 3600 EDL)", "edl", "sample_trailer.edl"),
        ("sample_indie", "The Quiet Hours (Indie Short - FCP/Premiere XML)", "xml", "sample_indie_reel.xml"),
        (
            "sample_mixed",
            "Mixed Clearance Demo (Case A / Case B / Non-catalog)",
            "edl",
            "sample_mixed_clearance.edl",
        ),
    ]

    samples = []
    for sample_id, name, file_type, filename in sample_files:
        path = os.path.join(samples_dir, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                samples.append({
                    "id": sample_id,
                    "name": name,
                    "type": file_type,
                    "content": f.read(),
                })
    return samples


@app.post("/api/upload-timeline")
async def upload_timeline(
    request: Request,
    response: Response,
    file: Optional[UploadFile] = File(None),
    raw_content: Optional[str] = Form(None),
    file_type: Optional[str] = Form(None),
    project_title: Optional[str] = Form("Production Sequence"),
):
    session = _get_session(request, response)
    content = ""
    f_type = file_type or "edl"

    if file is not None:
        file_bytes = await file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Timeline file too large. Max size is {MAX_UPLOAD_BYTES} bytes.",
            )
        content = file_bytes.decode("utf-8", errors="ignore")
        if file.filename and file.filename.lower().endswith(".xml"):
            f_type = "xml"
        else:
            f_type = "edl"
    elif raw_content:
        if len(raw_content.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Timeline content too large. Max size is {MAX_UPLOAD_BYTES} bytes.",
            )
        content = raw_content

    if not content:
        raise HTTPException(status_code=400, detail="No timeline file or content provided.")

    if f_type.lower() == "xml":
        parser = XMLParser(default_fps=24.0)
        clips = parser.parse(content)
    else:
        parser = EDLParser(default_fps=24.0)
        clips = parser.parse(content)

    session.clips = clips
    session.manifest = None
    return {
        "status": "success",
        "project_title": project_title,
        "file_type": f_type,
        "total_clips": len(clips),
        "clips": [c.model_dump() for c in clips],
    }


@app.post("/api/run-clearance")
async def run_clearance(payload: ClearanceRunRequest, request: Request, response: Response):
    _enforce_rate_limit(request)
    session = _get_session(request, response)

    if len(payload.clips) > MAX_CUES_PER_RUN:
        raise HTTPException(
            status_code=400,
            detail=f"Too many cues in one run. Max is {MAX_CUES_PER_RUN}.",
        )

    session.clips = payload.clips
    manifest = await agent.process_timeline(payload.clips, payload.project_title)
    session.manifest = manifest
    return manifest.model_dump()


@app.get("/api/stream-clearance")
async def stream_clearance(
    request: Request,
    response: Response,
    project_title: str = "Production Sequence",
):
    """Server-Sent Events endpoint streaming live agent reasoning and Parallel tool actions."""
    _enforce_rate_limit(request)
    session = _get_session(request, response)

    if not session.clips:
        raise HTTPException(
            status_code=400,
            detail="No timeline loaded in this session. Upload or select a sample first.",
        )

    if len(session.clips) > MAX_CUES_PER_RUN:
        raise HTTPException(
            status_code=400,
            detail=f"Too many cues in one run. Max is {MAX_CUES_PER_RUN}.",
        )

    clips = list(session.clips)

    async def event_generator():
        async for agent_event in agent.process_timeline_stream(clips, project_title):
            if agent_event.event_type == "complete" and agent_event.data:
                session.manifest = CueSheetManifest(**agent_event.data)
            payload = json.dumps(agent_event.model_dump())
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/sign-off")
async def sign_off_cue(payload: SignOffRequest, request: Request, response: Response):
    """Persist Music Supervisor sign-off into this session's manifest used by exports."""
    session = _get_session(request, response)
    if not session.manifest:
        raise HTTPException(
            status_code=400,
            detail="No active cue sheet manifest. Run clearance before signing off.",
        )

    cue = next((c for c in session.manifest.cues if c.cue_number == payload.cue_number), None)
    if cue is None:
        raise HTTPException(status_code=404, detail=f"Cue #{payload.cue_number} not found in active manifest.")

    apply_supervisor_sign_off(cue, signed_off_by=payload.signed_off_by)

    total = len(session.manifest.cues)
    cleared = sum(1 for c in session.manifest.cues if c.is_verified)
    session.manifest.total_cues = total
    session.manifest.cleared_cues = cleared
    session.manifest.flagged_cues = total - cleared
    session.manifest.compliance_score = round((cleared / total * 100.0) if total else 100.0, 1)

    return session.manifest.model_dump()


@app.get("/api/export/excel")
async def export_excel(request: Request, response: Response):
    session = _get_session(request, response)
    if not session.manifest:
        raise HTTPException(status_code=400, detail="No active cue sheet manifest to export.")

    excel_bytes = export_cue_sheet_to_excel(session.manifest)
    filename = f"CueClear_{safe_filename_part(session.manifest.project_title)}_CueSheet.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/cisac-xml")
async def export_cisac(request: Request, response: Response):
    session = _get_session(request, response)
    if not session.manifest:
        raise HTTPException(status_code=400, detail="No active cue sheet manifest to export.")

    xml_content = export_cue_sheet_to_cisac_xml(session.manifest)
    filename = f"CueClear_{safe_filename_part(session.manifest.project_title)}_CISAC.xml"
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/json")
async def export_json(request: Request, response: Response):
    session = _get_session(request, response)
    if not session.manifest:
        raise HTTPException(status_code=400, detail="No active cue sheet manifest to export.")

    filename = f"CueClear_{safe_filename_part(session.manifest.project_title)}_Manifest.json"
    return JSONResponse(
        content=session.manifest.model_dump(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Static frontend mounting (after API routes)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
