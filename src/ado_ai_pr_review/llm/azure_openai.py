from __future__ import annotations

import json
import os
from typing import Protocol

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI
from pydantic import ValidationError

from ado_ai_pr_review.errors import ModelOutputError
from ado_ai_pr_review.models import ReviewResult


class ResponseObject(Protocol):
    output_text: str


class ResponsesClient(Protocol):
    class ResponsesApi(Protocol):
        def create(self, **kwargs: object) -> ResponseObject: ...

    responses: ResponsesApi


def build_openai_client() -> OpenAI:
    base_url = os.environ["AZURE_OPENAI_BASE_URL"]
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if api_key:
        return OpenAI(api_key=api_key, base_url=base_url)
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    # Call the provider to get the current token string. Reviews complete
    # in well under the 1-hour Azure token lifetime.
    return OpenAI(api_key=token_provider(), base_url=base_url)


class ModelClient:
    def __init__(self, openai_client: ResponsesClient, deployment: str) -> None:
        self._openai_client = openai_client
        self._deployment = deployment

    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        response = self._openai_client.responses.create(
            model=self._deployment,
            instructions=system_prompt,
            input=user_prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "review_result",
                    "schema": ReviewResult.model_json_schema(),
                    "strict": True,
                }
            },
        )
        output_text = str(response.output_text)
        try:
            return ReviewResult.model_validate(json.loads(output_text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModelOutputError(f"Model returned invalid review JSON: {exc}") from exc
