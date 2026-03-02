# User Stories: Core Contract Methods in Real Application Scenarios

This document describes real-world user stories for all core contract methods, aimed at developers, auditors, and integrators.

## Scope

- Factory contract: `VaultFactory`
- Vault contract: `MandatedVaultClone`
- Coverage rule: core `public` / `external` methods, including key external helper methods

## Story 1: Strategy team deploys vaults with deterministic addresses

- Business scenario: an institutional strategy team deploys isolated vaults per client and pre-registers predicted addresses in permission systems.
- As a: Vault Creator
- I want: to predict vault addresses before deployment and get exact address consistency after deployment.
- So that: frontend, risk systems, and allowlists can be prepared before on-chain creation.
- Contract methods:
  - `predictVaultAddress(asset,name,symbol,authority,salt)`
  - `predictVaultAddress(creator,asset,name,symbol,authority,salt)`
  - `createVault(asset,name,symbol,authority,salt)`
  - `implementation()`
- Acceptance criteria:
  - Given fixed inputs and salt, when prediction is called, then a deterministic address is returned.
  - Given the same inputs used in `createVault`, then actual deployment address equals predicted address.
  - Given audit or tooling needs, then `implementation()` returns the clone template address.

## Story 2: Operations verifies whether an address is an official vault

- Business scenario: operations tooling ingests chain addresses and must identify official vaults created by this factory.
- As a: Operations Engineer
- I want: quick registry lookups from the factory.
- So that: non-official vaults are not treated as production assets.
- Contract methods:
  - `isVault(vault)`
  - `getVaultsByCreator(creator)`
  - `vaultCount()`
- Acceptance criteria:
  - Given any address, when `isVault` is called, then valid/invalid vault status is returned.
  - Given a creator address, when `getVaultsByCreator` is called, then all created vaults are returned.
  - Given monitoring logic, when `vaultCount` is called, then total vault count is returned.

## Story 3: Clone initialization must happen exactly once

- Business scenario: the factory initializes a fresh clone immediately; re-initialization must always fail.
- As a: Protocol Developer
- I want: one-time initialization with strict non-zero parameter checks.
- So that: takeover risks and invalid asset/authority setups are prevented.
- Contract methods:
  - `initialize(asset,name,symbol,authority)`
- Acceptance criteria:
  - Given an uninitialized clone, when factory calls `initialize`, then initialization succeeds.
  - Given an initialized clone or implementation contract, when `initialize` is called again, then it reverts.
  - Given zero `asset` or zero `authority`, then initialization reverts.

## Story 4: Integrator reads authority and capability metadata

- Business scenario: aggregator/frontend needs current authority status and extension/interface support.
- As a: Integrator
- I want: capability and authority metadata from vault.
- So that: UI and integration paths can be enabled conditionally.
- Contract methods:
  - `mandateAuthority()`
  - `authorityEpoch()`
  - `pendingAuthority()`
  - `supportsExtension(id)`
  - `supportsInterface(interfaceId)`
- Acceptance criteria:
  - Given a deployed vault, then current authority and epoch are queryable.
  - Given an authority transfer proposal, then `pendingAuthority()` returns the candidate.
  - Given extension/interface IDs, then support checks return correct booleans.

## Story 5: Authority handover must be safe and two-step

- Business scenario: signer rotation requires explicit propose + accept flow.
- As a: Current Authority
- I want: a two-step authority transfer mechanism.
- So that: accidental single-transaction loss of authority is prevented.
- Contract methods:
  - `proposeAuthority(newAuthority)`
  - `acceptAuthority()`
- Acceptance criteria:
  - Given current authority calls `proposeAuthority`, then pending authority is set.
  - Given a non-pending address calls `acceptAuthority`, then it reverts.
  - Given pending authority calls `acceptAuthority`, then authority switches and `authorityEpoch` increments.

## Story 6: Authority signs offline, executor executes on-chain

- Business scenario: risk engine signs mandates offline; executor submits and executes action bundles.
- As a: Executor
- I want: strict hash binding and signature verification before execution.
- So that: actions cannot be tampered with and only authorized payloads execute.
- Contract methods:
  - `hashActions(actions)`
  - `hashMandate(mandate)`
  - `execute(mandate,actions,signature,adapterProofs,extensions)`
- Acceptance criteria:
  - Given `payloadDigest` binds action hash, when actions are modified, then execution reverts.
  - Given valid signature and policy constraints, then `execute` succeeds and returns `preAssets/postAssets`.
  - Given invalid signature, expired mandate, or wrong executor, then execution reverts.

## Story 7: Authority performs emergency revocation and replay blocking

- Business scenario: strategy incident response requires immediate blocking of specific or ranged nonces and mandate hashes.
- As a: Authority
- I want: nonce-level and mandate-level revocation controls.
- So that: replay and leaked-signature reuse are blocked without pausing the whole vault.
- Contract methods:
  - `invalidateNonce(nonce)`
  - `invalidateNoncesBelow(threshold)`
  - `revokeMandate(mandateHash)`
  - `isNonceUsed(authority,nonce)`
  - `nonceThreshold(authority)`
  - `isMandateRevoked(mandateHash)`
