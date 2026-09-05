import pytest
import asyncio
import os
from unittest.mock import patch, MagicMock, AsyncMock
from backend.models.schemas import ResolvedCue, RightsHolder, UsageType, SplitStatus, ExtractedPROData
from backend.agent.split_reconciler import validate_splits, compute_manifest_compliance
from backend.agent.adk_orchestrator import CueClearADKOrchestrator as CueClearAgent
from backend.agent.gemini_orchestrator import extract_pro_rights_with_gemini
from backend.parsers.edl_parser import EDLParser

def test_split_reconciler_valid():
    cue = ResolvedCue(
        cue_number=1,
        title="Midnight City",
        artist="M83",
        usage_type=UsageType.BI,
        timecode_in="00:00:05:00",
        timecode_out="00:01:31:12",
        duration_frames=2076,
        duration_timecode="00:01:26:12",
        writers=[
            RightsHolder(name="Anthony Gonzalez", share=50.0, pro="SACEM"),
            RightsHolder(name="Morgan Kibby", share=25.0, pro="BMI"),
            RightsHolder(name="Yann Gonzalez", share=25.0, pro="SACEM")
        ],
        publishers=[
            RightsHolder(name="Delphic Music", share=50.0, pro="ASCAP"),
            RightsHolder(name="Universal Music", share=50.0, pro="BMI")
        ]
    )
    is_verified, flags = validate_splits(cue)
    assert is_verified is True
    assert len(flags) == 0
    assert cue.total_writer_share == 100.0
    assert cue.total_publisher_share == 100.0

def test_split_reconciler_invalid():
    cue = ResolvedCue(
        cue_number=2,
        title="Incomplete Song",
        usage_type=UsageType.BI,
        timecode_in="00:00:00:00",
        timecode_out="00:01:00:00",
        duration_frames=1440,
        duration_timecode="00:01:00:00",
        writers=[
            RightsHolder(name="Composer A", share=40.0, pro="ASCAP")  # Sums to 40%, not 100%
        ],
        publishers=[
            RightsHolder(name="Publisher A", share=100.0, pro="BMI")
        ]
    )
    is_verified, flags = validate_splits(cue)
    assert is_verified is False
    assert len(flags) >= 1
    assert "Writer split sums to 40.0%" in flags[0]

@pytest.mark.asyncio
async def test_gemini_extraction_case_a_explicit():
    """Case A: Verifies that explicit percentage tokens in excerpts produce float shares."""
    sample_excerpts = [
        "ASCAP Repertory Work #883581734: MIDNIGHT CITY (ISWC T-909.123.456-7)",
        "Writers: Anthony Gonzalez (50% SACEM), Morgan Kibby (25% BMI), Yann Gonzalez (25% SACEM)",
        "Publishers: Delphic Music (50% ASCAP), Universal Music (50% BMI)"
    ]
    extracted = await extract_pro_rights_with_gemini("Midnight City", "M83", sample_excerpts)
    assert isinstance(extracted, ExtractedPROData)
    assert len(extracted.writers) == 3
    assert extracted.writers[0].share == 50.0
    assert extracted.writers[1].share == 25.0
    assert extracted.publishers[0].share == 50.0

