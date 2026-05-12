from __future__ import annotations

from typing import Protocol

from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.context import ContextSelector
from ado_ai_pr_review.indexer import RepoIndexer
from ado_ai_pr_review.models import SelectedContext
from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest


class CommandHandler(Protocol):
    def handle(
        self,
        request: ReviewRequest,
        platform: PlatformAdapter,
        model: LLMPort,
        config: ReviewConfig,
    ) -> None: ...


def select_context(
    request: ReviewRequest,
    config: ReviewConfig,
    primary_instruction: str,
    prefer_tags: frozenset[str] = frozenset(),
) -> SelectedContext:
    entries = RepoIndexer(exclude=config.context.index.exclude).build(request.repo_root)
    selector = ContextSelector(max_files=config.context.dynamic_context.max_files)
    return selector.select(
        repo_root=request.repo_root,
        guidance_paths=[
            primary_instruction,
            *config.guidelines.code_style,
            *config.guidelines.security,
        ],
        entries=entries,
        prefer_tags=set(prefer_tags),
    )
