import os
import pytest
import asyncio
from dotenv import load_dotenv

# Force load .env from project root
load_dotenv(override=True)

PARALLEL_API_KEY = os.getenv("PARALLEL_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

@pytest.mark.asyncio
async def test_live_parallel_api_connection():
    """Live Parallel Search via official parallel-web AsyncParallel SDK."""
    assert PARALLEL_API_KEY, "PARALLEL_API_KEY is not set in .env"
    assert not PARALLEL_API_KEY.startswith("your_"), "PARALLEL_API_KEY is still placeholder"

    from parallel import AsyncParallel

    async with AsyncParallel(api_key=PARALLEL_API_KEY, timeout=20.0) as client:
        result = await client.search(
            objective="Find official ASCAP or BMI Work ID and songwriters for track 'Midnight City' by 'M83'",
            search_queries=[
                "ASCAP repertory Midnight City M83",
                "BMI Songview Midnight City M83",
            ],
            mode="fast",
        )

    print(f"\n[Parallel Live Test] search_id={result.search_id}")
    print(f"[Parallel Live Test] results={len(result.results)}")
    assert result.search_id
    assert result.results is not None

@pytest.mark.asyncio
async def test_live_gemini_api_connection():
    """Direct live network test to Gemini / Google GenAI using real GEMINI_API_KEY."""
    assert GEMINI_API_KEY, "GEMINI_API_KEY is not set in .env"
    assert not GEMINI_API_KEY.startswith("your_"), "GEMINI_API_KEY is still placeholder"

    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents="Respond with 'GEMINI_LIVE_OK' and one sentence describing an audio cue sheet."
        )
        print(f"\n[Gemini Live Test] Response: {response.text}")
        assert response.text is not None and len(response.text) > 0
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            pytest.skip(f"Gemini free tier quota exhausted temporarily: {e}")
        raise e

@pytest.mark.asyncio
async def test_live_end_to_end_agent_pipeline():
    """End-to-end agent run with live API credentials."""
    from backend.parsers.edl_parser import EDLParser
    from backend.agent.gemini_orchestrator import CueClearAgent

    sample_path = os.path.join(os.path.dirname(__file__), "..", "samples", "sample_trailer.edl")
    with open(sample_path, "r", encoding="utf-8") as f:
        edl_text = f.read()

    parser = EDLParser(default_fps=24.0)
    clips = parser.parse(edl_text)

    agent = CueClearAgent()
    manifest = await agent.process_timeline(clips, "Live Verified Trailer")
    
    assert manifest.total_cues == 5
    assert manifest.cleared_cues >= 2
    assert manifest.compliance_score >= 40.0
    print(f"\n[Agent Live Pipeline] Successfully processed {manifest.total_cues} cues: {manifest.cleared_cues} Cleared, {manifest.flagged_cues} Flagged (Score: {manifest.compliance_score}%)")
