"""Opaque provenance markers permit conservative matching after external editing."""
import hashlib
import json
import zipfile
from difflib import SequenceMatcher
from xml.etree import ElementTree as ET

from app.personalization.private_files import validate_pptx
from app.powerpoint.roundtrip import _read_parts, _slide_paths, _objects, NS

MARKER = "yingzhang:v1:"


def annotate_export(target, project_id, slides):
    parts = _read_parts(target.read_bytes())
    for path, spec in zip(_slide_paths(parts), slides, strict=True):
        root = ET.fromstring(parts[path])
        fingerprint = hashlib.sha256(json.dumps(spec.get("content", {}), sort_keys=True).encode()).hexdigest()[:16]
        for props in root.findall(".//p:cNvPr", NS):
            value = f"{MARKER}{project_id}:{spec['id']}:{props.get('id')}:{fingerprint}"
            previous = props.get("descr", "").split("\n" + MARKER)[0]
            props.set("descr", previous + "\n" + value)
        parts[path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def _read_objects(data):
    parts = _read_parts(data)
    pages = []
    for path in _slide_paths(parts):
        root = ET.fromstring(parts[path])
        markers = {}
        for props in root.findall(".//p:cNvPr", NS):
            marker = props.get("descr", "").split(MARKER)
            if len(marker) == 2:
                markers[props.get("id")] = marker[-1].strip()
        objects = _objects(parts[path])
        for item in objects:
            item["marker"] = markers.get(str(item.get("id", item.get("objectId", ""))))
        pages.append(objects)
    return pages


def compare_external(original, edited, project_id):
    validate_pptx(edited)
    before, after = _read_objects(original), _read_objects(edited)
    known = {item["marker"]: item for page in before for item in page if item.get("marker")}
    used = set()
    changes = []
    strong = uncertain = 0
    for page_index, page in enumerate(after):
        for item in page:
            marker = item.get("marker")
            prior = known.get(marker) if marker and marker.startswith(project_id + ":") else None
            confidence = 1.0 if prior else 0.0
            if prior and marker in used:
                # A copied shape inherits metadata; it is not a second accepted correction.
                prior = None
                confidence = 0.0
            if not prior and page_index < len(before):
                matches = [(SequenceMatcher(None, str(old.get("text", "")), str(item.get("text", ""))).ratio(), old)
                           for old in before[page_index] if old.get("text")]
                if matches:
                    score, candidate = max(matches, key=lambda value: value[0])
                    if score > .75:
                        prior, confidence = candidate, min(.7, score)
            if not prior:
                uncertain += 1
                continue
            if marker:
                used.add(marker)
            strong += confidence == 1.0
            uncertain += confidence < 1.0
            fields = [key for key in ("text", "bbox", "kind", "type") if prior.get(key) != item.get(key)]
            if fields:
                changes.append({"page": page_index + 1, "objectId": str(item.get("id", item.get("objectId", ""))),
                                "confidence": confidence, "changedFields": fields,
                                "businessTextChanged": "text" in fields})
    missing = len(set(known) - used)
    uncertain += missing
    return {"version": 1, "matchedObjects": strong, "uncertainObjects": uncertain, "deletedOrUnmatchedObjects": missing, "changes": changes[:500],
            "beforePages": len(before), "afterPages": len(after),
            "canSuggest": strong > 0 and uncertain == 0 and len(before) == len(after),
            "message": "低置信度匹配和正文修改仅用于对照，不自动生成长期规则"}
