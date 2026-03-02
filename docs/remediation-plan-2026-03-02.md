# Remediation Plan (2026-03-02)

This plan tracks six audit findings and their execution status.

## P0

### 1) Proxy adapter governance hardening
- **Finding:** `#1`
- **Action:** Introduce a mandatory adapter governance checklist and root re-sign policy in `SECURITY.md`.
- **Acceptance criteria:**
  - Security policy explicitly requires re-signing allowlist roots on proxy implementation/governance changes.
  - Checklist covers proxy admin, upgrade controls, and emergency response.

### 2) License compliance boundary
- **Finding:** `#2`
- **Action:** Add `THIRD_PARTY_LICENSES.md` and CI license gate script.
- **Acceptance criteria:**
  - AGPL components are documented as test/tooling scope only.
  - CI step fails if AGPL appears outside approved paths.

## P1

### 3) Gas-griefing regression tests
- **Finding:** `#4`
- **Action:** Add dedicated tests for high-gas adapter behavior and failure surfacing.
- **Acceptance criteria:**
  - A gas-burning adapter path is executed through `execute()`.
  - Expected `ActionCallFailed` behavior is asserted.

### 4) MandatedVaultClone branch coverage improvements
- **Finding:** `#5`
- **Action:** Add targeted tests for uncovered `MandatedVaultClone` branches.
- **Acceptance criteria:**
  - New tests cover additional `VaultBusy` guard paths and extension edge paths.
  - Coverage report indicates improved branch/line hit counts for `MandatedVaultClone.sol`.

### 5) Merkle helper unit tests without fork
- **Finding:** `#6`
- **Action:** Add pure/unit tests for `test/helpers/MerkleHelper.sol` that run in non-fork CI.
- **Acceptance criteria:**
  - `forge test` executes helper tests without requiring `--fork-url`.
  - Coverage for helper moves from 0% to non-zero in non-fork runs.

## P2

### 6) Test file maintainability
- **Finding:** `#3`
- **Action:** Route new test additions to dedicated files (avoid further growth in `VaultFactory.t.sol` / `VaultFork.t.sol`).
- **Acceptance criteria:**
  - New test logic is added in separate test modules.
  - Legacy large-file split can be executed in a follow-up PR with minimal risk.
