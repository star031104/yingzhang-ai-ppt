from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

OPENALEX_ENDPOINT = "https://api.openalex.org/works"
OPENVERSE_ENDPOINT = "https://api.openverse.org/v1/images/"
APPROVED_RESEARCH_HOSTS = {"api.openalex.org", "api.openverse.org"}
OPEN_LICENSES = {"cc0", "pdm", "by", "by-sa", "cc-by", "cc-by-sa", "public-domain"}


def _query_text(value: str, limit: int = 100) -> str:
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value[:limit]


def build_research_manifest(
    sources: list[dict], slides: list[dict], brief: dict | None = None
) -> dict:
    brief = brief or {}
    covered_roles = {
        str(section.get("semanticRole", "content"))
        for source in sources
        for section in source.get("sections", [])
        if str(section.get("text", "")).strip()
    }
    required = {"background", "problem", "method", "data", "conclusion"}
    gaps = sorted(required - covered_roles)
    work_queries = []
    image_queries = []
    for slide in slides:
        title = _query_text((slide.get("content") or {}).get("title", ""), 72)
        role = str(slide.get("role", "content"))
        if role in {"background", "problem", "comparison", "data", "insight"} and title:
            work_queries.append(
                {
                    "position": slide.get("position"),
                    "query": title,
                    "purpose": slide.get("purpose", ""),
                }
            )
        if role in {"cover", "background", "insight", "conclusion"} and title:
            image_queries.append(
                {
                    "position": slide.get("position"),
                    "query": _query_text(slide.get("visualIntent", {}).get("imageQuery") or title),
                    "licensePolicy": "open-license-review-required",
                }
            )
    return {
        "version": "research-manifest-v1",
        "mode": "source-first-with-controlled-discovery",
        "audience": str(brief.get("audience", "")),
        "objective": str(brief.get("objective", "")),
        "sourceCount": len(sources),
        "evidenceGaps": gaps,
        "workQueries": work_queries[:12],
        "imageQueries": image_queries[:10],
        "providers": [
            {
                "id": "openalex",
                "kind": "scholarly-metadata",
                "host": "api.openalex.org",
                "requiresReview": True,
            },
            {
                "id": "openverse",
                "kind": "open-media",
                "host": "api.openverse.org",
                "requiresLicenseVerification": True,
            },
        ],
        "policy": {
            "externalClaimsRequireImportAndCitation": True,
            "externalAssetsRequireLicenseVerification": True,
            "generatedImagesCannotProveFacts": True,
            "allowedHosts": sorted(APPROVED_RESEARCH_HOSTS),
        },
    }


def normalize_openalex(payload: dict) -> list[dict]:
    result = []
    for item in payload.get("results", []):
        location = item.get("best_oa_location") or item.get("primary_location") or {}
        result.append(
            {
                "provider": "openalex",
                "id": item.get("id"),
                "title": item.get("display_name") or item.get("title"),
                "year": item.get("publication_year"),
                "authors": [
                    author.get("author", {}).get("display_name")
                    for author in item.get("authorships", [])[:5]
                    if author.get("author")
                ],
                "citedByCount": item.get("cited_by_count", 0),
                "openAccess": bool((item.get("open_access") or {}).get("is_oa")),
                "sourceUrl": location.get("landing_page_url")
                or location.get("pdf_url")
                or item.get("doi")
                or item.get("id"),
                "license": location.get("license") or "metadata-only",
                "status": "candidate",
            }
        )
    return result


def normalize_openverse(payload: dict) -> list[dict]:
    result = []
    for item in payload.get("results", []):
        license_key = str(item.get("license") or "").lower()
        result.append(
            {
                "provider": "openverse",
                "id": item.get("id"),
                "title": item.get("title") or "开放许可图片",
                "thumbnail": item.get("thumbnail"),
                "assetUrl": item.get("url"),
                "sourceUrl": item.get("foreign_landing_url"),
                "creator": item.get("creator"),
                "license": license_key,
                "licenseUrl": item.get("license_url"),
                "approvedLicense": license_key in OPEN_LICENSES,
                "status": "license-review-required",
            }
        )
    return result


async def discover_research(query: str, kind: str, limit: int = 8) -> list[dict]:
    from app.config import settings
    if settings.local_only_mode:
        raise ValueError("完全本地模式已关闭外部素材检索")
    query = _query_text(query)
    if not query:
        return []
    limit = max(1, min(20, int(limit)))
    endpoint = OPENALEX_ENDPOINT if kind == "works" else OPENVERSE_ENDPOINT
    if urlparse(endpoint).hostname not in APPROVED_RESEARCH_HOSTS:
        raise ValueError("研究源不在允许列表")
    params = {"search": query, "per_page": limit}
    if kind != "works":
        params = {"q": query, "page_size": limit, "license_type": "commercial"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.get(
            endpoint, params=params, headers={"User-Agent": "YingZhang/0.3 research@localhost"}
        )
        response.raise_for_status()
    payload = response.json()
    return normalize_openalex(payload) if kind == "works" else normalize_openverse(payload)
