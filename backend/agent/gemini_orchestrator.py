import os
import re
import json
import asyncio
from datetime import datetime, timezone
from typing import List, AsyncGenerator, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

from ..models.schemas import (
    ParsedAudioClip,
    ResolvedCue,
    RightsHolder,
    UsageType,
    CueSheetManifest,
    AgentEvent,
    ExtractedPROData
)
from .parallel_tool import search_pro_music_rights, KNOWN_PRO_CATALOG
from .split_reconciler import validate_splits, compute_manifest_compliance

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

async def extract_pro_rights_with_gemini(
    track_title: str,
    artist: str,
    excerpts: List[str]
) -> ExtractedPROData:
    """
    Uses Google Cloud Gemini with structured output extraction to extract
    grounded PRO rights metadata, official Work ID, ISWC, and writer/publisher shares
    strictly from raw web excerpts returned by Parallel AI.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    has_gemini = bool(api_key and not api_key.startswith("your_"))
    
    if has_gemini and excerpts:
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=api_key)
            prompt = (
                f"You are a music rights clearance expert in film & TV post-production.\n"
                f"Target Track: '{track_title}' by '{artist}'\n\n"
                f"Here are raw web search excerpts retrieved from ASCAP Repertory, BMI Songview, and PRO databases:\n"
                f"{json.dumps(excerpts, indent=2)}\n\n"
                f"STRICT EXTRACTION INSTRUCTIONS:\n"
                f"1. Extract the official Work ID (e.g. ASCAP-..., BMI-..., PRS-...) and ISWC (e.g. T-...) if present in the text.\n"
                f"2. Extract all Songwriters / Composers: full name, PRO affiliation (ASCAP, BMI, SESAC, PRS, SACEM, SIAE, GEMA, SOCAN), and IPI number.\n"
                f"3. Extract all Publishers: full name, PRO affiliation, and IPI number.\n"
                f"4. ROYALTY SPLIT GROUNDING RULE:\n"
                f"   - If numeric percentage shares are explicitly published in the text (e.g. '50%', '25%'), set 'share' to that float number.\n"
                f"   - If multiple writers/publishers are registered in the text but explicit percentage splits are NOT published, set 'share' to null (None). DO NOT invent or assume equal splits.\n"
                f"   - If a single writer/in-house composer exists with 100% ownership stated, set 'share: 100.0'.\n"
                f"5. Write a brief 'confidence_notes' explaining whether splits were explicitly cited or undisclosed in the text."
            )
            
            # Prefer current Gemini Flash; keep prior id as fallback
            for model_name in ["gemini-3.6-flash", "gemini-2.5-flash"]:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=ExtractedPROData,
                            temperature=0.0
                        )
                    )
                    if response.text:
                        data_dict = json.loads(response.text)
                        return ExtractedPROData(**data_dict)
                except Exception as model_err:
                    if "404" in str(model_err) or "not found" in str(model_err).lower():
                        continue
                    raise model_err
        except Exception:
            # Fallback to local catalog on API exception
            pass

    # Offline / Heuristic Fallback
    clean_key = re.sub(r"[^\w\s]", "", track_title).upper().strip()
    for key, data in KNOWN_PRO_CATALOG.items():
        if key in clean_key or clean_key in key:
            return ExtractedPROData(
                work_id=data.get("work_id"),
                iswc=data.get("iswc"),
                writers=[RightsHolder(**w) for w in data.get("writers", [])],
                publishers=[RightsHolder(**p) for p in data.get("publishers", [])],
                confidence_notes=f"Catalog Reference: {data.get('source_citation')}"
            )
            
    # No catalog match and no usable Gemini extraction: leave rights empty for reconciler flagging
    return ExtractedPROData(
        work_id=None,
        iswc=None,
        writers=[],
        publishers=[],
        confidence_notes=(
            f"No grounded PRO rights holders found for '{track_title}'"
            + (f" by '{artist}'" if artist else "")
            + ". Flag for Music Supervisor review."
        ),
    )

class CueClearAgent:
    """
    Autonomous Post-Production Music Rights Clearance Agent.
    Powered by Gemini Structured Outputs and Parallel AI Search Engine.
    """
    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.has_gemini = bool(self.api_key and not self.api_key.startswith("your_"))

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

    def _clean_track_name(self, raw_name: str) -> Tuple[str, str, UsageType]:
        clean = re.sub(r"\.(wav|mp3|aiff|m4a|flac)$", "", raw_name, flags=re.IGNORECASE).strip()
        usage = UsageType.BI
        lower = clean.lower()
        if "theme" in lower or "main title" in lower:
            usage = UsageType.MT
        elif "end credit" in lower or "outro" in lower:
            usage = UsageType.ET
        elif "vocal" in lower or "song" in lower:
            usage = UsageType.BV

        if " - " in clean:
            parts = clean.split(" - ", 1)
            return parts[1].strip(), parts[0].strip(), usage
        return clean, "", usage

    async def process_timeline_stream(
        self, 
        clips: List[ParsedAudioClip], 
        project_title: str = "Project Reel"
    ) -> AsyncGenerator[AgentEvent, None]:
        yield AgentEvent(
            event_type="start",
            timestamp=self._now(),
            message=f"🎬 Initialized CueClear Agent. Ingested {len(clips)} audio timeline clips.",
            data={"total_clips": len(clips), "project": project_title}
        )
        await asyncio.sleep(0.1)

        resolved_cues: List[ResolvedCue] = []
        cue_number = 1

        for clip in clips:
            raw_title, raw_artist, usage = self._clean_track_name(clip.clip_name)
            is_sfx = any(k in clip.clip_name.lower() for k in ["sfx", "ident", "subboom", "impact", "foley", "roomtone"])

            if is_sfx:
                cue = ResolvedCue(
                    cue_number=cue_number,
                    title=clip.clip_name,
                    artist="In-House Sound Design",
                    usage_type=UsageType.BI,
                    timecode_in=clip.record_in,
                    timecode_out=clip.record_out,
                    duration_frames=clip.duration_frames,
                    duration_timecode=clip.duration_timecode,
                    fps=clip.fps,
                    work_id=f"SFX-{cue_number:03d}",
                    iswc="N/A (Sound Design)",
                    writers=[RightsHolder(name="Sound Design Dept", role="Sound Designer", pro="ASCAP", share=100.0)],
                    publishers=[RightsHolder(name="Production House Library", role="Publisher", pro="ASCAP", share=100.0)],
                    source_reference="In-House Sound Library",
                    raw_clip_name=clip.clip_name
                )
                validate_splits(cue)
                resolved_cues.append(cue)

                yield AgentEvent(
                    event_type="cue_verified",
                    timestamp=self._now(),
                    message=f"✅ Cleared Cue #{cue_number:02d}: '{cue.title}' (100% In-House FX)",
                    cue_number=cue_number,
                    data=cue.model_dump()
                )
                cue_number += 1
                continue

            # Query Parallel Tool
            yield AgentEvent(
                event_type="parallel_query",
                timestamp=self._now(),
                message=f"🌐 Querying Parallel Search API for '{raw_title}' (Artist: {raw_artist or 'N/A'})...",
                cue_number=cue_number
            )
            await asyncio.sleep(0.1)

            pro_result = await search_pro_music_rights(raw_title, raw_artist)
            
            # Grounded Gemini Extraction from Parallel Excerpts
            yield AgentEvent(
                event_type="reasoning",
                timestamp=self._now(),
                message=f"🧠 Gemini Structured Extractor: Ingesting {len(pro_result.get('excerpts', []))} raw PRO excerpts to ground rights holders and verify split publication...",
                cue_number=cue_number
            )
            await asyncio.sleep(0.1)

            extracted = await extract_pro_rights_with_gemini(
                raw_title,
                raw_artist,
                pro_result.get("excerpts", [])
            )

            cue = ResolvedCue(
                cue_number=cue_number,
                title=raw_title,
                artist=raw_artist or "Various Artists",
                usage_type=usage,
                timecode_in=clip.record_in,
                timecode_out=clip.record_out,
                duration_frames=clip.duration_frames,
                duration_timecode=clip.duration_timecode,
                fps=clip.fps,
                iswc=extracted.iswc or pro_result.get("iswc"),
                work_id=extracted.work_id or pro_result.get("work_id"),
                writers=extracted.writers,
                publishers=extracted.publishers,
                source_reference=extracted.confidence_notes or pro_result.get("source_citation"),
                raw_clip_name=clip.clip_name,
                source_type=pro_result.get("source_type", "LIVE_PARALLEL_API"),
                search_id=pro_result.get("search_id"),
                latency_ms=pro_result.get("latency_ms"),
                is_live_hit=pro_result.get("is_live_hit", True)
            )

            is_verified, flags = validate_splits(cue)
            resolved_cues.append(cue)

            if is_verified:
                yield AgentEvent(
                    event_type="cue_verified",
                    timestamp=self._now(),
                    message=f"✅ Cleared Cue #{cue_number:02d}: '{cue.title}' -> 100% Confirmed Splits.",
                    cue_number=cue_number,
                    data=cue.model_dump()
                )
            else:
                yield AgentEvent(
                    event_type="cue_flagged",
                    timestamp=self._now(),
                    message=f"⚠️ Action Required Cue #{cue_number:02d}: {', '.join(flags)}",
                    cue_number=cue_number,
                    data=cue.model_dump()
                )

            cue_number += 1

        manifest = compute_manifest_compliance(resolved_cues, project_title)

        yield AgentEvent(
            event_type="complete",
            timestamp=self._now(),
            message=f"🏆 Clearance Completed. {manifest.cleared_cues}/{manifest.total_cues} Cues Cleared ({manifest.compliance_score}% Verified Compliance).",
            data=manifest.model_dump()
        )

    async def process_timeline(
        self,
        clips: List[ParsedAudioClip],
        project_title: str = "Production Sequence"
    ) -> CueSheetManifest:
        final_manifest = None
        async for event in self.process_timeline_stream(clips, project_title):
            if event.event_type == "complete" and event.data:
                final_manifest = CueSheetManifest(**event.data)
        return final_manifest or compute_manifest_compliance([], project_title)
