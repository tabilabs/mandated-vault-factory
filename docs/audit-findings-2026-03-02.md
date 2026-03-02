# Contract Audit Findings (2026-03-02)

Scope: `src/` contracts, core `test/` suites, dependency/license surface.

## Findings

### #1 [WARNING] Proxy adapter codehash binding can drift after implementation upgrades
- **File:** `src/libs/AdapterLib.sol:48`, `README.md` (Key Constraints)
- **Issue:** Adapter allowlist leaf binds `(adapter, codehash)`. For upgradeable proxy adapters, proxy codehash stays stable even when implementation changes, so previously valid Merkle proofs may remain valid after logic drift.
- **Risk:** Governance/operational trust-boundary risk; can invalidate signer assumptions over time.
- **Recommended fix:** Allowlist immutable adapters only, or enforce re-sign/rebuild of allowlist root whenever implementation/governance state changes.

### #2 [WARNING] AGPL-3.0 transitive dependencies require explicit compliance boundary
- **File:**
  - `lib/openzeppelin-contracts-upgradeable/lib/erc4626-tests/LICENSE`
  - `lib/openzeppelin-contracts-upgradeable/lib/halmos-cheatcodes/LICENSE`
- **Issue:** Dependency tree includes AGPL components (mainly test/tooling scope).
- **Risk:** Potential distribution/compliance exposure if those assets are accidentally bundled into shipped artifacts.
- **Recommended fix:** Add license policy + CI gate (AGPL allowed only in test scope), and document boundary in third-party notices.

### #3 [WARNING] Oversized test files reduce maintainability and review clarity
- **File:**
  - `test/VaultFactory.t.sol` (~1002 lines)
  - `test/VaultFork.t.sol` (~879 lines)
- **Issue:** Large monolithic test files increase merge conflict rate and make targeted security regression review harder.
- **Risk:** Medium engineering risk (not direct protocol exploit risk).
- **Recommended fix:** Split by domain: Factory/Auth/Drawdown/Extensions/Fork-Protos.

### #4 [SUGGESTION] Missing explicit gas-griefing stress tests for high-gas adapters
- **File:** `test/VaultBranch.t.sol`, `test/VaultFactory.t.sol`
- **Issue:** Revert-data size griefing is covered (4 KiB cap), but explicit high-gas-consumption adapter scenarios are not directly asserted.
- **Risk:** Runtime liveness/performance confidence gap.
- **Recommended fix:** Add adapter mocks that intentionally burn gas / expand memory and assert predictable failure boundaries.

### #5 [SUGGESTION] Security-critical contract branch coverage can be improved
- **File:** `src/MandatedVaultClone.sol`
- **Issue:** Coverage report indicates branch coverage is lower than other core modules (`75%` in latest run).
- **Risk:** Some edge paths may be insufficiently regression-tested.
- **Recommended fix:** Add targeted tests for uncovered branches in extension parsing, ERC-1271 edge behavior, and event/state coupling paths.

### #6 [SUGGESTION] Merkle helper not covered in non-fork path
- **File:** `test/helpers/MerkleHelper.sol`
- **Issue:** Coverage is `0%` in non-fork runs because fork suite is skipped without RPC.
- **Risk:** Helper correctness currently depends on fork-enabled environments.
- **Recommended fix:** Add pure/unit tests for Merkle helper logic that run without fork configuration.

## Verification Notes
- `forge build`: pass
- `forge test`: pass (fork suite skipped without `--fork-url`, expected)
- `forge coverage --report summary --ir-minimum`: pass; used for coverage signal only
