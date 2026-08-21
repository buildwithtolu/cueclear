import pytest
import os
from backend.parsers.edl_parser import (
    timecode_to_frames,
    frames_to_timecode,
    calculate_duration,
    EDLParser
)
from backend.parsers.xml_parser import XMLParser

def test_timecode_math():
    # 24 FPS tests
    assert timecode_to_frames("00:00:00:00", 24.0) == 0
    assert timecode_to_frames("00:00:01:00", 24.0) == 24
    assert timecode_to_frames("00:01:00:00", 24.0) == 1440
    assert timecode_to_frames("01:00:00:00", 24.0) == 86400
    assert timecode_to_frames("00:01:14:12", 24.0) == (1 * 60 + 14) * 24 + 12

    # Frames back to timecode
    assert frames_to_timecode(0, 24.0) == "00:00:00:00"
    assert frames_to_timecode(24, 24.0) == "00:00:01:00"
    assert frames_to_timecode(1440, 24.0) == "00:01:00:00"
    assert frames_to_timecode(1788, 24.0) == "00:01:14:12"

    # Duration calculation
    dur_frames, dur_tc = calculate_duration("00:01:14:00", "00:02:40:12", 24.0)
    assert dur_frames == timecode_to_frames("00:02:40:12", 24.0) - timecode_to_frames("00:01:14:00", 24.0)
    assert dur_tc == "00:01:26:12"

def test_edl_parser_with_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "samples", "sample_trailer.edl")
    with open(sample_path, "r", encoding="utf-8") as f:
        edl_content = f.read()

    parser = EDLParser(default_fps=24.0)
    clips = parser.parse(edl_content)

    assert len(clips) == 5
    
    # Check Event 002 (M83 - Midnight City)
    clip_2 = clips[1]
    assert clip_2.event_number == 2
    assert clip_2.track_type == "A3"
    assert "Midnight City" in clip_2.clip_name
    assert clip_2.record_in == "00:00:05:00"
    assert clip_2.record_out == "00:01:31:12"
    assert clip_2.duration_timecode == "00:01:26:12"

    # Check Event 003 (Hans Zimmer - Time)
    clip_3 = clips[2]
    assert clip_3.event_number == 3
    assert "Hans Zimmer" in clip_3.clip_name
    assert clip_3.duration_timecode == "00:00:45:00"

def test_xml_parser_with_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "samples", "sample_indie_reel.xml")
    with open(sample_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    parser = XMLParser(default_fps=24.0)
    clips = parser.parse(xml_content)

    assert len(clips) == 2
    assert "Ludovico Einaudi" in clips[0].clip_name
    assert clips[0].duration_frames == (2400 - 240)
    assert "Radiohead" in clips[1].clip_name
    assert clips[1].duration_frames == (4850 - 2450)

def test_edl_parser_video_filtering():
    """Confirms that video cuts (V, V1, V2) are filtered out, while audio cuts (A1, A2, NONE) are kept."""
    edl_mixed = """
TITLE: MIXED_VIDEO_AUDIO_REEL
FCM: NON-DROP FRAME

001  V        C        00:00:00:00 00:00:05:00 01:00:00:00 01:00:05:00
* FROM CLIP NAME: Video_Opening_Shot.mov

002  A1       C        00:00:00:00 00:01:00:00 01:00:00:00 01:01:00:00
* FROM CLIP NAME: M83_Midnight_City.wav

003  V2       C        00:00:05:00 00:00:10:00 01:00:05:00 01:00:10:00
* FROM CLIP NAME: Overlay_Graphic.png

004  AUD      C        00:00:00:00 00:00:30:00 01:01:00:00 01:01:30:00
* FROM CLIP NAME: SFX_SubBoom.wav
"""
    parser = EDLParser(default_fps=24.0)
    clips = parser.parse(edl_mixed)
    
    assert len(clips) == 2
    assert clips[0].clip_name == "M83 Midnight City"
    assert clips[0].track_type == "A1"
    assert clips[1].clip_name == "SFX SubBoom"
    assert clips[1].track_type == "AUD"

def test_xml_parser_stereo_deduplication():
    """Confirms that stereo linked audio tracks (A1 and A2) sharing the same name and in/out frames are deduplicated to 1 cue."""
    xml_stereo = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
<sequence id="sequence-1">
    <name>Stereo Sequence</name>
    <rate><timebase>24</timebase></rate>
    <media>
        <audio>
            <!-- Left Channel (A1) -->
            <track>
                <clipitem id="clipitem-1">
                    <name>Hans_Zimmer_Time.wav</name>
                    <in>0</in>
                    <out>1080</out>
                    <start>0</start>
                    <end>1080</end>
                </clipitem>
            </track>
            <!-- Right Channel (A2 - Duplicate Stereo Pair) -->
            <track>
                <clipitem id="clipitem-2">
                    <name>Hans_Zimmer_Time.wav</name>
                    <in>0</in>
                    <out>1080</out>
                    <start>0</start>
                    <end>1080</end>
                </clipitem>
            </track>
        </audio>
    </media>
</sequence>
</xmeml>"""
    parser = XMLParser(default_fps=24.0)
    clips = parser.parse(xml_stereo)
    
    # Should deduplicate the stereo pair into exactly 1 clip
    assert len(clips) == 1
    assert clips[0].clip_name == "Hans Zimmer Time"
    assert clips[0].duration_frames == 1080