@pytest.mark.asyncio
async def test_gemini_extraction_case_b_undisclosed():
    """Case B: Verifies that multi-writer registrations without published percentages return share=None."""
    sample_excerpts = [
        "BMI Songview Work #4819203: EXIT MUSIC FOR A FILM (ISWC T-010.456.789-0)",
        "5 Songwriters Registered with BMI: Yorke, Greenwood, Greenwood, O'Brien, Selway.",
        "Public Royalty Split Percentages Undisclosed.",
        "Publisher: Warner Chappell Music Ltd (BMI)"
    ]
    extracted = await extract_pro_rights_with_gemini("Exit Music (For A Film)", "Radiohead", sample_excerpts)
    assert isinstance(extracted, ExtractedPROData)
    assert len(extracted.writers) == 5
    # All writer shares should be None (undisclosed)
    for w in extracted.writers:
        assert w.share is None

    # Test that split_reconciler catches this and assigns PRO_REGISTERED_SPLIT_UNDISCLOSED
    cue = ResolvedCue(
        cue_number=1, title="Exit Music", usage_type=UsageType.BI,
        timecode_in="00:00:00:00", timecode_out="00:01:00:00", duration_frames=1440, duration_timecode="00:01:00:00",
        writers=extracted.writers, publishers=extracted.publishers
    )
    is_verified, flags = validate_splits(cue)
    assert is_verified is False
    assert cue.split_status == SplitStatus.PRO_REGISTERED_SPLIT_UNDISCLOSED
    assert cue.estimated_equal_share == 20.0

@pytest.mark.asyncio
async def test_agent_orchestrator_end_to_end():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "samples", "sample_trailer.edl")
    with open(sample_path, "r", encoding="utf-8") as f:
        edl_content = f.read()

    parser = EDLParser(default_fps=24.0)
    clips = parser.parse(edl_content)

    agent = CueClearAgent()
    events = []
    async for event in agent.process_timeline_stream(clips, "Test Trailer"):
        events.append(event)

    assert len(events) > 0
    assert events[0].event_type == "start"
    assert events[-1].event_type == "complete"

    manifest = await agent.process_timeline(clips, "Test Trailer")
    assert manifest.total_cues == 5
    assert manifest.cleared_cues >= 2
    assert manifest.compliance_score >= 40.0
    
    # Assert Midnight City resolved properly
    m83_cue = manifest.cues[1]
    assert "Midnight City" in m83_cue.title
    assert len(m83_cue.writers) >= 1
    assert m83_cue.total_writer_share >= 0.0


