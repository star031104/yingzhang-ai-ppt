# Presentation benchmarks

Only synthetic or openly redistributable fixtures belong here. Private user documents are prohibited.

Suites: `academic-thesis`, `business-report`, `product-launch`, `data-dashboard`, and `reference-style`. Run `python scripts/verify-benchmarks.py` for the merge gate: it parses each automated family, extracts evidence, plans a deck, validates source-section links and required metric values, then enforces thresholds for planning quality, source coverage, the number of available composition families, accessibility, and the least-compatible supported delivery profile. Planned visual maturity has a lower threshold because no candidate has been rendered or selected yet; the project's quality checks assess selected layouts and real renders before final delivery. The reference-style family is marked manual because the repository does not yet contain an openly redistributable or synthetic PPTX template.

The delivery profile score is a deterministic capability-rule check. A separate Office CI job generates PPTX files from all four automated fixture families and renders them through LibreOffice, checking page count and every planned slide title. This improves real-export coverage but does not replace desktop verification in PowerPoint or WPS.

`manifest.json` defines the reproducible v3 thresholds. Add a synthetic fixture and its measurable requirements before adding an automated family to the manifest. The professional suite also checks layout contracts, narrative rhythm, brand consistency, accessibility, research governance, and cross-platform delivery. Detailed chart and numeric-claim regressions live in the presentation-engine and Python tests.

All benchmark content must remain synthetic or explicitly redistributable. Do not copy customer documents, API prompts, or model outputs that contain private data into this directory. Benchmark scores are deterministic regression signals, not a substitute for visual review in PowerPoint or WPS.
