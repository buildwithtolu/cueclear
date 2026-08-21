from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class UsageType(str, Enum):
    BI = "BI"  # Background Instrumental
    BV = "BV"  # Background Vocal
    VV = "VV"  # Visual Vocal (On-screen performance)
    VI = "VI"  # Visual Instrumental
    MT = "MT"  # Main Title Theme
    ET = "ET"  # End Title Theme

class PROAffiliation(str, Enum):
    ASCAP = "ASCAP"
    BMI = "BMI"
    SESAC = "SESAC"
    PRS = "PRS"
    GEMA = "GEMA"
    SACEM = "SACEM"
    SOCAN = "SOCAN"
    OTHER = "OTHER"

class SplitStatus(str, Enum):
    CONFIRMED_PUBLIC_SPLIT = "CONFIRMED_PUBLIC_SPLIT"                      # Case A: Explicit numbers in register
    PRO_REGISTERED_SPLIT_UNDISCLOSED = "PRO_REGISTERED_SPLIT_UNDISCLOSED"  # Case B: Multi-writer, shares confidential (0% compliance)
    PARTIAL_PUBLISHER_CLAIM_FLAGGED = "PARTIAL_PUBLISHER_CLAIM_FLAGGED"    # Case C: Publisher < 100% (0% compliance)
    IN_HOUSE_SOUND_DESIGN = "IN_HOUSE_SOUND_DESIGN"                        # Unmetered production SFX/Foley (100% Cleared)
    UNREGISTERED_WORK_FLAGGED = "UNREGISTERED_WORK_FLAGGED"                # No PRO record found (0% compliance)

class ParsedAudioClip(BaseModel):
    event_number: int
    track_type: str  # "A1", "A2", "A3", "V", "NONE"
    clip_name: str
    source_file: Optional[str] = None
    source_in: str
    source_out: str
    record_in: str
    record_out: str
    duration_frames: int
    duration_timecode: str
    fps: float = 24.0
    comments: List[str] = []

class RightsHolder(BaseModel):
    name: str
    role: str = "Composer"  # "Composer", "Author", "Publisher", "Administrator"
    pro: str = "ASCAP"  # "ASCAP", "BMI", "SESAC", etc.
    share: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    ipi_cae: Optional[str] = None

class ExtractedPROData(BaseModel):
    work_id: Optional[str] = None
    iswc: Optional[str] = None
    writers: List[RightsHolder] = []
    publishers: List[RightsHolder] = []
    confidence_notes: Optional[str] = None

class ResolvedCue(BaseModel):
    cue_number: int
    title: str
    artist: Optional[str] = None
    usage_type: UsageType = UsageType.BI
    timecode_in: str
    timecode_out: str
    duration_frames: int
    duration_timecode: str
    fps: float = 24.0
    iswc: Optional[str] = None
    work_id: Optional[str] = None
    writers: List[RightsHolder] = []
    publishers: List[RightsHolder] = []
    total_writer_share: float = 0.0
    total_publisher_share: float = 0.0
    split_status: SplitStatus = SplitStatus.CONFIRMED_PUBLIC_SPLIT
    estimated_equal_share: Optional[float] = None
    is_verified: bool = False
    flagged_issues: List[str] = []
    source_reference: Optional[str] = None
    raw_clip_name: Optional[str] = None
    source_type: str = "LIVE_PARALLEL_API"  # "LIVE_PARALLEL_API", "LOCAL_PRO_CATALOG_FALLBACK", "IN_HOUSE_SFX"
    search_id: Optional[str] = None
    latency_ms: Optional[float] = None
    is_live_hit: bool = True
    supervisor_signed_off: bool = False
    signed_off_at: Optional[str] = None
    signed_off_by: Optional[str] = None
    invoke_mode: Optional[str] = None
    provenance: Optional[str] = None
    excerpts: List[str] = []
    extract_id: Optional[str] = None
    extracted_urls: List[str] = []
    confidence_notes: Optional[str] = None
    fallback_reason: Optional[str] = None

class CueSheetManifest(BaseModel):
    project_title: str
    production_company: str = "Independent Studio Productions"
    director: str = "Lead Director"
    target_distributor: str = "Netflix / Worldwide"
    framerate: float = 24.0
    total_duration: str = "00:00:00:00"
    cues: List[ResolvedCue] = []
    total_cues: int = 0
    cleared_cues: int = 0
    flagged_cues: int = 0
    compliance_score: float = 0.0

class AgentEvent(BaseModel):
    event_type: str  # "start", "parse", "reasoning", "parallel_query", "parallel_result", "reconciliation", "cue_verified", "cue_flagged", "complete", "error"
    timestamp: str
    message: str
    cue_number: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
