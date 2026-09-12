#!/usr/bin/env bash
# Install Tier 1 comparative benchmark dependencies (macOS/Linux).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MEMEX_VERSION="v0.6.0"
LOCAL_MEMORY_PKG="@studiomeyer/local-memory-mcp@1.0.7"

echo "==> Battery benchmark deps"

# Prefer Hermes/local Node (v20+) when present — avoids better-sqlite3 ABI mismatch in npx cache.
if [[ -x "${HOME}/.local/bin/node" ]]; then
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# Go (memex)
if ! command -v go >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Installing Go via Homebrew..."
    brew install go
  else
    echo "ERROR: Go not found. Install Go 1.22+ from https://go.dev/dl/"
    exit 1
  fi
fi
export PATH="$(go env GOPATH)/bin:${PATH:-}"

echo "==> memex ${MEMEX_VERSION}"
go install "github.com/kioie/memex/cmd/memex@${MEMEX_VERSION}"
memex version
memex doctor

# Node (local-memory-mcp)
if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: Node 20+ required for local-memory-mcp. Install from https://nodejs.org/"
  exit 1
fi
NODE_VER="$(node --version)"
echo "Node: ${NODE_VER}"

echo "==> Warming npx cache for ${LOCAL_MEMORY_PKG}"
NPX_LOG="$(mktemp)"
if ! npx -y "${LOCAL_MEMORY_PKG}" </dev/null >"${NPX_LOG}" 2>&1 &
then
  echo "ERROR: npx failed to start"
  exit 1
fi
NPX_PID=$!
sleep 5
if ! kill "${NPX_PID}" 2>/dev/null; then
  wait "${NPX_PID}" || true
fi
if grep -q "NODE_MODULE_VERSION" "${NPX_LOG}"; then
  echo "WARN: better-sqlite3 ABI mismatch — clearing npx cache and retrying..."
  rm -rf "${HOME}/.npm/_npx" 2>/dev/null || true
  npx -y "${LOCAL_MEMORY_PKG}" </dev/null &
  NPX_PID=$!
  sleep 8
  kill "${NPX_PID}" 2>/dev/null || true
elif grep -q "Database ready" "${NPX_LOG}" || grep -q "ready —" "${NPX_LOG}"; then
  echo "local-memory-mcp OK"
else
  echo "WARN: unexpected npx output (check Node version >= 20):"
  tail -5 "${NPX_LOG}"
fi
rm -f "${NPX_LOG}"

# Battery Python deps + ChromaDB baseline (G2b)
echo "==> Battery (uv sync + chromadb for G2b)"
cd "${ROOT}"
uv sync
uv pip install "chromadb==1.0.7"

if [[ ! -f "${ROOT}/vendor/sediment-benchmark/dataset/memories.jsonl" ]]; then
  echo "==> Sediment benchmark submodule"
  git -C "${ROOT}" submodule update --init vendor/sediment-benchmark
fi

echo ""
echo "Done. Add to your shell profile:"
echo "  export PATH=\"\$(go env GOPATH)/bin:\${HOME}/.local/bin:\$PATH\""
echo ""
echo "Verify:"
echo "  memex version && memex doctor"
echo "  node --version"
echo ""
echo "Run full Tier 1 benchmark:"
echo "  uv run battery eval --comparative --systems battery,memex,local-memory-mcp --phases retrieval --write-report"
