"""Keep the test counts quoted in README / development report in sync with the code.

Counts are taken from the code itself: Python tests via ``pytest --collect-only``,
engine and web tests by counting ``test(``/``it(`` cases in their test files. The
numbers live between markers such as ``<!-- stats:python -->300<!-- /stats -->``.

    uv run --locked --extra dev python scripts/update-doc-stats.py          # rewrite docs
    uv run --locked --extra dev python scripts/update-doc-stats.py --check  # CI: fail if stale
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "README.en.md", ROOT / "docs" / "development-report.md"]
MARKER = re.compile(r"<!-- stats:(?P<key>[a-z-]+) -->(?P<value>\d+)<!-- /stats -->")
CASE = re.compile(r"^\s*(?:test|it)(?:\.(?:skip|only|each\([^)]*\)))?\(\s*['\"`]", re.MULTILINE)


def python_tests() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    if not match:
        raise SystemExit("pytest --collect-only did not report a test count:\n" + result.stdout[-800:] + result.stderr[-800:])
    return int(match.group(1))


def counted(pattern: str) -> int:
    return sum(len(CASE.findall(path.read_text(encoding="utf-8"))) for path in ROOT.glob(pattern))


def measure() -> dict[str, int]:
    return {
        "python": python_tests(),
        "engine": counted("packages/presentation-engine/test/*.test.mjs"),
        "web": counted("apps/web/src/**/*.test.ts") + counted("apps/web/src/**/*.test.tsx"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when a document quotes stale numbers")
    args = parser.parse_args()
    stats = measure()
    stale: list[str] = []
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        found = {match.group("key") for match in MARKER.finditer(text)}
        missing = {"python", "engine", "web"} - found
        if missing:
            stale.append(f"{path.relative_to(ROOT)}: missing stats markers {sorted(missing)}")
        updated = MARKER.sub(lambda match: f"<!-- stats:{match.group('key')} -->{stats.get(match.group('key'), match.group('value'))}<!-- /stats -->", text)
        if updated != text:
            stale.append(f"{path.relative_to(ROOT)}: test counts are out of date")
            if not args.check:
                path.write_text(updated, encoding="utf-8")
    print("current test counts:", ", ".join(f"{key}={value}" for key, value in stats.items()))
    if args.check and stale:
        for item in stale:
            print("STALE:", item)
        print("Run: uv run --locked --extra dev python scripts/update-doc-stats.py")
        return 1
    for item in stale:
        if "missing" in item:
            print("WARNING:", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
