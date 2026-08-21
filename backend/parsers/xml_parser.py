import xml.etree.ElementTree as ET
import re
from typing import List, Optional
from ..models.schemas import ParsedAudioClip
from .edl_parser import frames_to_timecode, calculate_duration

class XMLParser:
    """
    Parser for Final Cut Pro 7 / Premiere Pro XML format.
    Extracts audio tracks, clip names, timecodes, and durations.
    """
    def __init__(self, default_fps: float = 24.0):
        self.fps = default_fps

    def parse(self, xml_text: str) -> List[ParsedAudioClip]:
        clips: List[ParsedAudioClip] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML content: {e}")

        # Extract sequence framerate if present
        timebase_elem = root.find(".//rate/timebase")
        if timebase_elem is not None and timebase_elem.text:
            try:
                self.fps = float(timebase_elem.text)
            except ValueError:
                pass

        # Locate audio clipitems with stereo deduplication
        event_counter = 1
        seen_cues = set()

        for audio_track in root.findall(".//audio/track"):
            for clipitem in audio_track.findall(".//clipitem"):
                name_elem = clipitem.find("name")
                start_elem = clipitem.find("start")
                end_elem = clipitem.find("end")
                in_elem = clipitem.find("in")
                out_elem = clipitem.find("out")
                file_elem = clipitem.find(".//file/name")
                path_elem = clipitem.find(".//file/pathurl")

                raw_name = name_elem.text if (name_elem is not None and name_elem.text) else f"Audio_Cue_{event_counter}"
                
                # Check for valid integer frame counts
                try:
                    start_frame = int(start_elem.text) if (start_elem is not None and start_elem.text) else 0
                    end_frame = int(end_elem.text) if (end_elem is not None and end_elem.text) else 0
                    src_in_frame = int(in_elem.text) if (in_elem is not None and in_elem.text) else 0
                    src_out_frame = int(out_elem.text) if (out_elem is not None and out_elem.text) else (end_frame - start_frame)
                except ValueError:
                    continue

                if end_frame <= start_frame:
                    continue

                # Clean display name
                clean_name = re.sub(r"\.(wav|mp3|aiff|m4a|flac|aac)$", "", raw_name, flags=re.IGNORECASE)
                clean_name = clean_name.replace("_", " ").strip()

                # Deduplicate stereo linked tracks (e.g. A1 and A2 stereo pairs sharing same clean name and frames)
                cue_signature = (clean_name.lower(), start_frame, end_frame)
                if cue_signature in seen_cues:
                    continue
                seen_cues.add(cue_signature)

                duration_frames = end_frame - start_frame
                dur_tc = frames_to_timecode(duration_frames, self.fps)
                rec_in_tc = frames_to_timecode(start_frame, self.fps)
                rec_out_tc = frames_to_timecode(end_frame, self.fps)
                src_in_tc = frames_to_timecode(src_in_frame, self.fps)
                src_out_tc = frames_to_timecode(src_out_frame, self.fps)

                source_file = path_elem.text if (path_elem is not None and path_elem.text) else (file_elem.text if file_elem is not None else None)

                clip = ParsedAudioClip(
                    event_number=event_counter,
                    track_type="AUDIO",
                    clip_name=clean_name,
                    source_file=source_file,
                    source_in=src_in_tc,
                    source_out=src_out_tc,
                    record_in=rec_in_tc,
                    record_out=rec_out_tc,
                    duration_frames=duration_frames,
                    duration_timecode=dur_tc,
                    fps=self.fps,
                    comments=[f"XML Track Item {event_counter}"]
                )
                clips.append(clip)
                event_counter += 1

        return clips
