import xml.etree.ElementTree as ET
from xml.dom import minidom
from ..models.schemas import CueSheetManifest

def export_cue_sheet_to_cisac_xml(manifest: CueSheetManifest) -> str:
    """
    Generates standard CISAC Audio-Visual Cue Sheet (AVCS) XML.
    """
    root = ET.Element("AVCueSheet", {
        "version": "1.2",
        "xmlns": "http://www.cisac.org/standards/avcs"
    })

    # Header / Production Details
    header = ET.SubElement(root, "ProductionHeader")
    ET.SubElement(header, "Sender").text = "CueClear AI Autonomous Clearance Engine"
    ET.SubElement(header, "WorkTitle").text = manifest.project_title
    ET.SubElement(header, "WorkOrigin").text = "Film/TV Post-Production Sequence"
    ET.SubElement(header, "ProductionCompany").text = manifest.production_company
    ET.SubElement(header, "Director").text = manifest.director
    ET.SubElement(header, "TargetDistributor").text = manifest.target_distributor
    ET.SubElement(header, "Framerate").text = str(manifest.framerate)
    ET.SubElement(header, "TotalCues").text = str(manifest.total_cues)
    ET.SubElement(header, "ComplianceScore").text = f"{manifest.compliance_score}%"

    # Musical Cues List
    cues_elem = ET.SubElement(root, "MusicalCues")

    for cue in manifest.cues:
        cue_elem = ET.SubElement(cues_elem, "Cue", {
            "id": f"CUE-{cue.cue_number:03d}",
            "verified": "true" if cue.is_verified else "false"
        })
        
        ET.SubElement(cue_elem, "CueNumber").text = str(cue.cue_number)
        ET.SubElement(cue_elem, "WorkTitle").text = cue.title
        ET.SubElement(cue_elem, "Title").text = cue.title
        ET.SubElement(cue_elem, "Artist").text = cue.artist or "N/A"
        ET.SubElement(cue_elem, "UsageType").text = cue.usage_type.value
        ET.SubElement(cue_elem, "TimecodeIn").text = cue.timecode_in
        ET.SubElement(cue_elem, "TimecodeOut").text = cue.timecode_out
        ET.SubElement(cue_elem, "DurationTimecode").text = cue.duration_timecode
        ET.SubElement(cue_elem, "DurationFrames").text = str(cue.duration_frames)
        ET.SubElement(cue_elem, "WorkID").text = cue.work_id or "N/A"
        ET.SubElement(cue_elem, "ISWC").text = cue.iswc or "N/A"

        # Writers
        writers_elem = ET.SubElement(cue_elem, "Writers")
        for w in cue.writers:
            w_node = ET.SubElement(writers_elem, "Writer")
            ET.SubElement(w_node, "Name").text = w.name
            ET.SubElement(w_node, "Role").text = w.role
            ET.SubElement(w_node, "PRO").text = w.pro
            ET.SubElement(w_node, "Share").text = f"{w.share:.2f}" if w.share is not None else "UNDISCLOSED"
            if w.ipi_cae:
                ET.SubElement(w_node, "IPICAE").text = w.ipi_cae

        # Publishers
        pubs_elem = ET.SubElement(cue_elem, "Publishers")
        for p in cue.publishers:
            p_node = ET.SubElement(pubs_elem, "Publisher")
            ET.SubElement(p_node, "Name").text = p.name
            ET.SubElement(p_node, "Role").text = p.role
            ET.SubElement(p_node, "PRO").text = p.pro
            ET.SubElement(p_node, "Share").text = f"{p.share:.2f}" if p.share is not None else "UNDISCLOSED"
            if p.ipi_cae:
                ET.SubElement(p_node, "IPICAE").text = p.ipi_cae

    # Prettify XML string
    xml_str = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(xml_str)
    return parsed.toprettyxml(indent="  ")
