import os
import json
import asyncio
from datetime import datetime, timezone
from typing import List, AsyncGenerator, Dict, Any, Optional

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ..models.schemas import (
    ParsedAudioClip,
    ResolvedCue,
    RightsHolder,
    UsageType,
    CueSheetManifest,
    AgentEvent,
    SplitStatus,
)
from .parallel_tool import search_pro_music_rights
from .split_reconciler import validate_splits, compute_manifest_compliance
from .gemini_orchestrator import extract_pro_rights_with_gemini

load_dotenv()

# Define First-Class ADK Tools
async def parallel_pro_search_tool(track_title: str, artist: str = "") -> dict:
    """
    Queries Parallel Search API across ASCAP Repertory, BMI Songview, and MusicBrainz.
    Returns official Work ID, ISWC, and raw extracted writer/publisher registers.
    """
    return await search_pro_music_rights(track_title, artist)

def audit_and_reconcile_splits_tool(writers_json: str, publishers_json: str) -> dict:
    """
    Audits composition and publishing shares.
    Enforces strict dual-sided 100% check:
    - Writer shares MUST sum to 100.0%
    - Publisher shares MUST sum to 100.0%
    - If splits are undisclosed in public PRO text, flags cue as PENDING_LEGAL_SIGN_OFF (0% cleared).
    """
    try:
        writers = json.loads(writers_json) if isinstance(writers_json, str) else writers_json
        publishers = json.loads(publishers_json) if isinstance(publishers_json, str) else publishers_json
    except Exception as e:
        return {"is_verified": False, "flags": [f"Invalid split payload: {e}"], "total_writer": 0.0, "total_publisher": 0.0}

    cue = ResolvedCue(
        cue_number=1,
        title="Audit Target",
        usage_type=UsageType.BI,
        timecode_in="00:00:00:00",
        timecode_out="00:00:00:00",
        duration_frames=0,
        duration_timecode="00:00:00:00",
        writers=[RightsHolder(**w) for w in writers],
        publishers=[RightsHolder(**p) for p in publishers]
    )
    is_verified, flags = validate_splits(cue)
    return {
        "is_verified": is_verified,
        "total_writer_share": cue.total_writer_share,
        "total_publisher_share": cue.total_publisher_share,
        "flagged_issues": flags
    }

