"""Optional local document-parsing backends (MinerU, PaddleOCR-VL or any command).

The built-in PDF parser (PyMuPDF + optional Tesseract) is fast and dependency-free
but weak on scanned pages, formulas and complex tables. Small local vision-language
parsers such as MinerU 2.5 (1.2B) and PaddleOCR-VL (0.9B) handle those well and
still run on the user's machine, so they fit a local-first product.

The backend is a command line run without a shell; it must write Markdown (and,
for MinerU, an optional ``*_content_list.json`` with page indices) somewhere under
``{output}``. Presets are templates only: install the tool yourself and adjust
``YINGZHANG_DOCUMENT_PARSER_COMMAND`` if your version uses different flags.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

PRESET_COMMANDS = {
    # MinerU 2.x: `mineru -p <input> -o <output_dir> -b <backend>`
    "mineru": "mineru -p {input} -o {output} -b pipeline",
    # PaddleOCR 3.x document parsing pipeline with PaddleOCR-VL
    "paddleocr-vl": "paddleocr doc_parser -i {input} --save_path {output}",
}
AUTO_TRIGGER_WARNINGS = {"ocr-required", "ocr-completed", "table-text-only", "table-extraction-failed"}
FORMULA_HINT = re.compile(r"[∑∫√∂≤≥≈±×÷]|\\(?:frac|sum|int|sqrt|alpha|beta|lambda)|[=]\s*\(\d+\)\s*$|公式\s*[（(]\d+[）)]", re.MULTILINE)
SUPPORTED = {"builtin", "mineru", "paddleocr-vl", "command"}


@dataclass
class ExternalResult:
    backend: str
    markdown: str
    page_map: dict[str, int]
    reason: str


def configured_backend() -> str:
    value = str(settings.document_parser or "builtin").strip().lower()
    return value if value in SUPPORTED else "builtin"


def command_template(backend: str) -> str | None:
    if settings.document_parser_command:
        return settings.document_parser_command
    return PRESET_COMMANDS.get(backend)


def availability() -> dict:
    """Describe the configured backend for the settings page and diagnostics."""
    backend = configured_backend()
    template = command_template(backend) if backend != "builtin" else None
    executable = shlex.split(template)[0] if template else None
    return {
        "backend": backend,
        "policy": settings.document_parser_policy,
        "command": template,
        "executable": executable,
        "available": bool(executable and shutil.which(executable)),
        "presets": PRESET_COMMANDS,
    }


def trigger_reason(warnings: list[dict], text: str) -> str | None:
    """Why the external parser should run for this PDF, or None to keep the built-in result."""
    if configured_backend() == "builtin":
        return None
    if str(settings.document_parser_policy).lower() == "always":
        return "always"
    codes = {str(item.get("code")) for item in warnings}
    if codes & AUTO_TRIGGER_WARNINGS:
        return "scanned-or-table-pages"
    if len(FORMULA_HINT.findall(text)) >= 3:
        return "formulas"
    return None


def normalize_math(markdown: str) -> str:
    """Use YingZhang's ``$$…$$`` formula delimiter for inline ``$…$`` LaTeX as well."""
    def inline(match: re.Match) -> str:
        body = match.group(1)
        return f"$${body.strip()}$$" if re.search(r"[\\^_]", body) else match.group(0)

    markdown = re.sub(r"\$\$\s*\n?([\s\S]{1,400}?)\n?\s*\$\$", lambda m: "$$" + " ".join(m.group(1).split()) + "$$", markdown)
    return re.sub(r"(?<!\$)\$([^$\n]{1,200})\$(?!\$)", inline, markdown)


def _page_map(output: Path) -> dict[str, int]:
    """Heading/line text → 1-based page, from MinerU's content list when present."""
    mapping: dict[str, int] = {}
    for path in output.rglob("*content_list*.json"):
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or "page_idx" not in item:
                continue
            text = re.sub(r"\s+", "", str(item.get("text") or ""))[:60]
            if text and text not in mapping:
                mapping[text] = int(item["page_idx"]) + 1
        break
    return mapping


def run_external_parser(name: str, data: bytes, reason: str) -> ExternalResult:
    backend = configured_backend()
    template = command_template(backend)
    if not template:
        raise RuntimeError("未配置外部解析命令")
    with tempfile.TemporaryDirectory(prefix="yz-parse-") as folder:
        root = Path(folder)
        source = root / ("input" + (Path(name).suffix.lower() or ".pdf"))
        source.write_bytes(data)
        output = root / "output"
        output.mkdir()
        arguments = [part.format(input=str(source), output=str(output)) for part in shlex.split(template)]
        if not shutil.which(arguments[0]):
            raise RuntimeError(f"找不到解析程序 {arguments[0]}，请先在本机安装或调整命令")
        completed = subprocess.run(
            arguments, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=settings.document_parser_timeout_seconds, check=False,
        )
        if completed.returncode:
            raise RuntimeError((completed.stderr or completed.stdout or "解析失败").strip()[-400:])
        candidates = sorted(output.rglob("*.md"), key=lambda path: path.stat().st_size, reverse=True)
        if not candidates:
            raise RuntimeError("外部解析没有产生 Markdown 结果")
        markdown = normalize_math(candidates[0].read_text(encoding="utf-8", errors="replace"))
        if len(re.sub(r"\s", "", markdown)) < 20:
            raise RuntimeError("外部解析结果为空")
        return ExternalResult(backend, markdown, _page_map(output), reason)


def page_for(title: str, text: str, page_map: dict[str, int]) -> int | None:
    if not page_map:
        return None
    for probe in (title, text[:80]):
        key = re.sub(r"\s+", "", probe)[:60]
        if not key:
            continue
        if key in page_map:
            return page_map[key]
        for known, page in page_map.items():
            if key[:20] and known.startswith(key[:20]):
                return page
    return None
