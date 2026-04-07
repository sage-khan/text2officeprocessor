#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/switch-llm-backend.sh <ollama|vllm> [--start]

Examples:
  scripts/switch-llm-backend.sh ollama
  scripts/switch-llm-backend.sh vllm --start
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

BACKEND="$1"
START_FLAG="${2:-}"

if [[ "$BACKEND" != "ollama" && "$BACKEND" != "vllm" ]]; then
  echo "Error: backend must be 'ollama' or 'vllm'."
  usage
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG_RUNTIME="$ROOT_DIR/config/llm_config.yaml"
CFG_BUNDLED="$ROOT_DIR/src/data/config/llm_config.yaml"

if [[ ! -f "$CFG_RUNTIME" || ! -f "$CFG_BUNDLED" ]]; then
  echo "Error: llm_config.yaml files not found."
  exit 1
fi

python - "$BACKEND" "$CFG_RUNTIME" "$CFG_BUNDLED" <<'PY'
import sys
from pathlib import Path
import yaml

backend = sys.argv[1]
targets = [Path(sys.argv[2]), Path(sys.argv[3])]

for path in targets:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg["default_provider"] = backend
    providers = cfg.setdefault("providers", {})
    providers.setdefault("ollama", {})
    providers.setdefault("vllm", {})

    if backend == "ollama":
        providers["ollama"].setdefault("base_url", "http://localhost:11434")
        providers["ollama"]["model"] = providers["ollama"].get("model", "llama3.1:8b")
    else:
        providers["vllm"].setdefault("base_url", "http://localhost:8000/v1")
        providers["vllm"]["model"] = providers["vllm"].get("model", "meta-llama/Llama-3.1-8B-Instruct")

    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
PY

echo "Switched default LLM backend to: $BACKEND"
echo "Updated:"
echo "  - $CFG_RUNTIME"
echo "  - $CFG_BUNDLED"

if [[ "$START_FLAG" == "--start" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found; cannot start backend container."
    exit 1
  fi

  if [[ "$BACKEND" == "ollama" ]]; then
    docker compose -f "$ROOT_DIR/docker-compose.yml" --profile llm up -d ollama
    echo "Started ollama profile."
  else
    # vLLM image/model layers are large; fail early if disk is too low.
    avail_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
    min_kb=$((25 * 1024 * 1024)) # 25 GB
    if [[ "$avail_kb" -lt "$min_kb" ]]; then
      echo "Not enough free disk for vLLM startup."
      echo "Need at least ~25GB free on /, found $((avail_kb / 1024 / 1024))GB."
      echo "Switch completed, but vLLM service was not started."
      exit 2
    fi
    docker compose -f "$ROOT_DIR/docker-compose.yml" --profile vllm up -d vllm
    echo "Started vllm profile."
  fi
fi
