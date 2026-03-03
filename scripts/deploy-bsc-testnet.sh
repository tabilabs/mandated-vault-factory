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

run_file_path() {
  local script_name="$1"
  printf 'broadcast/%s/%s/run-latest.json\n' "$script_name" "$BSC_TESTNET_CHAIN_ID"
}

resolve_foundry_out_dir() {
  local out_dir
  out_dir="$(forge config --json 2>/dev/null | jq -r '.out // empty' || true)"
  if [[ -z "$out_dir" || "$out_dir" == "null" ]]; then
    out_dir="out"
  fi
  printf '%s\n' "$out_dir"
}

SIGNER_ARGS=()
DEPLOY_SIGNER_MODE="${DEPLOY_SIGNER_MODE:-auto}"

configure_signer() {
  local mode="$DEPLOY_SIGNER_MODE"

  case "$mode" in
    auto)
      if [[ -n "${DEPLOYER_ACCOUNT:-}" ]]; then
        mode="account"
      elif [[ "${DEPLOY_USE_LEDGER:-0}" == "1" ]]; then
        mode="ledger"
      elif [[ -n "${DEPLOYER_PRIVATE_KEY:-}" ]]; then
        mode="private-key"
      else
        echo "Signer configuration missing: set DEPLOYER_ACCOUNT, DEPLOY_USE_LEDGER=1, or DEPLOYER_PRIVATE_KEY." >&2
        exit 1
      fi
      ;;
    private-key|account|ledger)
      ;;
    *)
      echo "Unsupported DEPLOY_SIGNER_MODE: $mode (expected auto|private-key|account|ledger)" >&2
      exit 1
      ;;
  esac

  case "$mode" in
    private-key)
      : "${DEPLOYER_PRIVATE_KEY:?DEPLOYER_PRIVATE_KEY is required when DEPLOY_SIGNER_MODE=private-key}"
      SIGNER_ARGS=(--private-key "$DEPLOYER_PRIVATE_KEY")
      ;;
    account)
      : "${DEPLOYER_ACCOUNT:?DEPLOYER_ACCOUNT is required when DEPLOY_SIGNER_MODE=account}"
      SIGNER_ARGS=(--account "$DEPLOYER_ACCOUNT")
      if [[ -n "${DEPLOYER_PASSWORD_FILE:-}" ]]; then
        SIGNER_ARGS+=(--password-file "$DEPLOYER_PASSWORD_FILE")
      elif [[ -n "${DEPLOYER_PASSWORD:-}" ]]; then
        SIGNER_ARGS+=(--password "$DEPLOYER_PASSWORD")
      fi
      ;;
    ledger)
      SIGNER_ARGS=(--ledger)
      if [[ -n "${DEPLOYER_DERIVATION_PATH:-}" ]]; then
        SIGNER_ARGS+=(--mnemonic-derivation-path "$DEPLOYER_DERIVATION_PATH")
      fi
      ;;
  esac

  DEPLOY_SIGNER_MODE="$mode"
}

