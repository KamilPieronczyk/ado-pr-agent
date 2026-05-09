# src/ado_ai_pr_review/model_client.py
# Re-export shim — keeps existing imports working.
from ado_ai_pr_review.llm.azure_openai import (
    ModelClient,
    ResponseObject,
    ResponsesClient,
    build_openai_client,
)

__all__ = ["ModelClient", "ResponseObject", "ResponsesClient", "build_openai_client"]
