# Konfiguracja Managed Application (Azure)

Agent działa jako kontener w **Azure Container Apps** z zarządzaną tożsamością (`Managed Identity`).
Poniżej opisano pełen proces wdrożenia za pomocą dołączonego szablonu ARM (`infra/`).

---

## Co zostaje wdrożone

| Zasób | Nazwa | Cel |
|---|---|---|
| User Assigned Managed Identity | `<appName>-identity` | Tożsamość kontenera — używana do uwierzytelniania w ADO i OpenAI |
| Container Apps Environment | `<appName>-env` | Środowisko uruchomieniowe kontenera |
| Container App | `<appName>` | Właściwy serwer webhook |
| Azure OpenAI | `<appName>-openai` | Model LLM (np. `gpt-4o`) |
| Key Vault | `<appName>-kv` | Przechowuje hasło Basic Auth dla webhooka |

Prawa RBAC są automatycznie przypisywane:
- Managed Identity → rola **Cognitive Services OpenAI User** na instancji OpenAI
- Managed Identity → rola **Key Vault Secrets User** na Key Vault

---

## Wdrożenie — krok po kroku

### 1. Przygotuj parametry

Potrzebne wartości wejściowe:

| Parametr | Opis | Przykład |
|---|---|---|
| `appName` | Unikalna nazwa aplikacji (3–12 znaków, a–z, 0–9) | `myadobot` |
| `imageTag` | Tag obrazu Docker z `ghcr.io/kamilpieronczyk/ado-pr-agent` | `latest` |
| `openAiDeploymentName` | Nazwa modelu w Azure OpenAI | `gpt-4o` |
| `webhookUsername` | Login Basic Auth dla webhooka | `adowebhook` |
| `webhookPassword` | Hasło Basic Auth (min. 16 znaków) | `<silne-haslo>` |

### 2. Wdróż szablon ARM

```bash
az deployment group create \
  --resource-group <twoja-grupa-zasobów> \
  --template-file infra/mainTemplate.json \
  --parameters \
      appName=myadobot \
      openAiDeploymentName=gpt-4o \
      webhookUsername=adowebhook \
      webhookPassword=<silne-haslo>
```

### 3. Pobierz URL kontenera i principal ID tożsamości

```bash
az deployment group show \
  --resource-group <twoja-grupa-zasobów> \
  --name mainTemplate \
  --query "properties.outputs"
```

Zapisz `containerAppUrl` — będzie potrzebny do konfiguracji webhooka w ADO.
Zapisz `managedIdentityPrincipalId` — potrzebny do kroku 4.

### 4. Utwórz deployment modelu w Azure OpenAI

Po wdrożeniu ARM otwórz **Azure AI Foundry**, wybierz instancję `<appName>-openai`
i utwórz deployment o nazwie podanej w `openAiDeploymentName` (np. `gpt-4o`).

---

## Onboarding tożsamości w Azure DevOps

Azure RBAC **nie nadaje** uprawnień w Azure DevOps automatycznie.
Managed Identity musi być ręcznie dodana do organizacji ADO.

### Krok 1 — Dodaj tożsamość do organizacji

1. Przejdź do **Organization Settings → Users → Add user**.
2. W polu użytkownika wklej `managedIdentityPrincipalId` (GUID z kroku 3 powyżej).
3. Wybierz poziom dostępu: **Basic**.
4. Kliknij **Add**.

### Krok 2 — Nadaj uprawnienia w projekcie

W ustawieniach projektu (Project Settings → Permissions) dodaj tożsamość do roli z co najmniej:

| Uprawnienie | Wymagane dla |
|---|---|
| Code (Read) | Wszystkie tryby |
| Pull Request Threads (Read & Write) | Wszystkie tryby |
| Code (Contribute) | Tylko `/ai fix` (tworzenie gałęzi fix) |

### Krok 3 — Skonfiguruj service hook w ADO

1. Przejdź do **Project Settings → Service hooks → Create subscription**.
2. Wybierz **Web Hooks**.
3. Skonfiguruj triggery:
   - *Pull request created*
   - *Pull request updated*
   - *Pull request commented on*
4. Ustaw URL: `https://<containerAppUrl>/webhook/ado`
5. Ustaw Basic Auth: `webhookUsername` / `webhookPassword` z wdrożenia.

---

## Zmienne środowiskowe (wdrożone automatycznie)

Szablon ARM automatycznie wstrzykuje poniższe zmienne do kontenera:

| Zmienna | Źródło | Opis |
|---|---|---|
| `AZURE_OPENAI_BASE_URL` | Obliczane z nazwy instancji OpenAI | Endpoint modelu |
| `AZURE_OPENAI_DEPLOYMENT` | Parametr `openAiDeploymentName` | Nazwa deploymenta |
| `ADO_AUTH_MODE` | Stała: `entra` | Uwierzytelnianie przez Managed Identity |
| `WEBHOOK_USERNAME` | Parametr | Login Basic Auth |
| `WEBHOOK_PASSWORD` | Pobierane z Key Vault | Hasło Basic Auth |
| `AZURE_CLIENT_ID` | Managed Identity | Używane przez `DefaultAzureCredential` |

`AZURE_OPENAI_API_KEY` **nie** jest ustawiany — agent używa Managed Identity zamiast klucza API.

---

## Endpointy serwera

| Endpoint | Opis |
|---|---|
| `POST /webhook/ado` | Odbiorca service hooków ADO. Odpowiada `200 OK` natychmiast, przetwarza asynchronicznie. Pole `request_id` w odpowiedzi umożliwia korelację logów. |
| `GET /health` | Probe liveness/readiness dla Container Apps. |

---

## Logi i obserwowalność

Logi są emitowane jako JSON. Każde zdarzenie zawiera pole `request_id`
(przekazane nagłówkiem `X-Request-ID` / `X-Correlation-ID` lub losowo wygenerowane).
Znane formaty sekretów i tokenów są redagowane przed zapisem do logów.

Opcjonalnie można włączyć integrację z **Langfuse** przez zmienne środowiskowe:

```bash
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
```

Konfiguracja obserwowalności w `.ado-ai-review.yml`:

```yaml
observability:
  langfuse:
    enabled: true
    trace_pr_reviews: true
    capture_token_usage: true
    capture_costs: true
    capture_prompts: false       # tylko do debugowania
    capture_code_context: false  # tylko do debugowania
```