class CueClearADKOrchestrator:
    """
    Hybrid clearance orchestrator:
    - Google ADK Runner actually invokes Parallel Search as a tool per music cue
    - Gemini structured extraction and dual-sided split audit remain deterministic
    """
    def __init__(self):
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.has_gemini = bool(gemini_key and not gemini_key.startswith("your_"))
        if self.has_gemini and not os.getenv("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = gemini_key

        self.session_service = InMemorySessionService()
        self.adk_active = self.has_gemini

        # ADK agent owns Parallel Search tool-calling. Extract + audit stay explicit.
        # Prefer 3.6-flash, then aliases that remain available when free-tier quotas trip.
        env_model = os.getenv("CUECLEAR_ADK_MODEL", "").strip()
        self.adk_model_candidates: List[str] = []
        if env_model:
            self.adk_model_candidates.append(env_model)
        for model_name in ("gemini-3.6-flash", "gemini-flash-latest", "gemini-3-flash-preview"):
            if model_name not in self.adk_model_candidates:
                self.adk_model_candidates.append(model_name)
        self.adk_model = self.adk_model_candidates[0]
        self._adk_instruction = (
            "You are CueClear's PRO search agent on Google ADK. "
            "Each user message is an independent music cue with a fresh session. "
            "Always call parallel_pro_search_tool exactly once for the current cue "
            "with the provided track_title and artist. "
            "Do not invent Work IDs, writers, publishers, or ownership shares. "
            "After the tool returns, briefly confirm that search completed."
        )
        self._build_adk_runner(self.adk_model)

    def _build_adk_runner(self, model_name: str) -> None:
        self.adk_model = model_name
        self.agent = Agent(
            name="cueclear_adk_agent",
            model=model_name,
            instruction=self._adk_instruction,
            tools=[parallel_pro_search_tool],
        )
        self.runner = Runner(
            agent=self.agent,
            app_name="cueclear_studio",
            session_service=self.session_service,
        )

    def _rotate_adk_model(self, err: Exception) -> bool:
        """Advance to the next ADK model candidate after 404/429/503. Returns True if rotated."""
        err_l = str(err).lower()
        retriable = (
            "404" in err_l
            or "not found" in err_l
            or "no longer available" in err_l
            or "429" in err_l
            or "resource_exhausted" in err_l
            or "503" in err_l
            or "unavailable" in err_l
            or "high demand" in err_l
        )
        if not retriable:
            return False
        try:
            idx = self.adk_model_candidates.index(self.adk_model)
        except ValueError:
            idx = 0
        if idx + 1 >= len(self.adk_model_candidates):
            return False
        next_model = self.adk_model_candidates[idx + 1]
        self._build_adk_runner(next_model)
        return True

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

    async def _invoke_parallel_via_adk(
        self,
        track_title: str,
        artist: str,
        clearance_session_id: str,
        cue_number: int,
    ) -> tuple[Dict[str, Any], str, Optional[str]]:
        """
        Prefer ADK Runner tool-calling for Parallel Search.
        Uses a fresh ADK session per cue so prior tool history cannot suppress
        subsequent parallel_pro_search_tool calls.
        Fall back to direct tool invocation if ADK/Gemini is unavailable or fails.
        Returns (result, invoke_mode, fallback_reason).
        """
        if not self.has_gemini:
            result = await parallel_pro_search_tool(track_title, artist)
            return result, "direct_tool_fallback", "Gemini API key unavailable; ADK Runner skipped"

        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=(
                        f"Cue #{cue_number:02d} is a new independent search. "
                        "Call parallel_pro_search_tool exactly once NOW for this cue only.\n"
                        f'track_title="{track_title}"\n'
                        f'artist="{artist or ""}"\n'
                        "Do not invent Work IDs or ownership shares."
                    )
                )
            ],
        )

        last_err: Optional[Exception] = None
        rotated_from: Optional[str] = None
        for attempt in range(len(self.adk_model_candidates)):
            cue_session_id = (
                f"{clearance_session_id}-cue-{cue_number:03d}"
                if attempt == 0
                else f"{clearance_session_id}-cue-{cue_number:03d}-m{attempt}"
            )
            cue_session = await self.session_service.create_session(
                app_name="cueclear_studio",
                user_id="post_supervisor_1",
                session_id=cue_session_id,
            )
            try:
                tool_payload: Optional[Dict[str, Any]] = None
                async for event in self.runner.run_async(
                    user_id="post_supervisor_1",
                    session_id=cue_session.id,
                    new_message=message,
                ):
                    if not event.content or not event.content.parts:
                        continue
                    for part in event.content.parts:
                        fr = getattr(part, "function_response", None)
                        if fr is None or fr.name != "parallel_pro_search_tool":
                            continue
                        response = fr.response
                        if isinstance(response, dict):
                            tool_payload = response
                        elif response is not None:
                            tool_payload = dict(response)

                if tool_payload and tool_payload.get("status") == "success":
                    if rotated_from:
                        tool_payload = {
                            **tool_payload,
                            "adk_model": self.adk_model,
                            "adk_model_rotated_from": rotated_from,
                        }
                    else:
                        tool_payload = {**tool_payload, "adk_model": self.adk_model}
                    return tool_payload, "adk_runner", None

                result = await parallel_pro_search_tool(track_title, artist)
                return (
                    result,
                    "direct_tool_fallback",
                    "ADK Runner completed without a Parallel tool response; used direct Parallel Search",
                )
            except Exception as adk_err:
                last_err = adk_err
                previous = self.adk_model
                if self._rotate_adk_model(adk_err):
                    rotated_from = previous
                    continue
                break
            finally:
                try:
                    await self.session_service.delete_session(
                        app_name="cueclear_studio",
                        user_id="post_supervisor_1",
                        session_id=cue_session.id,
                    )
                except Exception:
                    pass

        result = await parallel_pro_search_tool(track_title, artist)
        if last_err is not None:
            err_name = type(last_err).__name__
            err_text = " ".join(str(last_err).split())[:160]
            reason = f"ADK Runner error ({err_name}: {err_text}); used direct Parallel Search"
        else:
            reason = "ADK Runner unavailable; used direct Parallel Search"
        return result, "direct_tool_fallback", reason

    async def process_timeline_stream(
        self,
        clips: List[ParsedAudioClip],
        project_title: str = "Production Sequence"
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Clears a timeline: ADK tool-calls Parallel Search per cue, then deterministic
        Gemini extraction and split reconciliation, streaming progress events.
        """
        session = await self.session_service.create_session(
            app_name="cueclear_studio",
            user_id="post_supervisor_1"
        )

        yield AgentEvent(
            event_type="start",
            timestamp=self._now(),
            message=(
                f"[ADK_INIT] Clearance {session.id[:8]} ready. "
                f"ADK model={self.adk_model}; fresh tool session per cue"
                f"{'' if self.has_gemini else ' (Gemini unavailable: direct tool fallback)'}. "
                f"Ingested {len(clips)} timeline clips."
            ),
            data={
                "total_clips": len(clips),
                "project": project_title,
                "session_id": session.id,
                "adk_tool_calling": self.has_gemini,
                "adk_session_policy": "per_cue",
                "adk_model": self.adk_model,
            },
        )

        # Pre-plan work items so we can overlap next-cue ADK search with Gemini extract.
        planned: List[Dict[str, Any]] = []
        cue_number = 1
        for clip in clips:
            raw_title, raw_artist, usage = self._clean_track_name(clip.clip_name)
            is_sfx = any(
                k in clip.clip_name.lower()
                for k in ["sfx", "ident", "subboom", "impact", "foley", "roomtone"]
            )
            planned.append({
                "clip": clip,
                "cue_number": cue_number,
                "raw_title": raw_title,
                "raw_artist": raw_artist,
                "usage": usage,
                "is_sfx": is_sfx,
            })
            cue_number += 1

        music_indices = [i for i, item in enumerate(planned) if not item["is_sfx"]]
        prefetch_task: Optional[asyncio.Task] = None
        prefetch_index: Optional[int] = None

        def _start_adk_search(item: Dict[str, Any]) -> asyncio.Task:
            return asyncio.create_task(
                self._invoke_parallel_via_adk(
                    item["raw_title"],
                    item["raw_artist"],
                    session.id,
                    item["cue_number"],
                )
            )

        resolved_cues: List[ResolvedCue] = []
        for idx, item in enumerate(planned):
            clip = item["clip"]
            cue_number = item["cue_number"]
            raw_title = item["raw_title"]
            raw_artist = item["raw_artist"]
            usage = item["usage"]
            try:
                if item["is_sfx"]:
                    yield AgentEvent(
                        event_type="reasoning",
                        timestamp=self._now(),
                        message=f"[ADK_IDENT] Identified sound design event '{clip.clip_name}'. Cataloging as Production Sound FX.",
                        cue_number=cue_number,
                        data={"clip": clip.clip_name, "type": "SFX"}
                    )

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
                        message=f"[CLEARED] Cue #{cue_number:02d}: '{cue.title}' (100% In-House FX)",
                        cue_number=cue_number,
                        data=cue.model_dump()
                    )
                    continue

                # Step 1: Parallel PRO Search via ADK Runner tool-calling
                prefetched = prefetch_task is not None and prefetch_index == idx
                yield AgentEvent(
                    event_type="parallel_query",
                    timestamp=self._now(),
                    message=(
                        f"[ADK_TOOL] {'Resuming prefetched' if prefetched else 'Invoking'} "
                        f"parallel_pro_search_tool for '{raw_title}' "
                        f"(Artist: {raw_artist or 'N/A'})..."
                    ),
                    cue_number=cue_number,
                    data={"prefetched": prefetched},
                )

                if prefetched and prefetch_task is not None:
                    pro_result, invoke_mode, fallback_reason = await prefetch_task
                    prefetch_task = None
                    prefetch_index = None
                else:
                    if prefetch_task is not None:
                        prefetch_task.cancel()
                        try:
                            await prefetch_task
                        except (asyncio.CancelledError, Exception):
                            pass
                        prefetch_task = None
                        prefetch_index = None
                    pro_result, invoke_mode, fallback_reason = await self._invoke_parallel_via_adk(
                        raw_title,
                        raw_artist,
                        session.id,
                        cue_number,
                    )

                if invoke_mode != "adk_runner" and fallback_reason:
                    yield AgentEvent(
                        event_type="reasoning",
                        timestamp=self._now(),
                        message=f"[ADK_FALLBACK] {fallback_reason}.",
                        cue_number=cue_number,
                        data={"invoke_mode": invoke_mode, "fallback_reason": fallback_reason},
                    )

                is_live_hit = bool(pro_result.get("is_live_hit")) or ("Live" in str(pro_result.get("source", "")))
                source_tag = "LIVE_PARALLEL_HIT" if is_live_hit else "CACHED_REFERENCE_ARCHIVE"
                work_id_display = pro_result.get("work_id") or "pending Gemini extract"
                provenance = pro_result.get("provenance") or (
                    "LIVE_PARALLEL_SEARCH" if is_live_hit else "OFFLINE_CATALOG_OR_UNRESOLVED"
                )

                yield AgentEvent(
                    event_type="parallel_result",
                    timestamp=self._now(),
                    message=(
                        f"[PARALLEL_HIT] [{source_tag}] via {invoke_mode}: "
                        f"provenance={provenance}; Work ID '{work_id_display}' "
                        f"({len(pro_result.get('excerpts', []))} excerpts, "
                        f"search_id={str(pro_result.get('search_id'))[:12]}, "
                        f"extract_id={str(pro_result.get('extract_id') or '—')[:12]})"
                    ),
                    cue_number=cue_number,
                    data={
                        **pro_result,
                        "invoke_mode": invoke_mode,
                        "fallback_reason": fallback_reason,
                        "provenance": provenance,
                    },
                )

                extract_id = pro_result.get("extract_id")
                extracted_urls = pro_result.get("extracted_urls") or []
                if extract_id or extracted_urls:
                    yield AgentEvent(
                        event_type="reasoning",
                        timestamp=self._now(),
                        message=(
                            f"[PARALLEL_EXTRACT] Grounded {len(extracted_urls)} PRO/source URL(s)"
                            + (f" (extract_id={str(extract_id)[:12]})" if extract_id else "")
                            + "."
                        ),
                        cue_number=cue_number,
                        data={
                            "extract_id": extract_id,
                            "extracted_urls": extracted_urls,
                            "provenance": provenance,
                        },
                    )

                # Overlap next cue's ADK+Parallel search with this cue's Gemini extract + audit.
                try:
                    pos = music_indices.index(idx)
                    if pos + 1 < len(music_indices):
                        next_idx = music_indices[pos + 1]
                        next_item = planned[next_idx]
                        prefetch_task = _start_adk_search(next_item)
                        prefetch_index = next_idx
                        yield AgentEvent(
                            event_type="reasoning",
                            timestamp=self._now(),
                            message=(
                                f"[ADK_PREFETCH] Started Parallel search for cue "
                                f"#{next_item['cue_number']:02d} '{next_item['raw_title']}' "
                                "while Gemini grounds the current cue."
                            ),
                            cue_number=cue_number,
                            data={
                                "prefetch_cue_number": next_item["cue_number"],
                                "prefetch_title": next_item["raw_title"],
                            },
                        )
                except ValueError:
                    pass

                # Step 2: Deterministic Gemini structured extraction from Parallel Search+Extract text
                grounding_excerpts = [
                    str(x)[:1500] for x in (pro_result.get("excerpts") or [])[:8]
                ]
                yield AgentEvent(
                    event_type="reasoning",
                    timestamp=self._now(),
                    message=(
                        f"[GEMINI_EXTRACT] Grounding rights holders from "
                        f"{len(grounding_excerpts)} Parallel Search/Extract excerpts..."
                    ),
                    cue_number=cue_number,
                )

                extracted = await extract_pro_rights_with_gemini(
                    raw_title,
                    raw_artist,
                    grounding_excerpts,
                )

                # Step 3: Deterministic dual-sided split audit
                yield AgentEvent(
                    event_type="reconciliation",
                    timestamp=self._now(),
                    message="[SPLIT_AUDIT] Verifying dual-sided 100% writer & publisher split parity...",
                    cue_number=cue_number,
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
                    is_live_hit=pro_result.get("is_live_hit", True),
                    invoke_mode=invoke_mode,
                    provenance=provenance,
                    excerpts=list(pro_result.get("excerpts") or [])[:12],
                    extract_id=extract_id,
                    extracted_urls=list(extracted_urls)[:5],
                    confidence_notes=extracted.confidence_notes,
                    fallback_reason=fallback_reason,
                )

                is_verified, flags = validate_splits(cue)
                resolved_cues.append(cue)

                if is_verified:
                    yield AgentEvent(
                        event_type="cue_verified",
                        timestamp=self._now(),
                        message=f"[CLEARED] Cue #{cue_number:02d}: '{cue.title}' -> 100% Confirmed Splits.",
                        cue_number=cue_number,
                        data=cue.model_dump()
                    )
                else:
                    w_count = len(cue.writers)
                    p_count = len(cue.publishers)
                    share_est = cue.estimated_equal_share if cue.estimated_equal_share is not None else 0.0
                    if cue.split_status == SplitStatus.PRO_REGISTERED_SPLIT_UNDISCLOSED:
                        action_msg = f"[ACTION_REQUIRED] Cue #{cue_number:02d}: PRO registration confirmed ({w_count} writers, {p_count} publishers), but exact percentage splits are undisclosed in public registry. Estimated equal split: {share_est:.1f}% each. Requires Music Supervisor sign-off."
                    else:
                        action_msg = f"[ACTION_REQUIRED] Cue #{cue_number:02d}: {', '.join(flags)}"

                    yield AgentEvent(
                        event_type="cue_flagged",
                        timestamp=self._now(),
                        message=action_msg,
                        cue_number=cue_number,
                        data=cue.model_dump()
                    )

            except Exception as cue_err:
                if prefetch_task is not None:
                    prefetch_task.cancel()
                    try:
                        await prefetch_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    prefetch_task = None
                    prefetch_index = None
                yield AgentEvent(
                    event_type="reasoning",
                    timestamp=self._now(),
                    message=f"[WARNING] Notice: Isolated exception on cue #{cue_number} ({clip.clip_name}): {cue_err}. Fallback catalog applied.",
                    cue_number=cue_number
                )
                fallback_cue = ResolvedCue(
                    cue_number=cue_number,
                    title=clip.clip_name,
                    artist="Unknown / Library",
                    usage_type=UsageType.BI,
                    timecode_in=clip.record_in,
                    timecode_out=clip.record_out,
                    duration_frames=clip.duration_frames,
                    duration_timecode=clip.duration_timecode,
                    fps=clip.fps,
                    work_id=f"FALLBACK-{cue_number:03d}",
                    iswc="N/A",
                    writers=[RightsHolder(name="Unresolved Writer", role="Composer", pro="ASCAP", share=None)],
                    publishers=[RightsHolder(name="Unresolved Publisher", role="Publisher", pro="BMI", share=None)],
                    source_reference=f"Fault Isolation: {cue_err}",
                    raw_clip_name=clip.clip_name,
                    source_type="LOCAL_PRO_CATALOG_FALLBACK",
                    is_live_hit=False
                )
                validate_splits(fallback_cue)
                resolved_cues.append(fallback_cue)
                yield AgentEvent(
                    event_type="cue_flagged",
                    timestamp=self._now(),
                    message=f"[ACTION_REQUIRED] Cue #{cue_number:02d}: Unresolved cue flagged for supervisor review.",
                    cue_number=cue_number,
                    data=fallback_cue.model_dump()
                )

        if prefetch_task is not None:
            prefetch_task.cancel()
            try:
                await prefetch_task
            except (asyncio.CancelledError, Exception):
                pass

        manifest = compute_manifest_compliance(resolved_cues, project_title)

        yield AgentEvent(
            event_type="complete",
            timestamp=self._now(),
            message=(
                f"[CLEARANCE_COMPLETE] {manifest.cleared_cues}/{manifest.total_cues} cues cleared "
                f"({manifest.compliance_score}% verified compliance). "
                "Pipeline: ADK Parallel tool-call → Gemini extract → split audit."
            ),
            data=manifest.model_dump(),
        )

    def _clean_track_name(self, raw_name: str) -> tuple:
        import re
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
