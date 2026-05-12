# Azure Marketplace — Managed Application offer (research)

> Research date: 2026-05-09

## Co to jest i jak się nazywa

Mechanizm nosi nazwę **Azure Application offer** w Microsoft Marketplace. Ma dwa warianty planów:

| Typ planu | Rozliczany przez Marketplace? | Kto zarządza po deploy? | Kiedy używać |
|---|---|---|---|
| **Managed Application** | Tak | Publisher ma dostęp; klient ma konfigurowalny dostęp | SaaS-style produkt żyjący w tenancie klienta |
| **Solution Template** | Nie | Klient przejmuje pełną kontrolę | Darmowe toolkity, deploy-and-hand-off |

Dla webhooka + AI service z możliwością monetyzacji → **Managed Application**.

Nie mylić z:
- **Azure Managed Service** (Lighthouse — dla MSP zarządzających istniejącymi subskrypcjami)
- **Container offers** (klient sam deployuje obrazy do AKS/ACI)
- **SaaS offers** (wszystko działa w tenancie publishera)

Dokumentacja: [Plan an Azure Application offer](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/plan-azure-application-offer)

---

## Wymagane pliki konfiguracyjne

Pakiet to **plik `.zip`** (max 120 MB) uploadowany do Partner Center. Dwa pliki muszą być w root zip:

### `mainTemplate.json` (wymagany)

Standardowy ARM template (JSON) definiujący zasoby Azure deployowane w subskrypcji klienta.

Ograniczenia:
- Tylko ARM `languageVersion 1.0` (nie 2.0)
- Można pisać w **Bicep** i kompilować: `bicep build` → JSON musi zostać na languageVersion 1.0
- Wszystkie zasoby lądują w **subskrypcji klienta** w managed resource group

Szkielet:
```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "location": { "type": "string", "defaultValue": "[resourceGroup().location]" }
  },
  "resources": [
    {
      "type": "Microsoft.App/containerApps",
      "apiVersion": "2024-03-01",
      "name": "my-webhook-app"
    }
  ]
}
```

### `createUiDefinition.json` (wymagany)

Definiuje wizard w Azure Portal pokazywany klientowi przy zakupie. Klient wypełnia parametry (lokalizacja, klucze OpenAI, itp.) mapowane na parametry `mainTemplate.json`.

Szkielet:
```json
{
  "$schema": "https://schema.management.azure.com/schemas/0.1.2-preview/CreateUIDefinition.MultiVm.json#",
  "handler": "Microsoft.Azure.CreateUIDef",
  "version": "0.1.2-preview",
  "parameters": {
    "basics": [],
    "steps": [
      {
        "name": "config",
        "label": "Configuration",
        "elements": [
          {
            "name": "openAiEndpoint",
            "type": "Microsoft.Common.TextBox",
            "label": "Azure OpenAI Endpoint",
            "constraints": { "required": true }
          }
        ]
      }
    ],
    "outputs": {
      "openAiEndpoint": "[steps('config').openAiEndpoint]"
    }
  }
}
```

Opcjonalne pliki w zip:
- `nestedtemplates/` — zagnieżdżone ARM templates
- `artifacts/` — skrypty deploymentowe, konfiguracje kontenerów
- `viewDefinition.json` — customizacja widoku w portalu klienta

