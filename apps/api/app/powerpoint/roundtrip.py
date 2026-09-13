import hashlib
import io
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"p": P, "a": A, "r": R}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return {name: package.read(name) for name in package.namelist()}


def _slide_paths(parts: dict[str, bytes]) -> list[str]:
    presentation = ET.fromstring(parts["ppt/presentation.xml"])
    relationships = ET.fromstring(parts["ppt/_rels/presentation.xml.rels"])
    targets = {
        item.get("Id"): item.get("Target", "")
        for item in relationships.findall(f"{{{PR}}}Relationship")
    }
    paths = []
    for item in presentation.findall(".//p:sldId", NS):
        target = targets.get(item.get(f"{{{R}}}id"), "")
        if target.startswith("slides/"):
            paths.append(f"ppt/{target}")
        elif target:
            paths.append(str(Path("ppt") / target).replace("\\", "/"))
    return paths


def _bbox(container: ET.Element) -> dict[str, int]:
    xfrm = container.find(".//p:spPr/a:xfrm", NS)
    if xfrm is None:
        xfrm = container.find(".//p:xfrm", NS)
    if xfrm is None:
        return {}
    offset, extent = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
    if offset is None or extent is None:
        return {}
    return {
        "x": int(offset.get("x", "0")), "y": int(offset.get("y", "0")),
        "width": int(extent.get("cx", "0")), "height": int(extent.get("cy", "0")),
    }


def _objects(slide_xml: bytes) -> list[dict]:
    root = ET.fromstring(slide_xml)
    tree = root.find("p:cSld/p:spTree", NS)
    if tree is None:
        return []
    result = []
    for container in list(tree):
        tag = container.tag.rsplit("}", 1)[-1]
        if tag not in {"sp", "pic", "graphicFrame", "grpSp", "cxnSp"}:
            continue
        props = container.find(".//p:cNvPr", NS)
        if props is None:
            continue
        texts = [node.text or "" for node in container.findall(".//a:t", NS)]
        placeholder = container.find(".//p:nvPr/p:ph", NS)
        object_type = {
            "sp": "text" if texts else "shape", "pic": "image",
            "graphicFrame": "table-or-chart", "grpSp": "group", "cxnSp": "connector",
        }[tag]
        result.append({
            "id": str(props.get("id", "")), "name": props.get("name", ""),
            "type": object_type, "text": "".join(texts).strip(),
            "placeholder": placeholder.get("type", "body") if placeholder is not None else None,
            "bbox": _bbox(container), "editable": bool(texts),
        })
    return result


def inspect_pptx(data: bytes) -> dict:
    parts = _read_parts(data)
    slide_paths = _slide_paths(parts)
    slides = []
    for index, path in enumerate(slide_paths, 1):
        xml = parts[path]
        root = ET.fromstring(xml)
        objects = _objects(xml)
        title = next((item["text"] for item in objects if item["placeholder"] in {"title", "ctrTitle"} and item["text"]), "")
        slides.append({
            "position": index, "path": path, "title": title or next((item["text"] for item in objects if item["text"]), ""),
            "objects": objects, "hasTransition": root.find("p:transition", NS) is not None,
            "hasAnimation": root.find("p:timing", NS) is not None,
        })
    fidelity_parts = {
        name: _sha(value) for name, value in parts.items()
        if name.startswith(("ppt/theme/", "ppt/slideMasters/", "ppt/slideLayouts/")) and name.endswith(".xml")
    }
    return {
        "version": "ooxml-roundtrip-v1", "slideCount": len(slides), "slides": slides,
        "themeCount": sum(name.startswith("ppt/theme/theme") for name in fidelity_parts),
        "masterCount": sum(name.startswith("ppt/slideMasters/slideMaster") for name in fidelity_parts),
        "layoutCount": sum(name.startswith("ppt/slideLayouts/slideLayout") for name in fidelity_parts),
        "transitionSlides": sum(item["hasTransition"] for item in slides),
        "animationSlides": sum(item["hasAnimation"] for item in slides),
        "fidelityHashes": fidelity_parts,
    }


def _find_object(root: ET.Element, object_id: str) -> ET.Element | None:
    tree = root.find("p:cSld/p:spTree", NS)
    if tree is None:
        return None
    for container in list(tree):
        props = container.find(".//p:cNvPr", NS)
        if props is not None and props.get("id") == str(object_id):
            return container
    return None


