"""Rewriting slide XML must keep namespace prefixes that attributes refer to."""
import zipfile

from app.personalization.roundtrip_learning import annotate_export
from app.powerpoint.roundtrip import apply_generated_effects, update_imported_object

SLIDE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    ' xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
    ' xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" mc:Ignorable="p14">'
    '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr/><p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
    '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="10" cy="10"/></a:xfrm></p:spPr>'
    '<p:txBody><a:bodyPr/><a:p><a:r><a:t>Old</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>'
    '<mc:AlternateContent><mc:Choice Requires="p14"><p:transition spd="slow" p14:dur="1200"><p14:vortex/></p:transition></mc:Choice>'
    '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback></mc:AlternateContent>'
    '<p:extLst><p:ext uri="{BB962C8B-B14F-4D97-AF65-F5344CB8AC3E}"><p14:creationId val="1"/></p:ext></p:extLst></p:sld>'
)
PRESENTATION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst></p:presentation>'
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"'
    ' Target="slides/slide1.xml"/></Relationships>'
)


def _package(path):
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("ppt/presentation.xml", PRESENTATION)
        package.writestr("ppt/_rels/presentation.xml.rels", RELS)
        package.writestr("ppt/slides/slide1.xml", SLIDE)
    return path


def _slide(path):
    with zipfile.ZipFile(path) as package:
        return package.read("ppt/slides/slide1.xml").decode()


def _assert_prefixes_kept(xml, transition_wrapper=True):
    assert 'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"' in xml
    assert 'mc:Ignorable="p14"' in xml
    assert ('Requires="p14"' in xml) is transition_wrapper
    assert "<p14:creationId" in xml
    assert "ns0:" not in xml and "ns1:" not in xml


def test_effects_keep_markup_compatibility_prefixes(tmp_path):
    deck = _package(tmp_path / "deck.pptx")
    report = apply_generated_effects(deck, [{"powerPoint": {"transition": "push", "animation": "fade"}}])
    xml = _slide(deck)
    assert report == {"transitionSlides": 1, "animationSlides": 1}
    _assert_prefixes_kept(xml, transition_wrapper=False)
    assert xml.count("<p:transition") == 1 and "<p:push/>" in xml and "<p:timing>" in xml


def test_imported_object_edit_keeps_prefixes(tmp_path):
    source = _package(tmp_path / "source.pptx")
    before, after = update_imported_object(source, tmp_path / "out.pptx", 1, "2", "New")
    xml = _slide(tmp_path / "out.pptx")
    assert (before, after) == ("Old", "New")
    _assert_prefixes_kept(xml)


def test_provenance_annotation_keeps_prefixes(tmp_path):
    deck = _package(tmp_path / "deck.pptx")
    annotate_export(deck, "project", [{"id": "slide", "content": {}}])
    _assert_prefixes_kept(_slide(deck))
