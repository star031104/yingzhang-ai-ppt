"""Small, user-facing reading report shared by upload and workspace responses."""


def source_reading_view(row) -> dict:
    model = row.model or {}
    stats = model.get("stats", {})
    warnings = model.get("readingWarnings", [])
    grouped = {}
    for warning in warnings:
        key = (warning.get("code"), warning.get("message"))
        if key not in grouped:
            grouped[key] = {**warning, "pages": [], "count": 0}
        grouped[key]["count"] += 1
        if warning.get("page") is not None and warning["page"] not in grouped[key]["pages"]:
            grouped[key]["pages"].append(warning["page"])
    warnings = [{**item, "message": item.get("message", "") +
                 (f"（涉及第 {'、'.join(map(str, item['pages']))} 页）" if item["pages"] and item["count"] > 1 else
                  f"（共 {item['count']} 处）" if item["count"] > 1 else "")} for item in grouped.values()]
    outline = {}
    for section in model.get("sections", []):
        title = section.get("title", "正文")
        if title not in outline:
            outline[title] = {"id": section["id"], "title": title,
                              "headingPath": section.get("headingPath", []),
                              "mainPoint": section.get("understanding", {}).get("mainPoint", ""),
                              "limitations": section.get("understanding", {}).get("limitations", [])}
    return {
        "id": row.id, "name": row.name, "sha256": row.sha256, **stats,
        "sections": len(outline), "sectionFragments": len(model.get("sections", [])),
        "readingStatus": "needs-attention" if warnings else "read",
        "readingWarnings": warnings,
        "outline": list(outline.values())[:40],
        "outlineTotal": len(outline),
    }
