# Testowanie lokalne

Agent można uruchomić lokalnie na dwa sposoby:

| Tryb | Opis |
|---|---|
| **CLI (`local`)** | Przeglądanie bieżącej gałęzi git, wyniki na stdout. Bez ADO, bez webhooków. |
| **Serwer webhook (`serve`)** | Pełny serwer FastAPI odbierający payloady ADO service hook. Wymaga PAT lub Entra. |

---

## Wymagania wstępne

```bash
# Python 3.11+
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Opcjonalnie: GitHub Copilot jako LLM (nie wymaga Azure OpenAI)
gh auth login
```

Sprawdź instalację:

```bash
ado-ai-pr-review --help
```

---

## Tryb 1: CLI (`local`)

Przeglądanie bieżącej gałęzi bez żadnych credentiali ADO.
Wyniki trafiają na stdout.

### Z GitHub Copilot (najprostsza opcja)

Wymaga aktywnej subskrypcji Copilot i zalogowania przez `gh auth login`.

```bash
gh auth login
ado-ai-pr-review local --command review --llm copilot
```

### Z Azure OpenAI — interaktywnie (`az login`)

```bash
az login
export AZURE_OPENAI_BASE_URL=https://<instancja>.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review local --command review
```

### Z Azure OpenAI — klucz API

```bash
export AZURE_OPENAI_API_KEY=<klucz-api>
export AZURE_OPENAI_BASE_URL=https://<instancja>.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review local --command security
```

### Opcje CLI

```bash
ado-ai-pr-review local \
  --command review|security|fix \
  --target-branch main          # domyślnie: main
  --llm copilot|azure           # domyślnie: azure
```

Diff jest obliczany jako `origin/<target-branch>...HEAD` — upewnij się, że gałąź ma
odpowiedni remote (`git fetch origin`) przed uruchomieniem.

---

## Tryb 2: Lokalny serwer webhook (`serve`)

Uruchom pełny serwer i wyślij mu ręcznie payload ADO.
Wymaga PAT (Personal Access Token) do uwierzytelniania w ADO.

### Szybki start — skrypt

```bash
export ADO_PAT=<twój-personal-access-token>
./scripts/run-local.sh
```

Skrypt automatycznie:
- wybiera LLM (domyślnie `copilot`, jeśli brak kluczy Azure OpenAI)
- zatrzymuje poprzedni proces na tym samym porcie
- uruchamia serwer w tle i sprawdza `/health`

Logi trafiają do `/tmp/webhook.log` (konfigurowalnie przez `LOG_FILE`).

### Ręczne uruchomienie

```bash
export ADO_AUTH_MODE=pat
export ADO_PAT=<twój-personal-access-token>
export AZURE_OPENAI_BASE_URL=https://<instancja>.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o

ado-ai-pr-review serve --host 0.0.0.0 --port 8080 --verbose
```

### Sprawdzenie zdrowia serwera

```bash
curl -s http://localhost:8080/health
```

### Wysłanie testowego payloadu

```bash
curl -s -u test:testpass \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/webhook_pr_created.json \
  http://localhost:8080/webhook/ado
```

Ważne: webhook odpowiada `200 OK` natychmiast (przetwarzanie asynchroniczne).
Wyniki pojawią się w logach i jako komentarze w PR (jeśli `ADO_PAT` ma odpowiednie uprawnienia).

---

## Testy jednostkowe i statyczna analiza

```bash
# Testy
pytest

# Linting
ruff check src tests

# Typy
mypy src
```

Wszystkie trzy narzędzia muszą przejść bez błędów przed wypchnięciem zmian.

---

## Używanie ngrok do testowania webhooków z ADO

Jeśli chcesz przetestować pełny przepływ z prawdziwym ADO service hookiem:

```bash
# W osobnym terminalu
ngrok http 8080

# Skopiuj URL ngrok (np. https://abc123.ngrok.io)
# Skonfiguruj w ADO: Project Settings → Service hooks
# URL: https://abc123.ngrok.io/webhook/ado
```

---

## Zmienne środowiskowe — podsumowanie (tryb lokalny)

| Zmienna | Wymagana | Opis |
|---|---|---|
| `ADO_AUTH_MODE` | Nie (dla `serve`) | `pat` (lokalnie) lub `entra` (produkcja) |
| `ADO_PAT` | Tak przy `ADO_AUTH_MODE=pat` | Personal Access Token do ADO |
| `AZURE_OPENAI_BASE_URL` | Tak (Azure OpenAI) | Endpoint modelu, musi kończyć się `/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | Tak (Azure OpenAI) | Nazwa deploymenta modelu |
| `AZURE_OPENAI_API_KEY` | Nie | Klucz API; jeśli nieustaw, używa DefaultAzureCredential |
| `WEBHOOK_USERNAME` | Nie | Login Basic Auth (domyślnie: `test`) |
| `WEBHOOK_PASSWORD` | Nie | Hasło Basic Auth (domyślnie: `testpass`) |
| `PORT` | Nie | Port serwera (domyślnie: `8080`) |
| `LOG_FILE` | Nie | Ścieżka pliku logów (domyślnie: `/tmp/webhook.log`) |
