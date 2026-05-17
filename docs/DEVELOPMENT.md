# HearThat — Guide développeur

Tout sur le lancement local, l'authentification Entra ID (sans clés), et le
dépannage rapide. Pour les **conventions de code**, voir
[`.github/copilot-instructions.md`](../.github/copilot-instructions.md).

---

## 1. Prérequis

| Outil | Version | Install |
|---|---|---|
| Python | 3.13+ | https://www.python.org/downloads/ |
| uv | dernière | `winget install astral-sh.uv` ou https://docs.astral.sh/uv/ |
| Azure CLI | 2.60+ | `winget install Microsoft.AzureCLI` |
| FFmpeg *(optionnel — notebooks)* | dernière | `winget install Gyan.FFmpeg` |

---

## 2. Setup en 3 commandes

```powershell
uv sync                          # installe deps depuis uv.lock
Copy-Item .env.example .env      # endpoints (pas de clés !)
# … remplis .env (voir §4)
uv run hearthat ui               # http://127.0.0.1:8000
```

Si l'environnement virtuel n'est pas activé :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

---

## 3. Authentification — `DefaultAzureCredential`

**Aucune clé API n'est lue à l'exécution.** Le code utilise
`DefaultAzureCredential` (voir [`src/hearthat/auth.py`](../src/hearthat/auth.py))
qui essaie ces sources **dans l'ordre** :

1. **`EnvironmentCredential`** — Service Principal via env vars *(recommandé en CI / pour éviter `az login`)*
2. **`WorkloadIdentityCredential`** — pods AKS / Container Apps
3. **`ManagedIdentityCredential`** — VM / App Service / ACI / ACA
4. **`AzureCliCredential`** — `az login` *(dev local par défaut)*
5. **`AzurePowerShellCredential`** — `Connect-AzAccount`
6. **`AzureDeveloperCliCredential`** — `azd auth login`
7. **`InteractiveBrowserCredential`** — popup navigateur (désactivé par défaut)

### Option A — Dev local rapide *(utilise ton compte user)*

```powershell
az login
az account set --subscription "<sub-id-or-name>"
```

### Option B — Service Principal *(évite d'utiliser ton user, idéal pour CI/CD ou poste partagé)*

```powershell
# 1. Crée un SP avec un rôle scoped sur ton RG Azure AI
az ad sp create-for-rbac `
  --name "hearthat-dev-sp" `
  --role "Cognitive Services User" `
  --scopes "/subscriptions/<sub-id>/resourceGroups/<rg>"
```

La commande retourne `appId`, `password`, `tenant`. Ajoute-les dans ton `.env`
(le `Settings` ignore les vars inconnues, et `DefaultAzureCredential` les lit
automatiquement) :

```env
AZURE_CLIENT_ID=<appId>
AZURE_CLIENT_SECRET=<password>
AZURE_TENANT_ID=<tenant>
```

> ⚠️ `.env` est dans `.gitignore` — vérifie avant tout commit.
> Pour la prod, préfère un **certificat** (`AZURE_CLIENT_CERTIFICATE_PATH`) ou
> **OIDC federated identity** plutôt qu'un secret.

### Option C — Managed Identity *(prod sur ACA / App Service / VM)*

Aucune variable nécessaire. Assigne simplement la MI à la ressource compute,
puis donne-lui les rôles RBAC ci-dessous.

---

## 4. Endpoints — `.env`

HearThat lit uniquement des **DNS** dans [`.env`](../.env.example). Minimum vital :

```env
AZURE_OPENAI_ENDPOINT=https://<foundry-project>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_SUMMARY=gpt-5.4-mini
AZURE_OPENAI_DEPLOYMENT_VISION=gpt-5.4-mini
AZURE_OPENAI_DEPLOYMENT_TTS=gpt-4o-mini-tts

AZURE_SPEECH_ENDPOINT=https://eastus.api.cognitive.microsoft.com/
AZURE_SPEECH_REGION=eastus

AZURE_DOCINTEL_ENDPOINT=https://<docintel>.cognitiveservices.azure.com/
```

Variables optionnelles (notebook 03 — traduction) :
`AZURE_TRANSLATOR_ENDPOINT`, `AZURE_STORAGE_ACCOUNT_NAME`.

---

## 5. RBAC requis

Sur chaque ressource Azure, l'identité (user / SP / MI) doit avoir :

| Ressource | Rôle |
|---|---|
| Azure OpenAI (Foundry) | **Cognitive Services User** *(ou OpenAI User)* |
| Azure Speech | **Cognitive Services User** |
| Document Intelligence | **Cognitive Services User** |
| Translator | **Cognitive Services User** |
| Storage account *(traduction)* | **Storage Blob Data Contributor** |

Assignation rapide (exemple OpenAI) :

```powershell
$principal = az ad sp show --id <appId> --query id -o tsv
az role assignment create `
  --assignee-object-id $principal `
  --assignee-principal-type ServicePrincipal `
  --role "Cognitive Services User" `
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<openai-name>"
```

---

## 6. Lancer

```powershell
# UI web (FastAPI + HTMX)
uv run hearthat ui                            # http://127.0.0.1:8000

# Pipeline CLI complet
uv run hearthat run data/samples/*.pdf --backend azure_speech_mai

# TTS one-shot
uv run hearthat tts-openai "Hello" --instructions "warm storyteller"

# Notebooks
uv run python -m ipykernel install --user --name hearthat --display-name "HearThat (uv)"
uv run jupyter lab notebooks/
```

### Docker (mêmes endpoints, même auth)

```powershell
docker compose build
docker compose up                              # UI :8000
docker compose --profile notebooks up          # + Jupyter :8888
```

Le compose monte `~/.azure` en lecture seule → `AzureCliCredential` fonctionne
dans le conteneur. Pour utiliser un SP à la place, passe les 3 env vars
`AZURE_CLIENT_ID/SECRET/TENANT_ID` au conteneur.

---

## 7. Vérifs rapides

```powershell
# Quelle identité résout DefaultAzureCredential ?
uv run python -c "from azure.identity import DefaultAzureCredential; print(DefaultAzureCredential().get_token('https://cognitiveservices.azure.com/.default').token[:20], '...')"

# Compte CLI actif
az account show --query "{user:user.name, tenant:tenantId, sub:name}" -o table

# Endpoints chargés
uv run python -c "from hearthat.config import get_settings; s=get_settings(); print(s.azure_openai_endpoint, s.azure_speech_region)"
```

---

## 8. Dépannage

| Symptôme | Cause probable | Fix |
|---|---|---|
| `DefaultAzureCredential failed to retrieve a token` | Pas connecté | `az login` **ou** set `AZURE_CLIENT_ID/SECRET/TENANT_ID` |
| `403 AuthorizationFailed` sur appel OpenAI/Speech | RBAC manquant | Assigne **Cognitive Services User** sur la ressource |
| `DeploymentNotFound` | Nom de deployment ≠ `.env` | Vérifie dans Foundry → Deployments |
| MAI-Voice-1 → `VoiceNotFound` | Region ≠ `eastus` | Force `AZURE_SPEECH_REGION=eastus` |
| `uv: command not found` | uv pas dans PATH | Redémarre le terminal après install |

---

## 9. Qualité

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

Tout doit passer avant un PR.