def update_imported_object(source: Path, output: Path, slide_index: int, object_id: str, value: str) -> tuple[str, str]:
    parts = _read_parts(source.read_bytes())
    paths = _slide_paths(parts)
    if slide_index < 1 or slide_index > len(paths):
        raise ValueError("Slide index is out of range")
    path = paths[slide_index - 1]
    root = ET.fromstring(parts[path])
    container = _find_object(root, object_id)
    if container is None:
        raise ValueError("PowerPoint object not found")
    runs = container.findall(".//a:t", NS)
    if not runs:
        raise ValueError("Selected PowerPoint object has no editable text")
    before = "".join(node.text or "" for node in runs)
    runs[0].text = value
    for node in runs[1:]:
        node.text = ""
    parts[path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        for name, payload in parts.items():
            package.writestr(name, payload)
    return before, value


def export_roundtrip(source: Path, output: Path, baseline: Path | None = None) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    source_analysis = inspect_pptx((baseline or source).read_bytes())
    output_analysis = inspect_pptx(output.read_bytes())
    expected, actual = source_analysis["fidelityHashes"], output_analysis["fidelityHashes"]
    changed = [name for name, digest in expected.items() if actual.get(name) != digest]
    return {
        "mode": "ooxml-lossless-roundtrip-v1", "slides": output_analysis["slideCount"],
        "themesPreserved": not any(name.startswith("ppt/theme/") for name in changed),
        "mastersPreserved": not any(name.startswith("ppt/slideMasters/") for name in changed),
        "layoutsPreserved": not any(name.startswith("ppt/slideLayouts/") for name in changed),
        "animationsPreserved": source_analysis["animationSlides"] == output_analysis["animationSlides"],
        "transitionsPreserved": source_analysis["transitionSlides"] == output_analysis["transitionSlides"],
        "changedFidelityParts": changed,
    }


def _transition(root: ET.Element, kind: str, speed: str) -> None:
    existing = root.find("p:transition", NS)
    if existing is not None:
        root.remove(existing)
    if kind == "none":
        return
    element = ET.Element(f"{{{P}}}transition", {"spd": speed, "advClick": "1"})
    ET.SubElement(element, f"{{{P}}}{kind if kind in {'fade', 'push', 'wipe'} else 'fade'}")
    children = list(root)
    insert_at = next((index for index, child in enumerate(children) if child.tag in {f"{{{P}}}timing", f"{{{P}}}extLst"}), len(children))
    root.insert(insert_at, element)


def _simple_fade_animation(root: ET.Element, shape_id: str) -> None:
    existing = root.find("p:timing", NS)
    if existing is not None:
        root.remove(existing)
    timing = ET.Element(f"{{{P}}}timing")
    tn_list = ET.SubElement(timing, f"{{{P}}}tnLst")
    par1 = ET.SubElement(tn_list, f"{{{P}}}par")
    root_tn = ET.SubElement(par1, f"{{{P}}}cTn", {"id": "1", "dur": "indefinite", "restart": "never", "nodeType": "tmRoot"})
    root_children = ET.SubElement(root_tn, f"{{{P}}}childTnLst")
    sequence = ET.SubElement(root_children, f"{{{P}}}seq", {"concurrent": "1", "nextAc": "seek"})
    main_tn = ET.SubElement(sequence, f"{{{P}}}cTn", {"id": "2", "dur": "indefinite", "nodeType": "mainSeq"})
    main_children = ET.SubElement(main_tn, f"{{{P}}}childTnLst")
    par2 = ET.SubElement(main_children, f"{{{P}}}par")
    effect_tn = ET.SubElement(par2, f"{{{P}}}cTn", {"id": "3", "fill": "hold"})
    conditions = ET.SubElement(effect_tn, f"{{{P}}}stCondLst")
    ET.SubElement(conditions, f"{{{P}}}cond", {"delay": "indefinite"})
    effect_children = ET.SubElement(effect_tn, f"{{{P}}}childTnLst")
    effect = ET.SubElement(effect_children, f"{{{P}}}animEffect", {"transition": "in", "filter": "fade"})
    behavior = ET.SubElement(effect, f"{{{P}}}cBhvr")
    ET.SubElement(behavior, f"{{{P}}}cTn", {"id": "4", "dur": "500", "fill": "hold"})
    target = ET.SubElement(behavior, f"{{{P}}}tgtEl")
    ET.SubElement(target, f"{{{P}}}spTgt", {"spid": shape_id})
    children = list(root)
    insert_at = next((index for index, child in enumerate(children) if child.tag == f"{{{P}}}extLst"), len(children))
    root.insert(insert_at, timing)


def apply_generated_effects(pptx: Path, slides: list[dict]) -> dict:
    parts = _read_parts(pptx.read_bytes())
    paths = _slide_paths(parts)
    transition_count = animation_count = 0
    for path, spec in zip(paths, slides):
        effects = spec.get("powerPoint", {})
        root = ET.fromstring(parts[path])
        transition = str(effects.get("transition", "none"))
        _transition(root, transition, str(effects.get("transitionSpeed", "med")))
        transition_count += int(transition != "none")
        animation = str(effects.get("animation", "none"))
        if animation == "fade":
            objects = [item for item in _objects(ET.tostring(root)) if item["type"] in {"text", "shape", "table-or-chart"} and item["id"] != "1"]
            if objects:
                _simple_fade_animation(root, objects[0]["id"])
                animation_count += 1
        parts[path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(pptx, "w", zipfile.ZIP_DEFLATED) as package:
        for name, payload in parts.items():
            package.writestr(name, payload)
    return {"transitionSlides": transition_count, "animationSlides": animation_count}
