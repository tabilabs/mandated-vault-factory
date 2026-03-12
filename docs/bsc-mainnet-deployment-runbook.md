# BSC Mainnet Deployment Runbook

This runbook is for the real `BSC mainnet` deployment path of:

- `VaultFactory`
- `VenusAdapter`
- `PancakeSwapV3Adapter`

It assumes the codebase has already moved to the active `ERC-8192` line and that mainnet preparation has passed code review.

## Scope and Safety Model

- Default mode is `preflight` only.
- Real broadcast happens only when `DEPLOY_BROADCAST=1`.
- Do not treat a successful preflight as deployment completion.
- Do not overwrite `deployments/bsc-mainnet.json` with guessed addresses.

## Required Tools

- `forge`
- `cast`
- `jq`
- access to a reliable `BSC mainnet` RPC

## Required Environment

```bash
export BSC_MAINNET_RPC="https://bsc-dataseed.binance.org/"
```

Recommended signer mode:

```bash
export DEPLOY_SIGNER_MODE="account"
export DEPLOYER_ACCOUNT="bsc-mainnet-deployer"
export DEPLOYER_PASSWORD_FILE="$HOME/.secrets/foundry-keystore.pass"
```

Optional verification:

```bash
export BSCSCAN_API_KEY="..."
```

Optional overrides:

```bash
export BSC_MAINNET_CHAIN_ID=56
export DEPLOYMENT_FILE="deployments/bsc-mainnet.json"
export PANCAKESWAP_V3_ROUTER="0x1b81D678ffb9C0263b24A97847620C99d213eB14"
export PANCAKESWAP_V3_FACTORY="0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
export PANCAKESWAP_V3_WNATIVE="0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
export VERIFIER_URL="https://api.bscscan.com/api"
```

## Preflight Checklist

- Confirm the launch scope is still `Venus + PancakeSwap V3`.
- Confirm the tracked token scope is still `BUSD / USDT / WBNB`, or update the deployment artifact first.
- Confirm signer mode is `account` or `ledger`; avoid private key mode unless absolutely necessary.
- Confirm `BSC_MAINNET_RPC` resolves to `chainId=56`.
- Confirm the Pancake router/factory/WBNB triplet is still correct.
- Confirm `deployments/bsc-mainnet.json` still contains placeholders for project deployment fields before the first real broadcast.
- Confirm `BSCSCAN_API_KEY` is present if explorer verification is required during broadcast.

## Run Safe Preflight

```bash
bash scripts/deploy-bsc-mainnet.sh
```

Expected result:

- prints RPC, chain ID, signer mode, verifier mode, deployment file, and Pancake target addresses
- validates `router.factory()` and `router.WETH9()`
- exits with:

```bash
Preflight passed. Re-run with DEPLOY_BROADCAST=1 to broadcast.
```

## Fork Validation Before Broadcast

Run protocol anchor validation:

```bash
forge test --match-path test/VaultForkBscMainnet.ProtocolAnchors.t.sol \
  --fork-url "$BSC_MAINNET_RPC"
```

If `deployments/bsc-mainnet.json` still contains placeholders, this is the expected state:

```bash
forge test --match-path test/VaultForkBscMainnet.DeployedConsistency.t.sol \
  --fork-url "$BSC_MAINNET_RPC"
```

Expected behavior before first mainnet deploy:

- `ProtocolAnchors` passes
- `DeployedConsistency` skips because project deployment fields are intentionally incomplete

## Real Broadcast

```bash
export DEPLOY_BROADCAST=1
bash scripts/deploy-bsc-mainnet.sh
```

What the script does after broadcast starts:

- deploys `VaultFactory`
- validates `factory.implementation()` is non-zero and has code
- deploys `VenusAdapter` and `PancakeSwapV3Adapter`
- validates `PancakeSwapV3Adapter.router()`
- computes factory / adapter codehashes and Merkle leaves
- atomically writes `deployments/bsc-mainnet.json`

## Post-Deploy Checklist

- Confirm all printed deployment addresses are non-zero and have runtime code.
- Open `deployments/bsc-mainnet.json` and verify the project fields are no longer placeholders.
- Verify contracts on BscScan if verification was enabled.
- Re-run:

```bash
forge test --match-path test/VaultForkBscMainnet.DeployedConsistency.t.sol \
  --fork-url "$BSC_MAINNET_RPC"
```

- Confirm deployed codehashes match the artifact.
- Confirm deployed Merkle leaves match the artifact.
- Record the final deployer address and deployment timestamp in operations tracking.

## Failure Handling

- If preflight fails on `chainId`, stop immediately and fix the RPC target.
- If preflight fails on Pancake router relationships, stop immediately and re-verify official addresses.
- If broadcast succeeds but artifact writing fails, do not guess values by hand; recover from the emitted addresses and on-chain codehashes.
- If `DeployedConsistency` fails after broadcast, treat it as a deployment-record mismatch until proven otherwise.
