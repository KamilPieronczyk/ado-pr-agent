from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal

logger = logging.getLogger(__name__)

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    ValidationError,
    field_validator,
)

from ado_ai_pr_review.errors import ConfigurationError

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveStrictInt = Annotated[int, Field(strict=True, ge=1)]


class CommandToggle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = True


class CommandsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review: CommandToggle = Field(default_factory=CommandToggle)
    security: CommandToggle = Field(default_factory=CommandToggle)
    fix: CommandToggle = Field(default_factory=CommandToggle)


class InstructionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer: NonBlankStr = ".ado-ai-review/instructions/reviewer.md"
    security: NonBlankStr = ".ado-ai-review/instructions/security.md"
    indexer: NonBlankStr = ".ado-ai-review/instructions/indexer.md"
    fixer: NonBlankStr = ".ado-ai-review/instructions/fixer.md"


class GuidelinesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code_style: list[NonBlankStr] = Field(
        default_factory=lambda: [".ado-ai-review/guidelines/code-style.md"], min_length=1
    )
    security: list[NonBlankStr] = Field(
        default_factory=lambda: [".ado-ai-review/guidelines/security.md"], min_length=1
    )


class ReviewSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    focus: list[NonBlankStr] = Field(
        default_factory=lambda: ["bug-risk", "test-gaps", "readability", "maintainability"],
        min_length=1,
    )
    max_findings: PositiveStrictInt = 20
    severity_threshold: Literal["low", "medium", "high", "critical"] = "medium"


class SecuritySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = True
    rules: list[NonBlankStr] = Field(
        default_factory=lambda: [
            "secrets",
            "injection",
            "authz",
            "authn",
            "input-validation",
            "unsafe-deserialization",
        ],
        min_length=1,
    )


class FixInlineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = True
    max_lines: PositiveStrictInt = 20


class FixBranchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = True
    name_template: NonBlankStr = "ai-fix/pr-{pr_id}/{run_id}"
    one_commit_per_change: StrictBool = True


class FixSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = True
    mode: Literal["mechanical-only"] = "mechanical-only"
    inline_suggestions: FixInlineSettings = Field(default_factory=FixInlineSettings)
    branch: FixBranchSettings = Field(default_factory=FixBranchSettings)


class IndexSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = True
    exclude: list[NonBlankStr] = Field(
        default_factory=lambda: [
            "node_modules/**",
            "bin/**",
            "obj/**",
            "dist/**",
            "build/**",
            ".git/**",
        ],
        min_length=1,
    )


class DynamicContextSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = True
    max_files: PositiveStrictInt = 20


class ContextSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: IndexSettings = Field(default_factory=IndexSettings)
    dynamic_context: DynamicContextSettings = Field(default_factory=DynamicContextSettings)


class LangfuseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = True
    trace_pr_reviews: StrictBool = True
    capture_token_usage: StrictBool = True
    capture_costs: StrictBool = True
    capture_prompts: StrictBool = False
    capture_code_context: StrictBool = False


class ObservabilitySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)


class ReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    instructions: InstructionsConfig = Field(default_factory=InstructionsConfig)
    guidelines: GuidelinesConfig = Field(default_factory=GuidelinesConfig)
    review: ReviewSettings = Field(default_factory=ReviewSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    fix: FixSettings = Field(default_factory=FixSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("version must be the integer 1")
        return value

    @classmethod
    def load(cls, repo_root: Path) -> ReviewConfig:
        path = repo_root / ".ado-ai-review.yml"
        if not path.exists():
            raise ConfigurationError("Missing .ado-ai-review.yml")
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return cls.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            raise ConfigurationError(f"Invalid .ado-ai-review.yml: {exc}") from exc

    @classmethod
    def load_or_default(cls, repo_root: Path) -> ReviewConfig:
        path = repo_root / ".ado-ai-review.yml"
        if not path.exists():
            logger.warning(
                "No .ado-ai-review.yml found; running with built-in defaults. "
                "Add a .ado-ai-review.yml to customise review behaviour.",
            )
            return cls.model_validate({"version": 1})
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return cls.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            raise ConfigurationError(f"Invalid .ado-ai-review.yml: {exc}") from exc
