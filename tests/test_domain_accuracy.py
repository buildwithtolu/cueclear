import pytest
from backend.models.schemas import ResolvedCue, RightsHolder, UsageType, SplitStatus
from backend.agent.split_reconciler import validate_splits, compute_manifest_compliance, apply_supervisor_sign_off
from backend.agent.parallel_tool import search_pro_music_rights

def test_case_a_confirmed_public_splits():
    """
    Case A: Public documentation explicitly provides writer & publisher percentages.
    Target: M83 - Midnight City.
    Expected: is_verified = True, split_status = CONFIRMED_PUBLIC_SPLIT, counts 100% toward compliance.
    """
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
    assert cue.split_status == SplitStatus.CONFIRMED_PUBLIC_SPLIT
    assert len(flags) == 0
    assert cue.total_writer_share == 100.0
    assert cue.total_publisher_share == 100.0

def test_case_b_pro_registered_undisclosed_splits():
    """
    Case B: Song is registered with PRO (BMI/PRS), but public databases do not publish royalty splits.
    Target: Radiohead - Exit Music (For A Film) [5 registered writers: Yorke, Greenwood x2, O'Brien, Selway].
    Expected: is_verified = False, split_status = PRO_REGISTERED_SPLIT_UNDISCLOSED,
              estimated_equal_share = 20.0, counts as 0% toward compliance.
    """
    cue = ResolvedCue(
        cue_number=2,
        title="Exit Music (For A Film)",
        artist="Radiohead",
        usage_type=UsageType.ET,
        timecode_in="00:01:35:00",
        timecode_out="00:03:00:00",
        duration_frames=2040,
        duration_timecode="00:01:25:00",
        writers=[
            RightsHolder(name="Thomas Edward Yorke", share=None, pro="BMI"),
            RightsHolder(name="Jonathan Richard Guy Greenwood", share=None, pro="BMI"),
            RightsHolder(name="Colin Charles Greenwood", share=None, pro="BMI"),
            RightsHolder(name="Edward John O'Brien", share=None, pro="BMI"),
            RightsHolder(name="Philip James Selway", share=None, pro="BMI")
        ],
        publishers=[
            RightsHolder(name="Warner Chappell Music Ltd", share=None, pro="BMI")
        ]
    )
    is_verified, flags = validate_splits(cue)
    assert is_verified is False
    assert cue.split_status == SplitStatus.PRO_REGISTERED_SPLIT_UNDISCLOSED
    assert cue.estimated_equal_share == 20.0  # 100% / 5 writers = 20%
    assert len(flags) == 1
    assert "exact percentage splits are undisclosed" in flags[0]
    assert "Requires Music Supervisor sign-off" in flags[0]

def test_case_c_partial_publisher_claim():
    """
    Case C: Writers are 100% confirmed, but only 75% of publishing is claimed (25% unadministered/black-box).
    Expected: is_verified = False, split_status = PARTIAL_PUBLISHER_CLAIM_FLAGGED, counts as 0% toward compliance.
    """
    cue = ResolvedCue(
        cue_number=3,
        title="Independent Co-Write",
        artist="Indie Artist",
        usage_type=UsageType.BI,
        timecode_in="00:03:05:00",
        timecode_out="00:04:00:00",
        duration_frames=1320,
        duration_timecode="00:00:55:00",
        writers=[
            RightsHolder(name="Writer A", share=50.0, pro="ASCAP"),
            RightsHolder(name="Writer B", share=50.0, pro="BMI")
        ],
        publishers=[
            RightsHolder(name="Publisher A (Admin)", share=75.0, pro="ASCAP")  # Missing 25%
        ]
    )
    is_verified, flags = validate_splits(cue)
    assert is_verified is False
    assert cue.split_status == SplitStatus.PARTIAL_PUBLISHER_CLAIM_FLAGGED
    assert len(flags) >= 1
    assert "Incomplete publisher claim: Only 75.0% claimed (25.0% open/unadministered)" in flags[0]

def test_overall_manifest_compliance_scoring_rigor():
    """
    Verifies that undisclosed (Case B) and partial (Case C) cues NEVER get backfilled into the compliance numerator.
    In a 3-cue timeline:
    - Cue 1: Cleared (Case A)
    - Cue 2: Undisclosed (Case B)
    - Cue 3: Partial (Case C)
    Expected Compliance Score: 33.3% (1 / 3).
    """
    cues = [
        ResolvedCue(
            cue_number=1, title="Track 1", usage_type=UsageType.BI,
            timecode_in="00:00:00:00", timecode_out="00:01:00:00", duration_frames=1440, duration_timecode="00:01:00:00",
            writers=[RightsHolder(name="W1", share=100.0, pro="ASCAP")],
            publishers=[RightsHolder(name="P1", share=100.0, pro="BMI")]
        ),
        ResolvedCue(
            cue_number=2, title="Track 2", usage_type=UsageType.BI,
            timecode_in="00:01:00:00", timecode_out="00:02:00:00", duration_frames=1440, duration_timecode="00:01:00:00",
            writers=[RightsHolder(name="W2", share=None, pro="BMI"), RightsHolder(name="W3", share=None, pro="BMI")],
            publishers=[RightsHolder(name="P2", share=None, pro="BMI")]
        ),
        ResolvedCue(
            cue_number=3, title="Track 3", usage_type=UsageType.BI,
            timecode_in="00:02:00:00", timecode_out="00:03:00:00", duration_frames=1440, duration_timecode="00:01:00:00",
            writers=[RightsHolder(name="W4", share=100.0, pro="ASCAP")],
            publishers=[RightsHolder(name="P3", share=60.0, pro="ASCAP")]
        )
    ]

    for c in cues:
        validate_splits(c)

    manifest = compute_manifest_compliance(cues, "Indie Feature Lock")
    assert manifest.total_cues == 3
    assert manifest.cleared_cues == 1
    assert manifest.flagged_cues == 2
    assert manifest.compliance_score == 33.3  # Exactly 1 / 3 = 33.3%


def test_supervisor_sign_off_assigns_equal_shares_and_clears_case_b():
    cue = ResolvedCue(
        cue_number=2,
        title="Exit Music",
        artist="Radiohead",
        usage_type=UsageType.BI,
        timecode_in="00:00:00:00",
        timecode_out="00:01:00:00",
        duration_frames=1440,
        duration_timecode="00:01:00:00",
        writers=[
            RightsHolder(name="Yorke", share=None, pro="BMI"),
            RightsHolder(name="Greenwood", share=None, pro="BMI"),
        ],
        publishers=[
            RightsHolder(name="Warner Chappell", share=None, pro="BMI"),
        ],
    )
    validate_splits(cue)
    assert cue.split_status == SplitStatus.PRO_REGISTERED_SPLIT_UNDISCLOSED
    assert cue.is_verified is False

    apply_supervisor_sign_off(cue, signed_off_by="Music Supervisor")
    assert cue.supervisor_signed_off is True
    assert cue.is_verified is True
    assert cue.split_status == SplitStatus.CONFIRMED_PUBLIC_SPLIT
    assert cue.signed_off_by == "Music Supervisor"
    assert cue.signed_off_at
    assert cue.total_writer_share == 100.0
    assert cue.total_publisher_share == 100.0
    assert all(w.share is not None for w in cue.writers)
    assert all(p.share is not None for p in cue.publishers)
