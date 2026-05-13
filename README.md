# ADO AI PR Review

AI-powered pull request reviewer for Azure DevOps. Listens for `/ai` commands in PR comments
and posts review findings, security findings, and mechanical fix suggestions.

Runs in two modes:

| Tryb | Opis |
|---|---|
| **Webhook** (`serve`) | Serwer FastAPI w Azure Container Apps. Odbiera service hooki ADO i przetwarza je asynchronicznie. |
| **Lokalny** (`local`) | CLI działający na bieżącej gałęzi git. Wyniki na stdout. Nie wymaga credentiali ADO. |

---

## Komendy

Wpisz jedną z poniższych w komentarzu do dowolnego wątku PR:

| Komenda | Opis |
|---|---|
| `/ai review` | Przegląd kodu: poprawność, luki w testach, czytelność, utrzymywalność. |
| `/ai security` | Bezpieczeństwo: sekrety, injection, authn/authz, walidacja wejść. |
| `/ai fix` | Mechaniczne poprawki: formatowanie, lint, importy, bezpieczne renamy. Tworzy osobny PR. |

Przy pierwszym uruchomieniu (brak komendy) agent publikuje komentarz powitalny i tworzy
pliki konfiguracyjne w repozytorium (`.ado-ai-review.yml` i katalog `.ado-ai-review/`).

---

## Dokumentacja

| Dokument | Zawartość |
|---|---|
| [docs/managed-app.md](docs/managed-app.md) | Wdrożenie na Azure Container Apps: szablon ARM, onboarding tożsamości w ADO, konfiguracja service hooków. |
| [docs/local-testing.md](docs/local-testing.md) | Testowanie lokalne: tryb CLI i serwer webhook z PAT. Opcje LLM (Copilot, Azure OpenAI, klucz API). |
| [docs/agent-internals.md](docs/agent-internals.md) | Jak agent się autoryzuje, jak wybiera repozytoria, jak tworzy gałęzie i commity, narzędzia i allowlista poleceń. |

---

## Szybki start — tryb lokalny

```bash
# Instalacja
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Z GitHub Copilot (najprostsza opcja)
gh auth login
ado-ai-pr-review local --command review --llm copilot

# Z Azure OpenAI
export AZURE_OPENAI_BASE_URL=https://<instancja>.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review local --command review
```

Pełne instrukcje: [docs/local-testing.md](docs/local-testing.md)

---

## Szybki start — serwer webhook (lokalnie)

```bash
export ADO_PAT=<twój-personal-access-token>
./scripts/run-local.sh
```

Skrypt uruchamia serwer na porcie 8080, sprawdza `/health` i drukuje przykładowe polecenie `curl`.

---

## Zmienne środowiskowe

### LLM

| Zmienna | Wymagana | Opis |
|---|---|---|
| `AZURE_OPENAI_BASE_URL` | Tak (Azure OpenAI) | Endpoint modelu, musi kończyć się `/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | Tak (Azure OpenAI) | Nazwa deploymenta (np. `gpt-4o`) |
| `AZURE_OPENAI_API_KEY` | Nie | Klucz API; pominięcie → DefaultAzureCredential |

### ADO (tylko tryb webhook)

| Zmienna | Wymagana | Opis |
|---|---|---|
| `ADO_AUTH_MODE` | Nie | `entra` (domyślnie, Managed Identity) lub `pat` |
| `ADO_PAT` | Tylko `pat` | Personal Access Token |
| `WEBHOOK_USERNAME` | Nie | Login Basic Auth |
| `WEBHOOK_PASSWORD` | Nie | Hasło Basic Auth |

---

## Konfiguracja repozytorium (`.ado-ai-review.yml`)

Plik tworzony automatycznie przy pierwszym uruchomieniu. Edytuj, żeby dostosować zachowanie agenta.

```yaml
version: 1

commands:
  review:
    enabled: true
  security:
    enabled: true
  fix:
    enabled: true

instructions:
  reviewer: .ado-ai-review/instructions/reviewer.md
  security: .ado-ai-review/instructions/security.md
  indexer:  .ado-ai-review/instructions/indexer.md
  fixer:    .ado-ai-review/instructions/fixer.md

guidelines:
  code_style:
    - .ado-ai-review/guidelines/code-style.md
    - AGENTS.md
    - CLAUDE.md
    - .github/copilot-instructions.md
  security:
    - .ado-ai-review/guidelines/security.md

review:
  focus:
    - bug-risk
    - test-gaps
    - readability
    - maintainability
  max_findings: 20
  severity_threshold: medium   # low | medium | high | critical

security:
  enabled: true
  rules:
    - secrets
    - injection
    - authz
    - authn
    - input-validation
    - unsafe-deserialization

fix:
  enabled: true
  mode: mechanical-only
  inline_suggestions:
    enabled: true
    max_lines: 20
  branch:
    enabled: true
    name_template: ai-fix/pr-{pr_id}/{run_id}
    one_commit_per_change: true

context:
  index:
    enabled: true
    exclude:
      - node_modules/**
      - bin/**
      - obj/**
      - dist/**
      - build/**
      - .git/**
  dynamic_context:
    enabled: true
    max_files: 20

observability:
  langfuse:
    enabled: true
    trace_pr_reviews: true
    capture_token_usage: true
    capture_costs: true
    capture_prompts: false
    capture_code_context: false
```

### Pliki instrukcji (`.ado-ai-review/instructions/`)

| Plik | Rola |
|---|---|
| `reviewer.md` | Priorytety, progi ważności i styl wyników przeglądu kodu. |
| `security.md` | Lista kontrolna bezpieczeństwa i mapowanie ważności. |
| `indexer.md` | Instrukcje tagowania plików przy indeksowaniu repozytorium. |
| `fixer.md` | Whitelist mechanicznych poprawek i format dostarczania. |

### Pliki wytycznych (`.ado-ai-review/guidelines/`)

| Plik | Rola |
|---|---|
| `code-style.md` | Styl kodu i konwencje nazewnictwa projektu. |
| `security.md` | Wymagania bezpieczeństwa i polityki danych wrażliwych. |

Istniejące pliki (`AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`) są
ładowane automatycznie, jeśli są wymienione w `guidelines.code_style`.

---

## Granica bezpieczeństwa

- Model nigdy nie otrzymuje surowego narzędzia shell. Każda operacja zapisu przechodzi przez kod Pythona walidujący wyjście modelu.
- Sekrety wykryte lokalnie w diffie są redagowane **przed** wysłaniem do modelu.
- Poprawki (`/ai fix`) nigdy nie trafiają bezpośrednio na gałąź PR — zawsze na osobną gałąź `ai-fix/...`.
- Wszystkie odczyty i zapisy plików są ograniczone do katalogu roboczego żądania (`WorkspaceBoundary`).
- Logi są emitowane jako JSON; tokeny i znane formaty sekretów są redagowane.

Szczegóły: [docs/agent-internals.md](docs/agent-internals.md)

---

## Rozwój lokalny

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
```