Docs:
- [CreateUiDefinition overview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/managed-applications/create-uidefinition-overview)
- [Publish service catalog app](https://learn.microsoft.com/en-us/azure/azure-resource-manager/managed-applications/publish-service-catalog-app)

---

## Co można deployować

Dowolny zasób ARM. Dla webhook + Azure OpenAI:

| Zasób | ARM type | Uwagi |
|---|---|---|
| **Azure Container Apps** | `Microsoft.App/containerApps` + `Microsoft.App/managedEnvironments` | Najlepszy fit: serverless, skaluje do zera, native HTTP/webhook |
| **Azure Functions** | `Microsoft.Web/sites` (kind: functionapp) | Event-driven webhook; działa też na Container Apps |
| **Azure OpenAI** | `Microsoft.CognitiveServices/accounts` | Klient dostaje własną instancję OpenAI w swojej sub |
| **Storage Account** | `Microsoft.Storage/storageAccounts` | Kolejki, blob, storage dla Functions |
| **Key Vault** | `Microsoft.KeyVault/vaults` | Bezpieczne przechowywanie sekretów klienta |
| **Managed Identity** | `Microsoft.ManagedIdentity/userAssignedIdentities` | RBAC auth z apki do OpenAI (bez kluczy) |

Ograniczenie: Solution Templates **nie** wspierają kontenerów/AKS. Managed Application — tak.

---

## Co to jest "Azure Foundry"

Trzy możliwe znaczenia:

### A) Microsoft Foundry (dawniej Azure AI Foundry) — najczęstsze znaczenie
- Azure AI Foundry został **przemianowany na Microsoft Foundry** pod koniec 2025
- Ujednolicona platforma AI Microsoftu: katalog modeli, agent framework, tracing, evals
- **Nie jest typem oferty Marketplace** — to platforma na której budujesz aplikację
- Publisherzy mogą publikować modele/agenty *do* katalogu Foundry (osobny flow od Marketplace)
- W kontekście oferty Marketplace: twój `mainTemplate.json` deployuje `Microsoft.CognitiveServices/accounts`, a kod aplikacji go woła
- Docs: [What is Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry)

### B) Azure Developer CLI (azd)
- CLI tool do scaffoldingu i deploymentu przez `azure.yaml` + Bicep/ARM
- **Narzędzie deweloperskie**, nie mechanizm publikacji do Marketplace
- Można użyć azd templates jako źródła, potem skompilować do formatu ARM dla Marketplace

### Wniosek
"Azure Foundry" = Microsoft Foundry (platforma AI), nie mechanizm deploymentu. Pakiet Marketplace to ARM/Bicep, nie `azure.yaml`.

---

## Billing — kto płaci za co

### Infrastruktura → klient płaci
- Wszystkie zasoby z `mainTemplate.json` lądują w **subskrypcji klienta**
- Klient jest rozliczany przez Microsoft za zużycie zasobów (compute, tokeny OpenAI, storage, itp.)
- Publisher ma **zero kosztów infrastruktury** przy deploymencie do klienta

### Opłata za oprogramowanie → publisher pobiera (opcjonalnie)
- **Flat monthly rate** (np. $99/miesiąc za licencję / support)
- **Metered dimensions** (np. $0.005 za wywołanie API, raportowane przez [Marketplace Metering Service API](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/azure-app-metered-billing))
- Opłaty widoczne jako osobna pozycja na fakturze Azure klienta
- Microsoft pobiera ~3% revenue share (obniżone z historycznych 20%)

Docs:
- [Azure Managed Application billing — under the hood](https://azure.microsoft.com/en-us/blog/azure-managed-application-in-azure-marketplace-under-the-hood/)
- [Metered billing for managed applications](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/azure-app-metered-billing)

---

## Kroki publishera — jak stworzyć ofertę

### Pre-requisites
1. Zarejestruj się w [Microsoft AI Cloud Partner Program](https://partner.microsoft.com) (bezpłatnie)
2. Utwórz konto Partner Center i zarejestruj się w commercial marketplace
3. Zweryfikowana tożsamość biznesowa (wymagana dla ofert transactable)

### Krok po kroku

**1. Zbuduj pakiet deploymentowy**
- Napisz `mainTemplate.json` (ARM, languageVersion 1.0)
- Napisz `createUiDefinition.json` (wizard portalu)
- Testuj w [CreateUiDefinition Sandbox](https://portal.azure.com/#blade/Microsoft_Azure_CreateUIDef/SandboxBlade)
- Spakuj oba pliki do root zip → `app.zip`

**2. Utwórz ofertę w Partner Center**
- Partner Center → Marketplace offers → "+ New offer" → "Azure Application"
- Ustaw Offer ID (permanentny, URL-safe slug)
- Uzupełnij listing: tytuł, opis, kategorie (wybierz "AI + Machine Learning"), loga, screenshoty

**3. Skonfiguruj plan**
- Utwórz plan → typ: **Managed Application**
- Ustaw cenę (flat monthly + opcjonalne metered dimensions)
- Upload `app.zip`
- Ustaw authorizations: które tożsamości w tenancie publishera mają jaką rolę RBAC (Owner/Contributor) na managed RG klienta
- Wybierz poziom dostępu klienta: pełny lub deny assignment (zablokowany przez publishera)
- Tryb deploymentu: Incremental (zalecany) lub Complete

**4. Integracja techniczna (dla metered billing)**
- Zarejestruj aplikację Microsoft Entra w swoim tenancie
- Twoja aplikacja woła Marketplace Metering Service API do raportowania użycia

**5. Testowanie**
- Submit to preview → deploy managed app w swojej subskrypcji z linku preview Marketplace
- Zweryfikuj: zasoby tworzone poprawnie, wizard UI działa, authorizations lądują prawidłowo

**6. Publikacja**
- Submit do certyfikacji Microsoft (~3–5 dni roboczych)
- Certyfikacja sprawdza: poprawność ARM template, createUiDefinition, polityki bezpieczeństwa

Docs:
- [Create an Azure application offer](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/azure-app-offer-setup)
- [Configure a managed application plan](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/azure-app-managed)
- [Lab 1: Publishing an Azure Managed Application Offer](https://microsoft.github.io/Mastering-the-Marketplace/ama/labs/lab-1-partner-center/)

---

## Rekomendacja dla webhook receiver + Azure OpenAI

**Azure Managed Application** to właściwy wybór, ponieważ:

1. **Data sovereignty** — enterprise klienci wymagają by dane (payloady webhooków, outputy AI) nie opuszczały ich subskrypcji Azure
2. **Zero kosztów infrastruktury dla publishera** — wszystko działa w subskrypcji klienta
3. **Publisher ma dostęp do zasobów** — można pushować aktualizacje, monitorować stan
4. **Idealny stack w `mainTemplate.json`**:
   - `Microsoft.App/managedEnvironments` — środowisko Container Apps
   - `Microsoft.App/containerApps` — kontener webhooka (skaluje do zera)
   - `Microsoft.CognitiveServices/accounts` (kind: `OpenAI`) — własna instancja OpenAI klienta
   - `Microsoft.ManagedIdentity/userAssignedIdentities` — RBAC auth kontener → OpenAI
   - `Microsoft.Storage/storageAccounts` — kolejkowanie/async
   - `Microsoft.KeyVault/vaults` — sekrety

Dla małych teamów bez wymagań data sovereignty → **SaaS offer** jest prostszy (bez ARM templating, bez zarządzania resource groups per klient).

### Porównanie typów ofert

| Kryterium | SaaS | Managed Application | Container | Solution Template |
|---|---|---|---|---|
| Zasoby w sub klienta | Nie | Tak | Tak | Tak |
| Publisher płaci za infra | Tak | Nie | Nie | Nie |
| Transactable billing | Tak | Tak | Tak | Nie |
| Publisher ma dostęp po deploy | N/A | Tak | Nie | Nie |
| Dane w tenancie klienta | Nie | Tak | Tak | Tak |
| Portal wizard (createUiDefinition) | Nie | Tak | Nie | Tak |
| Metered billing | Tak | Tak | Ograniczony | Nie |

---

## Słownik pojęć

| Termin | Znaczenie |
|---|---|
| **Azure Application offer** | Typ oferty Marketplace (nadrzędny) |
| **Managed Application plan** | Sub-typ: zasoby w sub klienta, publisher ma dostęp, transactable |
| **Solution Template plan** | Sub-typ: zasoby w sub klienta, klient przejmuje, nie transactable |
| **mainTemplate.json** | ARM template definiujący zasoby po stronie klienta |
| **createUiDefinition.json** | JSON wizarda portalu do zbierania parametrów przy zakupie |
| **Managed Resource Group** | RG tworzona w sub klienta zawierająca wszystkie deployowane zasoby |
| **Authorizations** | Przypisania RBAC dające tożsamości publishera dostęp do managed RG |
| **Deny assignment** | Blokuje klienta przed modyfikacją managed RG (opcjonalne) |
| **Metering Service API** | REST API do raportowania billable usage dimensions |
| **Microsoft Foundry** | Platforma AI (katalog modeli, agent builder) — dawniej Azure AI Foundry; nie typ deploymentu |
| **azd** | Azure Developer CLI — narzędzie deweloperskie, nie mechanizm Marketplace |
| **Partner Center** | Portal publishera: partner.microsoft.com/dashboard |

---

## Źródła

- [Plan an Azure Application offer](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/plan-azure-application-offer)
- [Plan a Managed Application](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/plan-azure-app-managed-app)
- [Configure a managed application plan](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/azure-app-managed)
- [CreateUiDefinition overview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/managed-applications/create-uidefinition-overview)
- [Metered billing for managed applications](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/azure-app-metered-billing)
- [Publishing guidance for AI apps and agents](https://learn.microsoft.com/en-us/partner-center/marketplace-offers/artificial-intelligence-app-agent-publishing-guidance)
- [AI apps and agents: choosing your Marketplace offer type](https://techcommunity.microsoft.com/blog/marketplace-blog/ai-apps-and-agents-choosing-your-marketplace-offer-type/4505694)
- [Production-ready architectures for AI apps on Marketplace](https://techcommunity.microsoft.com/blog/marketplace-blog/production-ready-architectures-for-ai-apps-and-agents-on-marketplace/4506377)
- [What is Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry)
- [Mastering the Marketplace: Azure Managed Application labs](https://microsoft.github.io/Mastering-the-Marketplace/ama/)
