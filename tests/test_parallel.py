import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from parallel import RateLimitError
from backend.agent.parallel_tool import search_pro_music_rights, clean_music_search_terms

def test_clean_music_search_terms():
    """Verifies that messy timeline audio clip names are cleanly normalized."""
    # Test messy versioned filename with feat and remix
    title, artist = clean_music_search_terms("01_Midnight_City_v2 (feat. Morgan) [Remix].wav", "M83")
    assert "Midnight City" in title
    assert "wav" not in title.lower()
    assert "v2" not in title.lower()
    assert "Remix" not in title
    assert "M83" in artist or "Morgan" in artist

    # Test underscore and dash stripping
    title2, artist2 = clean_music_search_terms("Hans_Zimmer_-_Time_FINAL_MASTER.mp3", "Hans Zimmer")
    assert title2 == "Hans Zimmer Time"

@pytest.mark.asyncio
async def test_parallel_search_known_commercial_tracks():
    """Offline catalog path for known demo tracks (no live key)."""
    with patch("backend.agent.parallel_tool.PARALLEL_API_KEY", ""):
        res_m83 = await search_pro_music_rights("M83 - Midnight City", "M83")
    assert res_m83["status"] == "success"
    assert res_m83["title"] == "Midnight City"
    assert "ASCAP" in res_m83["work_id"]
    assert len(res_m83["writers"]) == 3
    assert res_m83["provenance"] == "OFFLINE_CATALOG_FALLBACK"
    
    # Assert raw excerpts are captured
    assert "excerpts" in res_m83
    assert isinstance(res_m83["excerpts"], list)
    assert len(res_m83["excerpts"]) > 0
    assert any("ASCAP" in exc or "MIDNIGHT" in exc.upper() for exc in res_m83["excerpts"])

    # Assert latency & metadata
    assert "latency_ms" in res_m83
    assert "search_id" in res_m83
    assert "source_type" in res_m83

@pytest.mark.asyncio
async def test_parallel_search_film_score():
    with patch("backend.agent.parallel_tool.PARALLEL_API_KEY", ""):
        res_zimmer = await search_pro_music_rights("Hans Zimmer - Time", "Hans Zimmer")
    assert res_zimmer["status"] == "success"
    assert "Hans Florian Zimmer" in res_zimmer["writers"][0]["name"]
    assert res_zimmer["writers"][0]["share"] == 100.0
    assert "Warner-Barham" in res_zimmer["publishers"][0]["name"]
    assert len(res_zimmer["excerpts"]) > 0
    assert res_zimmer["provenance"] == "OFFLINE_CATALOG_FALLBACK"

@pytest.mark.asyncio
async def test_parallel_search_custom_library_cue():
    """Unknown cues must not invent Work IDs or cleared 100% shares."""
    with patch("backend.agent.parallel_tool.PARALLEL_API_KEY", ""):
        res_custom = await search_pro_music_rights("Action Chase Percussion Drone 02", "Trailer FX")
    assert res_custom["status"] == "success"
    assert res_custom.get("writers") == []
    assert res_custom.get("publishers") == []
    assert res_custom.get("work_id") is None
    assert res_custom.get("iswc") is None
    assert res_custom.get("resolution") in (
        "UNREGISTERED_OR_UNVERIFIED",
        "NEEDS_GEMINI_GROUNDING",
        "NEEDS_EXTRACTION",
    )
    assert res_custom.get("provenance") in (
        "OFFLINE_UNRESOLVED",
        "LIVE_PARALLEL_SEARCH_ONLY",
        "LIVE_PARALLEL_SEARCH_AND_EXTRACT",
    )
    assert len(res_custom["excerpts"]) > 0
    assert "excerpts" in res_custom

@pytest.mark.asyncio
async def test_parallel_exponential_backoff_and_retry():
    """Simulates Parallel SDK RateLimitError followed by Search + Extract success."""
    success_result = MagicMock()
    success_result.search_id = "search_retry_success_123"
    success_hit = MagicMock()
    success_hit.excerpts = ["ASCAP Repertory: Live Extracted Split 100%"]
    success_hit.url = "https://www.ascap.com/repertory#ace/search/workID/123"
    success_result.results = [success_hit]

    extract_result = MagicMock()
    extract_result.extract_id = "extract_retry_456"
    extract_hit = MagicMock()
    extract_hit.excerpts = ["Writers: Test Composer (100%)"]
    extract_hit.full_content = "ASCAP full page content with writer shares."
    extract_hit.url = success_hit.url
    extract_result.results = [extract_hit]

    mock_client = AsyncMock()
    mock_client.search = AsyncMock(
        side_effect=[
            RateLimitError("rate limited", response=MagicMock(status_code=429), body=None),
            success_result,
        ]
    )
    mock_client.extract = AsyncMock(return_value=extract_result)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("parallel.AsyncParallel", return_value=mock_client):
        with patch("backend.agent.parallel_tool.PARALLEL_API_KEY", "test_key_live_123"):
            res = await search_pro_music_rights("Dynamic Test Song", "Test Artist", max_retries=3)
            assert res["status"] == "success"
            assert mock_client.search.call_count == 2
            assert mock_client.extract.call_count == 1
            assert res["search_id"] == "search_retry_success_123"
            assert res["extract_id"] == "extract_retry_456"
            assert res["provenance"] == "LIVE_PARALLEL_SEARCH_AND_EXTRACT"
            assert len(res["excerpts"]) > 0
            assert res.get("writers") == []
            assert res.get("work_id") is None
            assert "ascap.com" in (res.get("extracted_urls") or [""])[0]