- Acceptance criteria:
  - Given an invalidated nonce, then execution with that nonce fails.
  - Given threshold increases, then all lower nonces become unusable.
  - Given revoked mandate hash, then execution fails even with a valid signature.

## Story 8: Risk team tracks drawdown per epoch

- Business scenario: risk management uses epoch windows for cumulative drawdown controls.
- As a: Risk Manager
- I want: explicit epoch reset and state visibility.
- So that: cumulative risk limits align with operational periods.
- Contract methods:
  - `resetEpoch()`
  - `epochStart()`
  - `epochAssets()`
  - `execute(...)` (drawdown checks happen in execution path)
- Acceptance criteria:
  - Given authority calls `resetEpoch`, then `epochStart/epochAssets` refresh to current baseline.
  - Given drawdown exceeds limits after actions, then `execute` reverts.
  - Given post-execution gains exceed prior high-water mark, then epoch high-water mark is updated.

## Story 9: Depositors need stable ERC-4626 flows without execution-state leakage

- Business scenario: users deposit/mint/withdraw/redeem normally; strategy execution should not create unsafe reentrancy windows.
- As a: Depositor
- I want: safe ERC-4626 operations.
- So that: share accounting remains consistent during execution activity.
- Contract methods:
  - `deposit(assets,receiver)`
  - `mint(shares,receiver)`
  - `withdraw(assets,receiver,owner)`
  - `redeem(shares,receiver,owner)`
- Acceptance criteria:
  - Given normal vault state, then ERC-4626 methods operate normally.
  - Given `execute` in progress, then these methods revert via `VaultBusy` guard.

## Story 10: Operations sweeps accidental native token balances

- Business scenario: ETH can be sent to vault by adapter behavior or external transfers and must be recoverable.
- As a: Authority
- I want: authority-only native token sweep to a target address.
- So that: stranded native balances can be safely recovered.
- Contract methods:
  - `sweepNative(to,amount)`
- Acceptance criteria:
  - Given authority and valid recipient, then native sweep succeeds.
  - Given non-authority caller or zero recipient, then call reverts.

## Story 11: SDK validates extension encoding before execution

- Business scenario: integrators encode extension payloads off-chain and need deterministic decoding checks.
- As a: SDK Developer
- I want: helper decoding methods for extension payload inspection.
- So that: malformed payloads are caught before production execution.
- Contract methods:
  - `decodeExtensions(bytes)`
  - `decodeSelectorAllowlist(bytes)`
- Acceptance criteria:
  - Given valid encoding, then helper methods decode into structured values.
  - Given invalid encoding in execution flow, then `InvalidExtensionsEncoding` path is triggered.

## Function Coverage Matrix

| Contract | Method | Covered by Story |
|---|---|---|
| `VaultFactory` | `createVault` | 1 |
| `VaultFactory` | `predictVaultAddress` (2 overloads) | 1 |
| `VaultFactory` | `implementation` | 1 |
| `VaultFactory` | `isVault` | 2 |
| `VaultFactory` | `getVaultsByCreator` | 2 |
| `VaultFactory` | `vaultCount` | 2 |
| `MandatedVaultClone` | `initialize` | 3 |
| `MandatedVaultClone` | `mandateAuthority` | 4 |
| `MandatedVaultClone` | `authorityEpoch` | 4, 5 |
| `MandatedVaultClone` | `pendingAuthority` | 4, 5 |
| `MandatedVaultClone` | `supportsExtension` | 4 |
| `MandatedVaultClone` | `supportsInterface` | 4 |
| `MandatedVaultClone` | `proposeAuthority` | 5 |
| `MandatedVaultClone` | `acceptAuthority` | 5 |
| `MandatedVaultClone` | `hashActions` | 6 |
| `MandatedVaultClone` | `hashMandate` | 6 |
| `MandatedVaultClone` | `execute` | 6, 8 |
| `MandatedVaultClone` | `invalidateNonce` | 7 |
| `MandatedVaultClone` | `invalidateNoncesBelow` | 7 |
| `MandatedVaultClone` | `revokeMandate` | 7 |
| `MandatedVaultClone` | `isNonceUsed` | 7 |
| `MandatedVaultClone` | `nonceThreshold` | 7 |
| `MandatedVaultClone` | `isMandateRevoked` | 7 |
| `MandatedVaultClone` | `resetEpoch` | 8 |
| `MandatedVaultClone` | `epochStart` | 8 |
| `MandatedVaultClone` | `epochAssets` | 8 |
| `MandatedVaultClone` | `deposit` | 9 |
| `MandatedVaultClone` | `mint` | 9 |
| `MandatedVaultClone` | `withdraw` | 9 |
| `MandatedVaultClone` | `redeem` | 9 |
| `MandatedVaultClone` | `sweepNative` | 10 |
| `MandatedVaultClone` | `decodeExtensions` | 11 |
| `MandatedVaultClone` | `decodeSelectorAllowlist` | 11 |

## Maintenance Guidance

- When a new external method is introduced, add or update at least one story and matrix row.
- If execution policy ordering changes, update Story 6/7/8 acceptance criteria and associated tests together.
