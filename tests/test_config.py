from pathlib import Path

import pytest

from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.errors import ConfigurationError


def write_config(tmp_path: Path, extra: str = "") -> None:
    (tmp_path / ".ado-ai-review.yml").write_text(
        f"""
version: 1
instructions:
  reviewer: .ado-ai-review/instructions/reviewer.md
  security: .ado-ai-review/instructions/security.md
  indexer: .ado-ai-review/instructions/indexer.md
  fixer: .ado-ai-review/instructions/fixer.md
{extra}
""".strip(),
        encoding="utf-8",
    )


def test_config_loader_applies_defaults(tmp_path: Path) -> None:
    write_config(tmp_path)

    config = ReviewConfig.load(tmp_path)

    assert config.version == 1
    assert config.commands.review.enabled is True
    assert config.review.max_findings == 20
    assert "node_modules/**" in config.context.index.exclude


def test_config_loader_raises_configuration_error_when_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match=r"Missing \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_malformed_yaml(
    tmp_path: Path,
) -> None:
    (tmp_path / ".ado-ai-review.yml").write_text("version: [\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_unknown_field(
    tmp_path: Path,
) -> None:
    write_config(tmp_path, "unexpected: true")

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_unsupported_version(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    config_path = tmp_path / ".ado-ai-review.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("version: 1", "version: 2"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_bool_version(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    config_path = tmp_path / ".ado-ai-review.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("version: 1", "version: true"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_float_version(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    config_path = tmp_path / ".ado-ai-review.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("version: 1", "version: 1.0"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_string_version(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    config_path = tmp_path / ".ado-ai-review.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("version: 1", 'version: "1"'),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_negative_max_findings(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
review:
  max_findings: -1
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_unknown_severity_threshold(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
review:
  severity_threshold: blocker
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_unknown_fix_mode(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
fix:
  mode: broad-refactor
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_negative_dynamic_context_max_files(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
context:
  dynamic_context:
    max_files: -1
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_quoted_bool(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
commands:
  review:
    enabled: "yes"
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_quoted_numeric_limit(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
review:
  max_findings: "5"
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_blank_instruction_path(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    config_path = tmp_path / ".ado-ai-review.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "reviewer: .ado-ai-review/instructions/reviewer.md",
            'reviewer: "   "',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_empty_guideline_entry(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
guidelines:
  code_style:
    - ""
  security:
    - .ado-ai-review/guidelines/security.md
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_empty_review_focus(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
review:
  focus: []
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_empty_security_rule_item(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
security:
  rules:
    - ""
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)


def test_config_loader_raises_configuration_error_for_empty_context_exclude_item(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
context:
  index:
    exclude:
      - ""
""",
    )

    with pytest.raises(ConfigurationError, match=r"Invalid \.ado-ai-review\.yml"):
        ReviewConfig.load(tmp_path)
