# Codex Proxy

**Unified multi-provider proxy for [Codex CLI](https://github.com/openai/codex).**

Route vos modèles préférés (OpenCode, NVIDIA NIM, DeepSeek, etc.) vers Codex CLI via un seul port, sans ChatGPT account.

```
┌──────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Codex    │────▶│  codex-proxy     │────▶│  OpenCode       │
│ CLI      │     │  :4444           │     │  (opencode.ai)  │
│          │     │                  │     ├─────────────────┤
│ model:   │     │  codex-relay × N │────▶│  NVIDIA NIM     │
│ qwen3.5  │     │  (one per        │     │  (nvidia.com)   │
│ provider:│     │   provider)      │     ├─────────────────┤
│ opencode │     └──────────────────┘     │  DeepSeek       │
└──────────┘                               │  (api.deepseek) │
                                           └─────────────────┘
```

## ✨ Features

- **Multi-provider** — Un seul port `:4444`, chaque provider sur sa route (`/opencode`, `/nvidia`, etc.)
- **Unified API** — Traduction automatique `/v1/responses` ↔ `/v1/chat/completions` via [codex-relay](https://github.com/opencode-ai/codex-relay)
- **Dockerized** — `docker compose up -d` et c'est prêt
- **BYO keys** — Chaque provider avec sa propre clé API dans `providers.yaml`
- **Codex native** — Pas de wrapper boiteux, Codex parle directement en `responses` format

## 🚀 Quick Start

### 1. Config

```bash
git clone <repo-url>
cd codex-proxy
cp providers.yaml.example providers.yaml
```

Éditez `providers.yaml` :

```yaml
providers:
  - name: opencode
    upstream: https://opencode.ai/zen/v1
    api_key: "sk-votre-cle-ici"     # ← en clair, pas de b64 nécessaire

  - name: nvidia
    upstream: https://integrate.api.nvidia.com/v1
    api_key: "nvapi-votre-cle-ici"

  # Ajoutez-en autant que vous voulez
  # - name: deepseek
  #   upstream: https://api.deepseek.com/v1
  #   api_key: "sk-votre-cle-ici"
```

### 2. Docker

```bash
docker compose build
docker compose up -d
```

### 3. Codex CLI

Dans `~/.codex/config.toml` :

```toml
[model_providers.opencode]
name = "OpenCode"
base_url = "http://127.0.0.1:4444/opencode/v1"
wire_api = "responses"
# Pas besoin de clé — le proxy la gère

[model_providers.nvidia]
name = "NVIDIA NIM"
base_url = "http://127.0.0.1:4444/nvidia/v1"
wire_api = "responses"
```

### 4. Utilisation

```bash
# Interface interactive (recommandé)
codex -m deepseek-v4-flash-free -c model_provider=opencode

codex -m qwen/qwen3.5-397b-a17b -c model_provider=nvidia

# En one-shot (pour scripts / automation)
codex exec -m deepseek-v4-flash-free -c model_provider=opencode "ta question"
```

> ⚠️ **Important** : utilisez `-c model_provider=<nom>` (singulier), PAS `model_providers.override`. Sans `-c model_provider=...`, Codex utilisera son provider par défaut (ChatGPT).

## 🔧 Configuration

### providers.yaml

```yaml
providers:
  - name: <nom>           # Route → /{name}/v1/responses
    upstream: <url>        # API upstream (chat completions ou responses)
    api_key: "<cle>"       # API key (en clair, ou b64:...)
    format: chat           # chat | responses (défaut: responses)
```

| Format | Description |
|---|---|
| `chat` | Le proxy lance un `codex-relay` qui traduit responses↔chat |
| `responses` | Appel direct à l'upstream en format responses |

**b64 optionnel** : si votre clé commence par `b64:`, le proxy la décode automatiquement. Sinon, laissez-la en clair.

### Endpoints proxy

| Route | Description |
|---|---|
| `/opencode/v1/responses` | Inférence OpenCode |
| `/nvidia/v1/models` | Liste des modèles NVIDIA |
| `/opencode/config` | Bloc TOML à copier dans config.toml |
| `/nvidia/v1/chat/completions` | Compat OpenAI (si l'upstream le supporte) |

## 🏗️ Architecture

```
proxy.py (port 4444)
├── /opencode/* → codex-relay (port 4445) → https://opencode.ai/zen/v1
└── /nvidia/*   → codex-relay (port 4446) → https://integrate.api.nvidia.com/v1
```

Le proxy lit `providers.yaml` et, pour chaque provider en `format: chat`, spawn un processus `codex-relay` qui fait la traduction. Les requêtes entrent en format `responses` (natif Codex), sont converties en `chat` pour l'upstream, et la réponse est reconvertie.

## 🛠️ Troubleshooting

### "Invalid API key"
→ Vérifiez la clé dans `providers.yaml`. Elle doit être identique à celle de votre fournisseur.

### "Provider 'v1' not found"
→ Mauvais chemin. Utilisez `/{nom}/v1/responses`, pas `/v1/responses`.

### Le proxy ne répond pas
```bash
docker logs codex-proxy
curl http://localhost:4444/opencode/config
```

### Changer de provider dans Codex
```bash
# Forcer un provider pour une commande
codex exec -m <model> -c model_provider=<nom>

# Voir la liste des providers reconnus par Codex
codex doctor | grep provider
```

## 📦 Déploiement

### backup / restore

Le projet se résume à 3 fichiers :
- `docker-compose.yml`
- `Dockerfile`
- `server.py`
- `providers.yaml` (vos clés)

Sauvegardez `providers.yaml` — c'est le seul fichier sensible.

### Mettre à jour un provider

1. Modifiez `providers.yaml`
2. Rebuild : `docker compose build`
3. Recreate : `docker compose up -d --force-recreate`

## 📄 License

MIT
