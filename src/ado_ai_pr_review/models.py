from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewCommand(StrEnum):
    REVIEW = "review"
    SECURITY = "security"
    FIX = "fix"
    ONBOARDING = "onboarding"
    SKIP = "skip"  # no-op: unrecognised comment, ignore the event


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingType(StrEnum):
    BUG_RISK = "bug_risk"
    SECURITY = "security"
    TEST_GAP = "test_gap"
    READABILITY = "readability"
    MAINTAINABILITY = "maintainability"
    MECHANICAL_FIX = "mechanical_fix"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: FindingType
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4_000)
    file_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    suggested_code: str | None = None

    @model_validator(mode="after")
    def validate_line_range(self) -> Self:
        if self.line_start is None and self.line_end is not None:
            raise ValueError("line_start is required when line_end is set")
        if self.line_start is not None and self.line_end is None:
            object.__setattr__(self, "line_end", self.line_start)
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=4_000)
    findings: list[Finding] = Field(default_factory=list)


class RepoIndexEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    language: str
    description: str
    tags: list[str] = Field(default_factory=list)
    relevance: int = Field(default=0, ge=0, le=100)


class SelectedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    always_on_guidance: list[str] = Field(default_factory=list)
    dynamic_files: list[str] = Field(default_factory=list)
    security_notes: list[str] = Field(default_factory=list)


class FixDelivery(StrEnum):
    INLINE_SUGGESTION = "inline_suggestion"
    FIX_BRANCH_CANDIDATE = "fix_branch_candidate"
    REJECTED = "rejected"


class FixCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery: FixDelivery
    title: str
    explanation: str
    file_path: str | None = None
    replacement: str | None = None
    commit_message: str | None = None


class InlineSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4_000)
    replacement_lines: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_line_range(self) -> Self:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        return self


class FixBranchChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4_000)
    full_file_content: str = Field(min_length=1)
    commit_message: str = Field(min_length=1, max_length=256)


class FixPlanResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=4_000)
    inline_suggestions: list[InlineSuggestion] = Field(default_factory=list)
    fix_branch_changes: list[FixBranchChange] = Field(default_factory=list)
