import math
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from ..models.schemas import ResolvedCue, RightsHolder, CueSheetManifest, SplitStatus

def validate_splits(cue: ResolvedCue) -> Tuple[bool, List[str]]:
    """
    Mathematically audits composition and publishing shares using strict 3-tier classification:
    
    - Tier 1 (Case A - CONFIRMED_PUBLIC_SPLIT):
      Explicit percentage literals exist in PRO registers.
      Verified ONLY if sum(writers) == 100.0% AND sum(publishers) == 100.0%. (100% Cleared)
      
    - Tier 2 (Case B - PRO_REGISTERED_SPLIT_UNDISCLOSED):
      Writers/Publishers registered with PRO, but royalty split numbers are confidential/undisclosed.
      Assigns share: None, computes informational equal split estimate, flags as PENDING SIGN-OFF. (0% Cleared)
      
    - Tier 3 (Case C - PARTIAL_PUBLISHER_CLAIM_FLAGGED):
      Publisher shares sum to < 100% (e.g. 75% claimed, 25% unrepresented/black-box).
      Flags unrepresented publisher share. (0% Cleared)
    """
    flags: List[str] = []

    # Check for In-House Sound Design
    if "sound design" in (cue.artist or "").lower() or "sfx" in cue.title.lower():
        cue.split_status = SplitStatus.IN_HOUSE_SOUND_DESIGN
        cue.total_writer_share = 100.0
        cue.total_publisher_share = 100.0
        cue.is_verified = True
        cue.flagged_issues = []
        return True, []

    # Check if rights holders exist
    if not cue.writers:
        flags.append("No registered songwriters/composers found in PRO database.")
        cue.split_status = SplitStatus.UNREGISTERED_WORK_FLAGGED
        cue.is_verified = False
        cue.flagged_issues = flags
        return False, flags

    # Check for Undisclosed Splits (Case B)
    has_undisclosed_writer = any(w.share is None for w in cue.writers)
    has_undisclosed_publisher = any(p.share is None for p in cue.publishers)

    if has_undisclosed_writer or has_undisclosed_publisher:
        cue.split_status = SplitStatus.PRO_REGISTERED_SPLIT_UNDISCLOSED
        count = len(cue.writers) if cue.writers else 1
        cue.estimated_equal_share = round(100.0 / count, 2)
        cue.total_writer_share = 0.0
        cue.total_publisher_share = 0.0
        flags.append(
            f"PRO registration confirmed ({len(cue.writers)} writers, {len(cue.publishers)} publishers), "
            f"but exact percentage splits are undisclosed in public registry. "
            f"Estimated equal split: {cue.estimated_equal_share}% each. Requires Music Supervisor sign-off."
        )
        cue.is_verified = False
        cue.flagged_issues = flags
        return False, flags

    # Calculate actual numeric sums
    writer_sum = sum(w.share for w in cue.writers if w.share is not None)
    pub_sum = sum(p.share for p in cue.publishers if p.share is not None)
    
    cue.total_writer_share = round(writer_sum, 2)
    cue.total_publisher_share = round(pub_sum, 2)

    # Check Writer parity (100.0%)
    if not math.isclose(writer_sum, 100.0, abs_tol=0.05):
        flags.append(f"Writer split sums to {writer_sum:.1f}% (Expected 100.0%)")

    # Check Publisher parity (100.0%)
    if not math.isclose(pub_sum, 100.0, abs_tol=0.05):
        if pub_sum < 99.95:
            cue.split_status = SplitStatus.PARTIAL_PUBLISHER_CLAIM_FLAGGED
            flags.append(
                f"Incomplete publisher claim: Only {pub_sum:.1f}% claimed "
                f"({round(100.0 - pub_sum, 1):.1f}% open/unadministered). Risk of copyright claim."
            )
        else:
            flags.append(f"Publisher split sums to {pub_sum:.1f}% (Expected 100.0%)")

    # Check for missing PRO details
    for w in cue.writers:
        if not w.pro or w.pro == "OTHER":
            flags.append(f"Missing PRO affiliation for writer: {w.name}")

    for p in cue.publishers:
        if not p.pro or p.pro == "OTHER":
            flags.append(f"Missing PRO affiliation for publisher: {p.name}")

    is_verified = (len(flags) == 0)
    if is_verified:
        cue.split_status = SplitStatus.CONFIRMED_PUBLIC_SPLIT

    cue.is_verified = is_verified
    cue.flagged_issues = flags
    
    return is_verified, flags

def apply_supervisor_sign_off(
    cue: ResolvedCue,
    signed_off_by: str = "Music Supervisor",
) -> ResolvedCue:
    """
    Human-in-the-loop clearance for Case B/C cues.
    Assigns equal shares only where shares were undisclosed, stamps audit metadata,
    and marks the cue verified for delivery exports.
    """
    if cue.writers:
        missing_writer_shares = any(w.share is None for w in cue.writers)
        if missing_writer_shares:
            split = round(100.0 / len(cue.writers), 2)
            for w in cue.writers:
                if w.share is None:
                    w.share = split
            # Fix rounding drift on last writer
            writer_sum = sum(w.share or 0.0 for w in cue.writers)
            if cue.writers and not math.isclose(writer_sum, 100.0, abs_tol=0.05):
                cue.writers[-1].share = round((cue.writers[-1].share or 0.0) + (100.0 - writer_sum), 2)

    if cue.publishers:
        missing_pub_shares = any(p.share is None for p in cue.publishers)
        if missing_pub_shares:
            split = round(100.0 / len(cue.publishers), 2)
            for p in cue.publishers:
                if p.share is None:
                    p.share = split
            pub_sum = sum(p.share or 0.0 for p in cue.publishers)
            if cue.publishers and not math.isclose(pub_sum, 100.0, abs_tol=0.05):
                cue.publishers[-1].share = round((cue.publishers[-1].share or 0.0) + (100.0 - pub_sum), 2)

    cue.total_writer_share = round(sum(w.share or 0.0 for w in cue.writers), 2)
    cue.total_publisher_share = round(sum(p.share or 0.0 for p in cue.publishers), 2)
    cue.split_status = SplitStatus.CONFIRMED_PUBLIC_SPLIT
    cue.is_verified = True
    cue.flagged_issues = []
    cue.supervisor_signed_off = True
    cue.signed_off_by = signed_off_by
    cue.signed_off_at = datetime.now(timezone.utc).isoformat()
    return cue


def compute_manifest_compliance(cues: List[ResolvedCue], project_title: str = "Project") -> CueSheetManifest:
    """
    Computes honest compliance metrics:
    Only cues with 100% verified writer AND 100% verified publisher shares count in the numerator.
    Undisclosed (Case B) and Partial (Case C) cues count as 0%.
    """
    total = len(cues)
    cleared = sum(1 for c in cues if c.is_verified)
    flagged = total - cleared
    
    score = (cleared / total * 100.0) if total > 0 else 100.0

    return CueSheetManifest(
        project_title=project_title,
        cues=cues,
        total_cues=total,
        cleared_cues=cleared,
        flagged_cues=flagged,
        compliance_score=round(score, 1)
    )
