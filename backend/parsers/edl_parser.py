import re
from typing import List, Tuple, Optional
from ..models.schemas import ParsedAudioClip

def timecode_to_frames(tc: str, fps: float = 24.0) -> int:
    """
    Converts HH:MM:SS:FF (NDF) or HH:MM:SS;FF (DF) timecode into total frames.
    Accurately handles:
    - 23.976 / 24.00 FPS (Cinematic Non-Drop Frame)
    - 25.00 FPS (Broadcast PAL Non-Drop Frame)
    - 29.97 FPS (SMPTE Drop-Frame / Non-Drop Frame)
    - 30.00 / 59.94 / 60.00 FPS
    """
    is_drop_frame = ";" in tc or (abs(fps - 29.97) < 0.01 and ";" in tc)
    parts = re.split(r"[:;]", tc.strip())
    if len(parts) != 4:
        raise ValueError(f"Invalid timecode format: '{tc}'. Expected HH:MM:SS:FF or HH:MM:SS;FF")
    
    hours, minutes, seconds, frames = map(int, parts)
    
    if is_drop_frame and abs(fps - 29.97) < 0.05:
        # SMPTE 29.97 Drop-Frame algorithm:
        # Drops frames :00 and :01 of every minute, except minutes divisible by 10
        total_minutes = (hours * 60) + minutes
        drop_frames = 2 * (total_minutes - (total_minutes // 10))
        total_frames = (hours * 107892) + (minutes * 1798) + (seconds * 30) + frames - drop_frames
        return total_frames
        
    int_fps = int(round(fps))
    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    total_frames = (total_seconds * int_fps) + frames
    return total_frames

def frames_to_timecode(total_frames: int, fps: float = 24.0, is_drop_frame: bool = False) -> str:
    """
    Converts total frames back into standard timecode.
    Uses ':' for Non-Drop Frame and ';' for Drop-Frame.
    """
    if total_frames < 0:
        total_frames = 0
        
    if is_drop_frame and abs(fps - 29.97) < 0.05:
        # SMPTE 29.97 Drop-Frame reverse algorithm
        d = total_frames // 17978
        m = total_frames % 17978
        if m > 1:
            total_frames += (18 * d) + (2 * ((m - 2) // 1798))
        else:
            total_frames += (18 * d)
            
        frames = total_frames % 30
        seconds = (total_frames // 30) % 60
        minutes = ((total_frames // 30) // 60) % 60
        hours = ((total_frames // 30) // 3600)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d};{frames:02d}"
        
    int_fps = int(round(fps))
    frames = total_frames % int_fps
    total_seconds = total_frames // int_fps
    
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"

def calculate_duration(in_tc: str, out_tc: str, fps: float = 24.0) -> Tuple[int, str]:
    """Calculates frame duration and formatted timecode duration between In and Out."""
    in_frames = timecode_to_frames(in_tc, fps)
    out_frames = timecode_to_frames(out_tc, fps)
    dur_frames = max(0, out_frames - in_frames)
    dur_tc = frames_to_timecode(dur_frames, fps)
    return dur_frames, dur_tc

class EDLParser:
    """
    Parser for CMX 3600 standard Edit Decision Lists (EDL).
    Extracts audio events, clip names, source files, and record timecodes.
    """
    def __init__(self, default_fps: float = 24.0):
        self.fps = default_fps

    def parse(self, edl_text: str) -> List[ParsedAudioClip]:
        lines = edl_text.strip().splitlines()
        clips: List[ParsedAudioClip] = []
        seen_cues = set()
        
        current_event_num: Optional[int] = None
        current_track: Optional[str] = None
        current_src_in: Optional[str] = None
        current_src_out: Optional[str] = None
        current_rec_in: Optional[str] = None
        current_rec_out: Optional[str] = None
        current_clip_name: Optional[str] = None
        current_source_file: Optional[str] = None
        current_comments: List[str] = []

        # Regex for CMX 3600 event line: matches event number, track, transition/edit type, and 4 timecodes
        event_pattern = re.compile(
            r"^(\d{3,4})\s+([\w\d/]+)\s+.*?\s*"
            r"(\d{2}[:;]\d{2}[:;]\d{2}[:;]\d{2})\s+"
            r"(\d{2}[:;]\d{2}[:;]\d{2}[:;]\d{2})\s+"
            r"(\d{2}[:;]\d{2}[:;]\d{2}[:;]\d{2})\s+"
            r"(\d{2}[:;]\d{2}[:;]\d{2}[:;]\d{2})"
        )

        def save_current_clip():
            nonlocal current_event_num, current_track, current_src_in, current_src_out
            nonlocal current_rec_in, current_rec_out, current_clip_name, current_source_file, current_comments
            
            if current_event_num is not None and current_rec_in and current_rec_out and current_track:
                # Only keep audio tracks (A, A1, A2, A3, A4, AA, AUD, NONE)
                is_audio = any(current_track.upper().startswith(p) for p in ["A", "AUD", "NONE"])
                if not is_audio:
                    # Reset fields and ignore video cuts
                    current_event_num = None
                    current_track = None
                    current_src_in = None
                    current_src_out = None
                    current_rec_in = None
                    current_rec_out = None
                    current_clip_name = None
                    current_source_file = None
                    current_comments = []
                    return
                
                # Determine display clip name
                clean_name = current_clip_name or current_source_file or f"Audio_Event_{current_event_num}"
                clean_name = re.sub(r"\.(wav|mp3|aiff|m4a|flac|aac)$", "", clean_name, flags=re.IGNORECASE)
                clean_name = clean_name.replace("_", " ").strip()

                # Deduplicate stereo audio tracks sharing same name & timecode
                cue_signature = (clean_name.lower(), current_rec_in, current_rec_out)
                if cue_signature in seen_cues:
                    current_event_num = None
                    current_track = None
                    current_src_in = None
                    current_src_out = None
                    current_rec_in = None
                    current_rec_out = None
                    current_clip_name = None
                    current_source_file = None
                    current_comments = []
                    return
                seen_cues.add(cue_signature)

                dur_frames, dur_tc = calculate_duration(current_rec_in, current_rec_out, self.fps)

                clip = ParsedAudioClip(
                    event_number=current_event_num,
                    track_type=current_track,
                    clip_name=clean_name,
                    source_file=current_source_file,
                    source_in=current_src_in,
                    source_out=current_src_out,
                    record_in=current_rec_in,
                    record_out=current_rec_out,
                    duration_frames=dur_frames,
                    duration_timecode=dur_tc,
                    fps=self.fps,
                    comments=list(current_comments)
                )
                clips.append(clip)

            # Reset fields
            current_event_num = None
            current_track = None
            current_src_in = None
            current_src_out = None
            current_rec_in = None
            current_rec_out = None
            current_clip_name = None
            current_source_file = None
            current_comments = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check FPS marker in EDL header
            if line_str.startswith("FCM:"):
                if "DROP FRAME" in line_str and "NON" not in line_str:
                    self.fps = 29.97

            # Match event line
            match = event_pattern.match(line_str)
            if match:
                save_current_clip()
                current_event_num = int(match.group(1))
                current_track = match.group(2)
                current_src_in = match.group(3)
                current_src_out = match.group(4)
                current_rec_in = match.group(5)
                current_rec_out = match.group(6)
                continue

            # Match comments and metadata lines
            if line_str.startswith("*"):
                comment_content = line_str[1:].strip()
                current_comments.append(comment_content)
                
                if comment_content.upper().startswith("FROM CLIP NAME:"):
                    current_clip_name = comment_content[15:].strip()
                elif comment_content.upper().startswith("SOURCE FILE:"):
                    current_source_file = comment_content[12:].strip()
                elif comment_content.upper().startswith("CLIP NAME:"):
                    current_clip_name = comment_content[10:].strip()

        # Save last clip
        save_current_clip()
        return clips