extract_created_addresses() {
  local run_file="$1"
  jq -r '
  (
    [
      .transactions[]?
      | select(
        (((.transactionType // .type // "") | tostring | ascii_upcase) as $tt
          | ($tt == "" or $tt == "CREATE" or $tt == "CREATE2"))
      )
      | (.contractAddress // .contract_address // empty)
    ]
    +
    [
      .receipts[]?
      | (.contractAddress // .contract_address // empty)
    ]
  )
  | .[]
  | select(type == "string" and test("^0x[0-9a-fA-F]{40}$"))
  ' "$run_file"
}

expected_runtime_codehash() {
  local source_file="$1"
  local contract_name="$2"
  local artifact_path="${FOUNDRY_OUT_DIR}/${source_file}/${contract_name}.json"

  if [[ ! -f "$artifact_path" ]]; then
    artifact_path="$(find "$FOUNDRY_OUT_DIR" -type f -path "*/${source_file}/${contract_name}.json" -print -quit 2>/dev/null || true)"
  fi

  [[ -n "$artifact_path" && -f "$artifact_path" ]] || {
    echo "Missing artifact for $contract_name at ${FOUNDRY_OUT_DIR}/${source_file}/${contract_name}.json" >&2
    exit 1
  }

  local runtime_bytecode
  runtime_bytecode="$(jq -r '.deployedBytecode.object // empty' "$artifact_path")"
  [[ -n "$runtime_bytecode" && "$runtime_bytecode" != "0x" ]] || {
    echo "Missing deployed bytecode for $contract_name in $artifact_path" >&2
    exit 1
  }

  if [[ "$runtime_bytecode" != 0x* ]]; then
    runtime_bytecode="0x${runtime_bytecode}"
  fi

  cast keccak "$runtime_bytecode"
}

extract_contract_address() {
  local script_name="$1"
  local contract_name="$2"
  local source_file="$3"
  local run_file
  run_file="$(run_file_path "$script_name")"

  [[ -f "$run_file" ]] || {
    echo "Missing forge broadcast file: $run_file" >&2
    exit 1
  }

  local parsed
  parsed="$(
    jq -r \
      --arg contract "$contract_name" \
      '
      . as $root
      | def txhash($tx): (($tx.hash // $tx.transactionHash // $tx.txHash // $tx.transaction_hash // "") | tostring | ascii_downcase);
        def receipt_addr_for_hash($h):
          (
            [
              $root.receipts[]?
              | select(((.transactionHash // .txHash // .hash // .transaction_hash // "") | tostring | ascii_downcase) == $h)
              | (.contractAddress // .contract_address // empty)
            ]
            | map(select(type == "string" and test("^0x[0-9a-fA-F]{40}$")))
            | first // empty
          );
      [
        $root.transactions[]?
        | select(
          (((.transactionType // .type // "") | tostring | ascii_upcase) as $tt | ($tt == "CREATE" or $tt == "CREATE2"))
          and ((.contractName // .contract_name // "") == $contract)
        )
        | (
            (.contractAddress // .contract_address // empty),
            (txhash(.) as $h | if $h == "" then empty else receipt_addr_for_hash($h) end)
          )
      ]
      | map(select(type == "string" and test("^0x[0-9a-fA-F]{40}$")))
      | last // empty
      ' \
      "$run_file"
  )"

  if [[ -n "$parsed" ]]; then
    printf '%s\n' "$parsed"
    return 0
  fi

  local expected_codehash
  expected_codehash="$(expected_runtime_codehash "$source_file" "$contract_name")"
  expected_codehash="${expected_codehash,,}"

  local -a codehash_matches=()
  local -A seen=()

  while IFS= read -r candidate; do
    local normalized
    normalized="${candidate,,}"
    if [[ -n "${seen[$normalized]:-}" ]]; then
      continue
    fi
    seen[$normalized]=1

    local actual_codehash
    actual_codehash="$(cast codehash "$candidate" --rpc-url "$BSC_TESTNET_RPC")"
    if [[ "${actual_codehash,,}" == "$expected_codehash" ]]; then
      codehash_matches+=("$candidate")
    fi
  done < <(extract_created_addresses "$run_file")

  if [[ "${#codehash_matches[@]}" -eq 1 ]]; then
    printf '%s\n' "${codehash_matches[0]}"
    return 0
  fi

  if [[ "${#codehash_matches[@]}" -gt 1 ]]; then
    echo "Ambiguous $contract_name address in $run_file: ${#codehash_matches[@]} candidates share codehash $expected_codehash" >&2
    printf '%s\n' "${codehash_matches[@]}" >&2
    echo "Refuse to pick one automatically; inspect broadcast JSON and set addresses manually." >&2
    exit 1
  fi

  echo "Failed to parse $contract_name address from $run_file (schema fallback exhausted)" >&2
  exit 1
}

extract_deployer_address() {
  local run_file="$1"
  local deployer
  deployer="$(
    jq -r '
      [
        .transactions[]?
        | (.from // .transaction.from // .tx.from // empty)
      ]
      | map(select(type == "string" and test("^0x[0-9a-fA-F]{40}$")))
      | last // empty
    ' "$run_file"
  )"

  [[ -n "$deployer" ]] || {
    echo "Failed to parse deployer address from $run_file" >&2
    exit 1
  }

  printf '%s\n' "$deployer"
}

assert_contract_deployed() {
  local contract_address="$1"
  local contract_label="$2"
  local code
  code="$(cast code "$contract_address" --rpc-url "$BSC_TESTNET_RPC")"
  if [[ "$code" == "0x" ]]; then
    echo "$contract_label has no runtime code at $contract_address" >&2
    exit 1
  fi
}

assert_factory_runtime_config() {
  local factory_address="$1"
  local implementation_address
  implementation_address="$(cast call "$factory_address" "implementation()(address)" --rpc-url "$BSC_TESTNET_RPC")" || {
    echo "Factory runtime validation failed: implementation() call failed on $factory_address" >&2
    exit 1
  }
  if [[ "${implementation_address,,}" == "0x0000000000000000000000000000000000000000" ]]; then
    echo "Factory runtime validation failed: implementation() returned zero address" >&2
    exit 1
  fi
  assert_contract_deployed "$implementation_address" "VaultFactory implementation"
}

assert_pancake_adapter_runtime_config() {
  local adapter_address="$1"
  local runtime_router
  runtime_router="$(cast call "$adapter_address" "router()(address)" --rpc-url "$BSC_TESTNET_RPC")" || {
    echo "Pancake adapter runtime validation failed: router() call failed on $adapter_address" >&2
    exit 1
  }
  if [[ "${runtime_router,,}" != "${PANCAKESWAP_V3_ROUTER,,}" ]]; then
    echo "Pancake adapter runtime validation failed: router mismatch, expected $PANCAKESWAP_V3_ROUTER got $runtime_router" >&2
    exit 1
  fi
}

assert_router_compatibility() {
  local factory_from_router
  local wnative_from_router

  factory_from_router="$(cast call "$PANCAKESWAP_V3_ROUTER" "factory()(address)" --rpc-url "$BSC_TESTNET_RPC")" || {
    echo "Router validation failed: factory() call failed on $PANCAKESWAP_V3_ROUTER" >&2
    exit 1
  }

  wnative_from_router="$(cast call "$PANCAKESWAP_V3_ROUTER" "WETH9()(address)" --rpc-url "$BSC_TESTNET_RPC")" || {
    echo "Router validation failed: WETH9() call failed on $PANCAKESWAP_V3_ROUTER" >&2
    exit 1
  }

  if [[ "${factory_from_router,,}" != "${PANCAKESWAP_V3_FACTORY,,}" ]]; then
    echo "Router validation failed: factory mismatch, expected $PANCAKESWAP_V3_FACTORY got $factory_from_router" >&2
    exit 1
  fi

  if [[ "${wnative_from_router,,}" != "${PANCAKESWAP_V3_WNATIVE,,}" ]]; then
    echo "Router validation failed: WETH9 mismatch, expected $PANCAKESWAP_V3_WNATIVE got $wnative_from_router" >&2
    exit 1
  fi
}

require_cmd forge
require_cmd cast
require_cmd jq
require_cmd mktemp

: "${BSC_TESTNET_RPC:?BSC_TESTNET_RPC is required}"

BSC_TESTNET_CHAIN_ID="${BSC_TESTNET_CHAIN_ID:-97}"
PANCAKESWAP_V3_ROUTER="${PANCAKESWAP_V3_ROUTER:-0x1b81D678ffb9C0263b24A97847620C99d213eB14}"
PANCAKESWAP_V3_FACTORY="${PANCAKESWAP_V3_FACTORY:-0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865}"
PANCAKESWAP_V3_WNATIVE="${PANCAKESWAP_V3_WNATIVE:-0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd}"
VERIFIER_URL="https://api-testnet.bscscan.com/api"
FOUNDRY_OUT_DIR="${FOUNDRY_OUT_DIR:-$(resolve_foundry_out_dir)}"

CHAIN_ID_ON_RPC="$(cast chain-id --rpc-url "$BSC_TESTNET_RPC")"
if [[ "$CHAIN_ID_ON_RPC" != "$BSC_TESTNET_CHAIN_ID" ]]; then
  echo "Chain mismatch: expected $BSC_TESTNET_CHAIN_ID, got $CHAIN_ID_ON_RPC" >&2
  exit 1
fi

assert_router_compatibility
configure_signer

echo "Using signer mode: $DEPLOY_SIGNER_MODE"

VERIFY_ARGS=()
if [[ -n "${BSCSCAN_API_KEY:-}" ]]; then
  VERIFY_ARGS=(
    --verify
    --verifier-url "$VERIFIER_URL"
    --etherscan-api-key "$BSCSCAN_API_KEY"
  )
fi

export EXPECTED_CHAIN_ID="$BSC_TESTNET_CHAIN_ID"
export PANCAKESWAP_V3_ROUTER

echo "Deploying VaultFactory to BSC Testnet (chainId=$BSC_TESTNET_CHAIN_ID)..."
forge script script/DeployFactory.s.sol:DeployFactory \
  --rpc-url "$BSC_TESTNET_RPC" \
  "${SIGNER_ARGS[@]}" \
  --broadcast \
  "${VERIFY_ARGS[@]}"

FACTORY_ADDRESS="$(extract_contract_address "DeployFactory.s.sol" "VaultFactory" "VaultFactory.sol")"
assert_contract_deployed "$FACTORY_ADDRESS" "VaultFactory"
assert_factory_runtime_config "$FACTORY_ADDRESS"

echo "Deploying adapters to BSC Testnet..."
forge script script/DeployAdapters.s.sol:DeployAdapters \
  --rpc-url "$BSC_TESTNET_RPC" \
  "${SIGNER_ARGS[@]}" \
  --broadcast \
  "${VERIFY_ARGS[@]}"

VENUS_ADAPTER_ADDRESS="$(extract_contract_address "DeployAdapters.s.sol" "VenusAdapter" "VenusAdapter.sol")"
PANCAKESWAP_ADAPTER_ADDRESS="$(
  extract_contract_address "DeployAdapters.s.sol" "PancakeSwapV3Adapter" "PancakeSwapV3Adapter.sol"
)"
assert_contract_deployed "$VENUS_ADAPTER_ADDRESS" "VenusAdapter"
assert_contract_deployed "$PANCAKESWAP_ADAPTER_ADDRESS" "PancakeSwapV3Adapter"
assert_pancake_adapter_runtime_config "$PANCAKESWAP_ADAPTER_ADDRESS"

DEPLOYER_ADDRESS="$(extract_deployer_address "$(run_file_path "DeployAdapters.s.sol")")"
DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
VENUS_ADAPTER_CODEHASH="$(cast codehash "$VENUS_ADAPTER_ADDRESS" --rpc-url "$BSC_TESTNET_RPC")"
PANCAKESWAP_ADAPTER_CODEHASH="$(cast codehash "$PANCAKESWAP_ADAPTER_ADDRESS" --rpc-url "$BSC_TESTNET_RPC")"
VENUS_ADAPTER_LEAF="$(cast abi-encode "f(address,bytes32)" "$VENUS_ADAPTER_ADDRESS" "$VENUS_ADAPTER_CODEHASH" | xargs -I{} cast keccak {})"
PANCAKESWAP_ADAPTER_LEAF="$(cast abi-encode "f(address,bytes32)" "$PANCAKESWAP_ADAPTER_ADDRESS" "$PANCAKESWAP_ADAPTER_CODEHASH" | xargs -I{} cast keccak {})"

DEPLOYMENT_FILE="deployments/bsc-testnet.json"
mkdir -p deployments
TMP_DEPLOYMENT_FILE="$(mktemp deployments/.bsc-testnet.json.tmp.XXXXXX)"
cleanup_tmp_file() {
  if [[ -f "${TMP_DEPLOYMENT_FILE:-}" ]]; then
    rm -f "$TMP_DEPLOYMENT_FILE"
  fi
}
trap cleanup_tmp_file EXIT

cat > "$TMP_DEPLOYMENT_FILE" <<JSON
{
  "chainId": ${BSC_TESTNET_CHAIN_ID},
  "network": "bsc-testnet",
  "factory": "${FACTORY_ADDRESS}",
  "adapters": {
    "venus": "${VENUS_ADAPTER_ADDRESS}",
    "pancakeswap": "${PANCAKESWAP_ADAPTER_ADDRESS}"
  },
  "adapterCodehashes": {
    "venus": "${VENUS_ADAPTER_CODEHASH}",
    "pancakeswap": "${PANCAKESWAP_ADAPTER_CODEHASH}"
  },
  "adapterLeaves": {
    "venus": "${VENUS_ADAPTER_LEAF}",
    "pancakeswap": "${PANCAKESWAP_ADAPTER_LEAF}"
  },
  "protocols": {
    "venus": {
      "comptroller": "0x94d1820b2D1c7c7452A163983Dc888CEC546b77D",
      "vBUSD": "0x08e0A5575De71037aE36AbfAfb516595fE68e5e4",
      "vUSDT": "0xb7526572FFE56AB9D7489838Bf2E18e3323b441A"
    },
    "pancakeswap": {
      "router": "${PANCAKESWAP_V3_ROUTER}",
      "factory": "${PANCAKESWAP_V3_FACTORY}",
      "wnative": "${PANCAKESWAP_V3_WNATIVE}"
    }
  },
  "tokens": {
    "BUSD": "0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee",
    "USDT": "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd",
    "WBNB": "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"
  },
  "deployedAt": "${DEPLOYED_AT}",
  "deployer": "${DEPLOYER_ADDRESS}"
}
JSON

jq empty "$TMP_DEPLOYMENT_FILE" >/dev/null
mv "$TMP_DEPLOYMENT_FILE" "$DEPLOYMENT_FILE"
trap - EXIT

echo "Deployment complete"
echo "Factory: $FACTORY_ADDRESS"
echo "Venus Adapter: $VENUS_ADAPTER_ADDRESS"
echo "PancakeSwap Adapter: $PANCAKESWAP_ADAPTER_ADDRESS"
echo "Venus Adapter codehash: $VENUS_ADAPTER_CODEHASH"
echo "PancakeSwap Adapter codehash: $PANCAKESWAP_ADAPTER_CODEHASH"
echo "Deployment record: $DEPLOYMENT_FILE"
