from __future__ import annotations

from pathlib import Path

FORBIDDEN = [
    "AdoPipelineAdapter",
    "ado-ai-pr-review pipeline",
    "azure-pipelines.ado-ai-review.yml",
    "templates/pipeline.yml",
    "SYSTEM_ACCESSTOKEN",
    "Pipeline Setup",
    "pipeline mode",
]


def test_active_docs_do_not_describe_pipeline_mode() -> None:
    paths = [
        Path("README.md"),
        Path("docs/operations/ado-ai-review.md"),
        Path("docs/marketplace-testing.md"),
        Path("docs/marketplace-publishing.md"),
        Path("docs/follow-ups/webhook-auth.md"),
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN:
            assert forbidden not in text, f"{path}: contains {forbidden!r}"