@pytest.mark.asyncio
async def test_adk_uses_fresh_session_per_cue():
    """
    Regression: reusing one ADK session across cues caused Gemini to skip
    parallel_pro_search_tool after cue 1 (direct_tool_fallback on cues 2+).
    Fresh per-cue sessions must keep invoke_mode=adk_runner for every music cue.
    """
    from backend.models.schemas import ParsedAudioClip

    clips = [
        ParsedAudioClip(
            event_number=1, track_type="A1", clip_name="M83 - Midnight City.wav",
            source_in="00:00:00:00", source_out="00:00:40:00",
            record_in="00:00:00:00", record_out="00:00:40:00",
            duration_frames=960, duration_timecode="00:00:40:00",
        ),
        ParsedAudioClip(
            event_number=2, track_type="A1", clip_name="Radiohead - Exit Music For A Film.wav",
            source_in="00:00:00:00", source_out="00:00:35:00",
            record_in="00:00:40:00", record_out="00:01:15:00",
            duration_frames=840, duration_timecode="00:00:35:00",
        ),
        ParsedAudioClip(
            event_number=3, track_type="A1", clip_name="Unknown Indie Needle Drop 07_final.wav",
            source_in="00:00:00:00", source_out="00:00:28:00",
            record_in="00:01:15:00", record_out="00:01:43:00",
            duration_frames=672, duration_timecode="00:00:28:00",
        ),
    ]

    class _FR:
        def __init__(self, name, response):
            self.name = name
            self.response = response

    class _Part:
        def __init__(self, fr):
            self.function_response = fr

    class _Content:
        def __init__(self, parts):
            self.parts = parts

    class _Event:
        def __init__(self, content):
            self.content = content

    created_session_ids = []
    run_session_ids = []
    call_count = {"n": 0}

    async def fake_search(track_title: str, artist: str = ""):
        call_count["n"] += 1
        return {
            "status": "success",
            "source": "Mock Parallel",
            "source_type": "LIVE_PARALLEL_API",
            "search_id": f"search_mock_{call_count['n']}",
            "extract_id": f"extract_mock_{call_count['n']}",
            "extracted_urls": ["https://www.ascap.com/repertory"],
            "latency_ms": 12.0,
            "is_live_hit": True,
            "provenance": "LIVE_PARALLEL_SEARCH_AND_EXTRACT",
            "title": track_title,
            "artist": artist or "Various Artists",
            "work_id": None,
            "iswc": None,
            "writers": [],
            "publishers": [],
            "excerpts": [f"Mock PRO excerpt for {track_title}"],
            "source_citation": "Mock Parallel",
        }

    agent = CueClearAgent()
    agent.has_gemini = True

    original_create = agent.session_service.create_session

    async def tracking_create_session(**kwargs):
        session = await original_create(**kwargs)
        created_session_ids.append(session.id)
        return session

    async def fake_run_async(*, user_id, session_id, new_message):
        from backend.agent.adk_orchestrator import audit_and_reconcile_splits_tool

        run_session_ids.append(session_id)
        text = ""
        if new_message and new_message.parts:
            text = getattr(new_message.parts[0], "text", "") or ""

        if "audit_and_reconcile_splits_tool" in text:
            writers_json = "[]"
            publishers_json = "[]"
            for line in text.splitlines():
                if line.startswith("writers_json="):
                    writers_json = line.split("=", 1)[1]
                elif line.startswith("publishers_json="):
                    publishers_json = line.split("=", 1)[1]
            payload = audit_and_reconcile_splits_tool(writers_json, publishers_json)
            yield _Event(_Content([_Part(_FR("audit_and_reconcile_splits_tool", payload))]))
            return

        title = "Unknown"
        for line in text.splitlines():
            if line.startswith("track_title="):
                title = line.split("=", 1)[1].strip().strip('"')
                break
        payload = await fake_search(title, "")
        yield _Event(_Content([_Part(_FR("parallel_pro_search_tool", payload))]))

    assert len(list(agent.agent.tools)) == 2

    with patch.object(agent.session_service, "create_session", side_effect=tracking_create_session):
        with patch.object(agent.runner, "run_async", side_effect=fake_run_async):
            with patch(
                "backend.agent.adk_orchestrator.parallel_pro_search_tool",
                side_effect=fake_search,
            ):
                with patch(
                    "backend.agent.adk_orchestrator.extract_pro_rights_with_gemini",
                    new=AsyncMock(
                        return_value=ExtractedPROData(
                            work_id=None,
                            iswc=None,
                            writers=[],
                            publishers=[],
                            confidence_notes="test",
                        )
                    ),
                ):
                    events = []
                    async for event in agent.process_timeline_stream(clips, "ADK Session Isolation"):
                        events.append(event)

    music_results = [
        e for e in events
        if e.event_type == "parallel_result" and e.data and e.data.get("invoke_mode")
    ]
    assert len(music_results) == 3
    assert all(e.data.get("invoke_mode") == "adk_runner" for e in music_results)

    audit_results = [
        e for e in events
        if e.event_type == "reconciliation"
        and e.data
        and e.data.get("audit_invoke_mode") == "adk_runner"
    ]
    assert len(audit_results) == 3
    assert not any("[ADK_FALLBACK]" in (e.message or "") for e in events)

    # Parent clearance session + one search session and one audit session per music cue
    cue_sessions = [s for s in created_session_ids if "-cue-" in s]
    audit_sessions = [s for s in created_session_ids if "-audit-" in s]
    assert len(cue_sessions) == 3
    assert len(audit_sessions) == 3
    assert len(set(cue_sessions)) == 3
    assert len(set(audit_sessions)) == 3
    # Prefetch can interleave search/audit session order across cues.
    assert len(run_session_ids) == 6
    assert set(run_session_ids) == set(cue_sessions + audit_sessions)

    complete = events[-1]
    assert complete.event_type == "complete"
    for cue in (complete.data or {}).get("cues") or []:
        assert cue.get("invoke_mode") == "adk_runner"
        assert cue.get("audit_invoke_mode") == "adk_runner"
