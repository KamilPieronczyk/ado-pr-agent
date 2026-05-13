# Jak działa agent — autoryzacja, repozytoria, gałęzie i narzędzia

---

## Autoryzacja

Agent obsługuje dwie strategie uwierzytelniania w Azure DevOps, wybierane przez `ADO_AUTH_MODE`.

### `entra` (domyślnie — produkcja)

Klasa: `EntraAdoAuthStrategy`

Używa `DefaultAzureCredential` z Azure Identity SDK, które automatycznie próbuje kolejnych źródeł:

1. Zmienne środowiskowe (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`)
2. Workload Identity (AKS)
3. Managed Identity (Container Apps, VM)
4. Azure CLI (`az login`)
5. Azure PowerShell, Azure Developer CLI

Token jest pobierany dla zakresu `499b84ac-1321-427f-aa17-267ca6975798/.default`
(oficjalny identyfikator Azure DevOps w Microsoft Entra).

Token jest przekazywany:
- jako nagłówek `Authorization: Bearer <token>` do REST API
- jako `GIT_CONFIG_VALUE_0: AUTHORIZATION: bearer <token>` do operacji `git clone` / `git push`

Token **nigdy nie jest logowany** — jego wartość jest dodawana do listy sekretów do redakcji
przed każdą operacją wyjścia.

### `pat` (lokalnie / testy)

Klasa: `PatAdoAuthStrategy`

Wymaga zmiennej `ADO_PAT`. Token jest zakodowany Base64 (`:<PAT>`) i przekazywany jako
`Authorization: Basic <base64>` w nagłówkach HTTP i konfiguracji git.

Wartość PAT jest redagowana we wszystkich logach.

---

## Jak agent wybiera repozytorium

### Tryb webhook

1. Agent odbiera payload ADO service hook (`POST /webhook/ado`).
2. Z payloadu odczytuje:
   - `remote_url` — URL repozytorium git
   - `source_ref_name` — gałąź źródłowa PR (np. `refs/heads/feature/xyz`)
   - `repository_id`, `project_name`, `organization_url`
3. Jeśli zdarzenie to `flat-comment` (komentarz PR bez pełnego kontekstu repo),
   agent robi dodatkowe zapytanie GET do ADO REST API, żeby pobrać brakujące dane PR.
4. Repozytorium jest **klonowane shallow** (`--depth 50`) do tymczasowego katalogu
   (`/tmp/<request_id>/`) za pomocą uwierzytelnionego `git clone`.
5. Po zakończeniu obsługi temp dir jest usuwany.

Klonowanie odbywa się tylko do gałęzi źródłowej PR — agent nigdy nie klonuje całej historii.

### Tryb lokalny (`local`)

Agent działa w katalogu bieżącym (tam, gdzie wywołano komendę).
Nie klonuje żadnego repozytorium — używa lokalnego repozytorium git.
Diff jest obliczany jako `git diff origin/<target-branch>...HEAD`.

---

## Jak agent tworzy gałęzie i commity (`/ai fix`)

Komenda `/ai fix` jest jedyną, która modyfikuje kod. Pozostałe (`review`, `security`)
są tylko do odczytu.

### Polityka mechanicznych napraw (`MechanicalFixPolicy`)

Zanim agent zastosuje jakąkolwiek poprawkę, sprawdza, czy kandydat należy do
**whitelisty mechanicznych zmian**:

Dozwolone słowa kluczowe w tytule/wyjaśnieniu poprawki:
`format`, `formatting`, `lint`, `import`, `imports`, `rename`, `type`, `typing`, `test`, `mechanical`

Blokowane słowa (odrzucane zawsze):
`business`, `pricing`, `discount`, `authorization behavior`

Poprawki biznesowe, algorytmiczne i zmiany kontraktów API są zawsze odrzucane.

### Przepływ tworzenia gałęzi fix

1. Model LLM zwraca listę kandydatów `FixCandidate` z polami:
   - `file_path` — ścieżka pliku do zmiany (względna, wewnątrz workspace)
   - `replacement` — **pełna nowa zawartość pliku** (nie diff)
   - `commit_message` — wiadomość commita
   - `delivery` — `FIX_BRANCH_CANDIDATE` lub `INLINE_SUGGESTION`
2. `MechanicalFixer.apply_commits()` filtruje kandydatów przez politykę.
3. Tworzy nową gałąź lokalnie: `git checkout -B <branch_name>`
4. Dla każdego kandydata:
   - Weryfikuje ścieżkę przez `WorkspaceBoundary` (blokuje `../`, linki symboliczne, ścieżki bezwzględne poza workspace)
   - Zapisuje pełną zawartość pliku (`safe_write_text`)
   - `git add <file_path>`
   - `git commit -m "<commit_message>"` — każda poprawka to osobny commit
5. `git push origin <branch_name>`
6. ADO REST API: tworzy PR z gałęzi fix do gałęzi docelowej PR

### Nazewnictwo gałęzi fix

Szablon konfigurowalny w `.ado-ai-review.yml`:
```yaml
fix:
  branch:
    name_template: ai-fix/pr-{pr_id}/{run_id}
```

Przykład: `ai-fix/pr-1234/webhook`

Poprawki **nigdy** nie trafiają bezpośrednio do gałęzi PR — zawsze do osobnej gałęzi fix.

---

## Narzędzia agenta

Agent dysponuje dwoma zestawami narzędzi działającymi wyłącznie przez Pythona
(model LLM nie ma bezpośredniego dostępu do shella).

### GitToolset

Wszystkie polecenia git są walidowane przez `CommandPolicy` przed wykonaniem.

| Metoda | Polecenie | Opis |
|---|---|---|
| `fetch(remote)` | `git fetch <remote> --prune` | Aktualizuje referencje remote |
| `diff(ref_range, unified)` | `git diff --unified=<n> <range>` | Pobiera diff między gałęziami |
| `name_status(ref_range)` | `git diff --name-status <range>` | Lista zmienionych plików |
| `checkout_new_branch(branch)` | `git checkout -B <branch>` | Tworzy/resetuje gałąź lokalnie |
| `add(paths)` | `git add <paths>` | Staguje pliki do commita |
| `commit(message)` | `git commit -m <msg>` + `git rev-parse HEAD` | Commituje i zwraca SHA |
| `push(remote, branch)` | `git push <remote> <branch>` | Wypycha gałąź do remote |
| `clone(remote_url, branch, ...)` | `git clone --depth 50 --branch <branch>` | Klonuje shallow |

### AdoToolset

Wszystkie zapytania HTTP idą przez `AdoRestClient` z nagłówkiem autoryzacyjnym strategii.

| Metoda | HTTP | Opis |
|---|---|---|
| `show_pr()` | `GET .../pullRequests/<pr_id>` | Pobiera metadane PR |
| `create_pr(source, target, title, desc)` | `POST .../pullRequests` | Tworzy PR gałęzi fix |
| `list_pr_threads()` | `GET .../pullRequests/<id>/threads` | Pobiera wszystkie wątki PR |
| `list_iterations()` | `GET .../pullRequests/<id>/iterations` | Lista iteracji PR |
| `list_iteration_changes(iter_id)` | `GET .../iterations/<id>/changes` | Lista zmienionych plików w iteracji |
| `create_pr_thread(body)` | `POST .../pullRequests/<id>/threads` | Publikuje komentarz/wynik przeglądu |

### CommandPolicy — allowlista poleceń shell

Model LLM nigdy nie wykonuje poleceń shell bezpośrednio. Każde polecenie przechodzi przez
`CommandPolicy.validate()`, która odrzuca wszystko, czego nie ma na liście dozwolonych kształtów.

Dozwolone polecenia (`git`):

```
git status
git status --short
git diff [--unified=N] [--name-status] <ref-range>
git fetch <remote> --prune
git checkout -B <branch>
git add <path> [<path>...]
git commit -m <message>
git rev-parse HEAD
git rev-parse --abbrev-ref HEAD
git show <ref>
git push <remote> <branch>
git clone --depth <n> --branch <branch> https://dev.azure.com/... <dest>
```

Dozwolone polecenia (`gh`):

```
gh auth token
```

Każdy inny kształt polecenia jest odrzucany z błędem `CommandRejectedError`.
Dodatkowe zabezpieczenia: `@` w URL clone, flagi `-c`/`--config`, ścieżki z `..` lub `\`.

---

## WorkspaceBoundary — izolacja plików

Wszystkie operacje odczytu i zapisu plików przechodzą przez `WorkspaceBoundary`,
który zapewnia, że agent nie może:

- wyjść poza katalog roboczy przez `../`
- używać ścieżek bezwzględnych wskazujących poza workspace
- czytać ani pisać przez linki symboliczne
- zapisywać do katalogu zawierającego symlinkowy przodek

Naruszenie któregokolwiek z tych warunków rzuca `WorkspaceBoundaryError` i przerywa operację.

---

## Scanner sekretów (pre-LLM)

Przed każdym wywołaniem LLM diff jest skanowany przez `SecurityScanner.scan_diff()`.
Wzorce wykrywanych sekretów:

- Generyczne przypisania: `api_key = "..."`, `password = "..."`, `secret = "..."`
- Tokeny OpenAI: `sk-...`
- AWS Access Key ID: `AKIA...`
- AWS Secret Access Key (40 znaków base64)
- GitHub PAT: `ghp_...`, `gho_...`, `ghu_...`, `ghs_...`, `ghr_...`, `github_pat_...`
- Klucze PEM: `-----BEGIN ... PRIVATE KEY-----`
- Azure connection strings / SAS tokens

Znalezione wartości są zastępowane przez `[REDACTED_SECRET]` w diffie przekazywanym do modelu
i dodawane jako oddzielne wyniki `CRITICAL` w raporcie przeglądu.
