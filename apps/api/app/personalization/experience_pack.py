import base64
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import PersonalCase, PersonalMemory, PersonalReference
from app.personalization.private_files import reference_root, validate_pptx
from app.personalization.schemas import validate_preference


def export_pack(db, profile, include_references=False):
    rules = [{"key": row.key, "value": row.value["choice"]} for row in db.scalars(select(PersonalMemory).where(
        PersonalMemory.profile_id == profile.id, PersonalMemory.status == "confirmed"))]
    examples = [{"label": row.label, "scenario": row.scenario, "features": row.features} for row in db.scalars(select(PersonalCase).where(
        PersonalCase.profile_id == profile.id, PersonalCase.status == "confirmed"))]
    references = []
    total = 0
    if include_references:
        for row in db.scalars(select(PersonalReference).where(PersonalReference.profile_id == profile.id)):
            data = (reference_root(row) / "reference.pptx").read_bytes()
            total += len(data)
            if total > 20 * 1024 * 1024:
                raise HTTPException(413, "原生参考模板合计超过 20 MB，请分别下载处理")
            references.append({"name": row.name, "sha256": hashlib.sha256(data).hexdigest(), "pptx": base64.b64encode(data).decode()})
    payload = {"version": 2, "name": profile.name, "scenario": profile.scenario, "memories": rules,
               "cases": examples, "references": references, "includesOriginalFiles": bool(references)}
    payload["checksum"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return payload


def validate_pack(payload):
    if not isinstance(payload, dict) or payload.get("version") != 2 or set(payload) - {
        "version", "name", "scenario", "memories", "cases", "references", "includesOriginalFiles", "checksum"
    }:
        raise ValueError("不支持的经验包格式")
    provided = payload.get("checksum")
    clean = {key: value for key, value in payload.items() if key != "checksum"}
    if provided != hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest():
        raise ValueError("经验包校验和不一致")
    for key, limit in (("memories", 100), ("cases", 200), ("references", 10)):
        if not isinstance(payload.get(key, []), list) or len(payload.get(key, [])) > limit:
            raise ValueError("经验包内容超过支持范围")
    for rule in payload.get("memories", []):
        if not isinstance(rule, dict) or set(rule) != {"key", "value"}:
            raise ValueError("规则格式错误")
        validate_preference(rule["key"], rule["value"])
    for case in payload.get("cases", []):
        if not isinstance(case, dict) or set(case) != {"label", "scenario", "features"}:
            raise ValueError("案例格式错误")
        features = case["features"]
        if not isinstance(features, dict) or set(features) - {"version", "slideCount", "roleSequence", "averageTitleLength", "rules", "variants", "retainsBusinessText", "quality"}:
            raise ValueError("案例包含不支持的字段")
        if features.get("retainsBusinessText") is not False:
            raise ValueError("案例不能包含业务正文")
        if not isinstance(features.get("roleSequence"), list) or len(features["roleSequence"]) > 60 or any(
            role not in {"cover", "agenda", "section", "background", "problem", "method", "architecture", "evidence", "data", "comparison", "insight", "conclusion", "content", "questions"}
            for role in features["roleSequence"] if isinstance(role, str)
        ) or any(not isinstance(role, str) for role in features["roleSequence"]):
            raise ValueError("案例页型不合法")
        if not isinstance(features.get("rules", {}), dict):
            raise ValueError("案例规则格式错误")
        for key, value in features.get("rules", {}).items():
            validate_preference(key, value)
        if any(type(features.get(key)) is not int or not 0 <= features[key] <= 10000 for key in ("slideCount", "averageTitleLength")):
            raise ValueError("案例计数格式错误")
        # Discard imported quality claims; user must inspect and accept the imported example.
        features["version"] = 1
        features["quality"] = {"passed": False, "imported": True}
        features["variants"] = {}
    for reference in payload.get("references", []):
        if not isinstance(reference, dict) or set(reference) != {"name", "sha256", "pptx"}:
            raise ValueError("模板格式错误")
        if not isinstance(reference["name"], str) or not 1 <= len(reference["name"].strip()) <= 200:
            raise ValueError("模板名称不合法")
        if not isinstance(reference["pptx"], str) or not isinstance(reference["sha256"], str):
            raise ValueError("模板文件格式错误")
        data = base64.b64decode(reference["pptx"], validate=True)
        validate_pptx(data)
        if hashlib.sha256(data).hexdigest() != reference["sha256"]:
            raise ValueError("模板校验失败")
    return payload
