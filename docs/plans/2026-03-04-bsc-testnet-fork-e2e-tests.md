# BSC Testnet Fork E2E Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide fork-based E2E coverage for the deployed `VaultFactory`, `VenusAdapter`, and `PancakeSwapV3Adapter` on BSC Testnet (`chainId=97`). Layer A performs the primary coverage with contracts deployed locally on top of the fork. Layer B validates the already deployed contracts for consistency and runs a minimal smoke path (`Venus + Pancake`), using a head-first strategy by default with optional env-based block pinning.

**Architecture:** The test stack is split into two layers. Layer A reuses the existing `test/VaultForkBsc.*.t.sol` base contracts and helpers to cover core business logic and security semantics. Layer B reads `deployments/bsc-testnet.json`, validates that on-chain code/codehash/leaf values match the recorded deployment data at fork head, and runs a minimal smoke path via the deployed factory. External protocol volatility (`Venus` / `Pancake`) uses a triage rule: `skip` when the protocol is unavailable, `fail` for non-protocol issues.

**Tech Stack:** Foundry (`forge-std` Test + cheatcodes), Solidity `0.8.28`, OpenZeppelin, `forge-std/StdJson` for JSON parsing.

---

## 0. Constraints and Preconditions

1. Default to fork head
- Do not force a rollback to a fixed block.
- Only call `vm.rollFork(BSC_FORK_BLOCK)` when the `BSC_FORK_BLOCK` environment variable is set.
- If the rollback fails, use `vm.skip(true, reason)` and include the block number plus an operator-facing hint in the skip reason.

2. Layer responsibilities
- Layer A deploys locally on top of the fork and aims for deterministic coverage of semantics, security, and failure modes.
- Layer B targets already deployed on-chain contracts and focuses on deployment consistency plus a minimal smoke path rather than exhaustive protocol-path coverage.

3. About `ActionCallFailed` wrapping
- Reverts from external protocols or inside adapters are often wrapped by `MandatedVaultClone` as `IERCXXXXMandatedVault.ActionCallFailed(index, reason)`.
- Tests must distinguish between vault-native validation failures (direct revert) and action-execution failures (`ActionCallFailed`).

---

## Task 1: Update the BSC Fork Base to Default to Head (Optional Block Pinning)

 **Files:**
- Modify: `test/VaultForkBsc.Base.t.sol`

**Steps:**
1. Add a guard test proving that the suite does not force a rollback when `BSC_FORK_BLOCK` is unset.
2. Update `setUp()` so `vm.rollFork` runs only when the env var exists; if it fails, skip the suite.
3. Run the fork suite and confirm that it passes.

---

## Task 2: Layer A — User-Story-Driven Tests (Local Deployment on Fork)

**Files:**
- Create: `test/VaultForkBsc.Security.t.sol`
- Create: `test/VaultForkBsc.CoreSemantics.t.sol`
- Modify: `test/VaultForkBsc.Venus.t.sol`, `test/VaultForkBsc.Pancake.t.sol`, `test/VaultForkBsc.Multi.t.sol`

**Coverage:**
- US-01 deterministic predict + create
- US-02B VaultBusy reenter deposit/withdraw (wrapped as ActionCallFailed)
- US-03A/B/C UnauthorizedExecutor + InvalidSignature + PayloadDigestMismatch (direct revert)
- US-04 allowlist leaf mismatch / EOA / NonZeroActionValue
- US-08 drawdown breaker (postExecution direct revert)
- US-09 nonce used / threshold / revoke
- US-10 authority epoch mismatch

---

## Task 3: Layer B — Deployment Consistency Validation + Minimal Smoke

**Files:**
- Create: `test/helpers/BscTestnetDeploymentJson.sol`
- Create/Modify: `test/VaultForkBsc.DeployedConsistency.t.sol`
- Modify: `deployments/bsc-testnet.json`
- Modify: `foundry.toml`

**Acceptance Criteria:**
1. `deployments/bsc-testnet.json` is filled with real values for:
- factory address
- adapter addresses
- adapter codehashes and adapter leaves

2. `foundry.toml` grants minimal `fs_permissions`: read-only access to `./deployments`.

3. Tests run successfully at fork head:
- static consistency: adapter code/codehash/leaf values match the JSON record
- minimal smoke: the deployed `VaultFactory` satisfies `predictVaultAddress == createVault`, and the created vault has runtime code

---

## Task 4: Update Documentation and Run Guidance

**Files:**
- Modify: `docs/e2e-fork-user-stories.md`

**Steps:**
1. Add runnable commands for both the default head-first strategy and `BSC_FORK_BLOCK`-based reproduction.
2. Add troubleshooting guidance for common fork infra failures such as `missing trie node` and RPC rate limits.

---

## Task 5: Validation and Quality Gates

1) Full BSC fork run in head mode:

```
forge test --match-test '^test_bscFork_' --fork-url "$BSC_RPC_URL"
```

Expected result:
- Layer A semantic and security tests pass.
- If Venus or Pancake is unavailable, the suite skips according to the triage rules.

2) Layer B deployed consistency:

```
forge test --match-path test/VaultForkBsc.DeployedConsistency.t.sol --fork-url "$BSC_RPC_URL"
```

---

<!-- This plan file was backfilled to restore missing `docs/plans` coverage. The actual implementation record and code status are defined by the repository state. -->
