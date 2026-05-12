from __future__ import annotations

import json
from pathlib import Path


def test_arm_template_does_not_collect_ado_pat() -> None:
    template = json.loads(Path("infra/mainTemplate.json").read_text(encoding="utf-8"))
    text = json.dumps(template)

    assert "adoAuthToken" not in text
    assert "ADO_AUTH_TOKEN" not in text
    assert "ado-auth-token" not in text
    assert "AZURE_CLIENT_ID" in text


def test_create_ui_definition_does_not_collect_ado_pat() -> None:
    ui = json.loads(Path("infra/createUiDefinition.json").read_text(encoding="utf-8"))
    text = json.dumps(ui)

    assert "Azure DevOps PAT" not in text
    assert "adoAuthToken" not in text
    assert "managed identity" in text.lower() or "service principal" in text.lower()
