import pytest
import asyncio
import os
from unittest.mock import patch, MagicMock
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
