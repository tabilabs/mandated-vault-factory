#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing command: $cmd" >&2
    exit 1
  }
}

is_placeholder() {
  local value="$1"
  [[ -z "$value" || "${value:0:1}" == "<" ]]
}

deployment_record_complete() {
  local file="$1"
  local factory
  local factory_codehash
  local factory_leaf
  local venus
  local pancake
  local venus_codehash
  local pancake_codehash
  local venus_leaf
  local pancake_leaf

  factory="$(jq -r '.factory // ""' "$file")"
  factory_codehash="$(jq -r '.factoryCodehash // ""' "$file")"
  factory_leaf="$(jq -r '.factoryLeaf // ""' "$file")"
  venus="$(jq -r '.adapters.venus // ""' "$file")"
  pancake="$(jq -r '.adapters.pancakeswap // ""' "$file")"
  venus_codehash="$(jq -r '.adapterCodehashes.venus // ""' "$file")"
  pancake_codehash="$(jq -r '.adapterCodehashes.pancakeswap // ""' "$file")"
  venus_leaf="$(jq -r '.adapterLeaves.venus // ""' "$file")"
  pancake_leaf="$(jq -r '.adapterLeaves.pancakeswap // ""' "$file")"

  is_placeholder "$factory" && return 1
  is_placeholder "$factory_codehash" && return 1
  is_placeholder "$factory_leaf" && return 1
  is_placeholder "$venus" && return 1
  is_placeholder "$pancake" && return 1
  is_placeholder "$venus_codehash" && return 1
  is_placeholder "$pancake_codehash" && return 1
  is_placeholder "$venus_leaf" && return 1
  is_placeholder "$pancake_leaf" && return 1

  return 0
}

require_cmd bash
require_cmd forge
require_cmd jq

: "${BSC_MAINNET_RPC:?BSC_MAINNET_RPC is required}"

DEPLOYMENT_FILE="${DEPLOYMENT_FILE:-deployments/bsc-mainnet.json}"
REQUIRE_COMPLETE_DEPLOYMENT_RECORD="${REQUIRE_COMPLETE_DEPLOYMENT_RECORD:-0}"

if [[ ! -f "$DEPLOYMENT_FILE" ]]; then
  echo "Missing deployment file: $DEPLOYMENT_FILE" >&2
  exit 1
fi

echo "== BSC Mainnet Readiness =="
echo "rpc: $BSC_MAINNET_RPC"
echo "deployment_file: $DEPLOYMENT_FILE"
echo "require_complete_deployment_record: $REQUIRE_COMPLETE_DEPLOYMENT_RECORD"

echo
echo "== Step 1: Wrapper Preflight =="
DEPLOY_BROADCAST=0 bash scripts/deploy-bsc-mainnet.sh

echo
echo "== Step 2: Protocol Anchors =="
forge test --match-path test/VaultForkBscMainnet.ProtocolAnchors.t.sol --fork-url "$BSC_MAINNET_RPC"

if deployment_record_complete "$DEPLOYMENT_FILE"; then
  echo
  echo "deployment record status: complete"
elif [[ "$REQUIRE_COMPLETE_DEPLOYMENT_RECORD" == "1" ]]; then
  echo
  echo "deployment record status: incomplete" >&2
  echo "REQUIRE_COMPLETE_DEPLOYMENT_RECORD=1, refusing to continue with incomplete project deployment fields." >&2
  exit 1
else
  echo
  echo "deployment record status: incomplete (expected before first mainnet broadcast)"
fi

echo
echo "== Step 3: Deployed Consistency =="
forge test --match-path test/VaultForkBscMainnet.DeployedConsistency.t.sol --fork-url "$BSC_MAINNET_RPC"

echo
echo "BSC mainnet readiness checks completed."
