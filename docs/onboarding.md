# Contributor Onboarding

## 1. What This Repository Implements

- Deterministic deployment factory (`VaultFactory`) for ERC-1167 clone vaults.
- Mandated execution vault (`MandatedVaultClone`) built on ERC-4626 + EIP-712.
- Risk controls via nonce/revocation/epoch + adapter allowlist + drawdown guards.

## 2. Quick Start

Prerequisites:
- Foundry toolchain (`forge`, `cast`, `anvil`)
- Git submodules initialized

Setup:
```bash
git submodule update --init --recursive
forge --version
```

Local checks (same as CI intent):
```bash
forge fmt --check
forge build --sizes
forge test -vvv
```

## 3. Recommended Reading Order

1. `src/interfaces/IERCXXXXMandatedVault.sol` (domain interface and error model)
2. `src/VaultFactory.sol` + `src/interfaces/IVaultFactory.sol` (deployment boundary)
3. `src/MandatedVaultClone.sol` (core execution path)
4. `src/libs/MandateLib.sol` / `src/libs/AdapterLib.sol` / `src/libs/DrawdownLib.sol` (isolated validation logic)
5. `test/VaultFactory.t.sol` (behavioral specification)

## 4. How Tests Map to Runtime Behavior

- `test_createVault*`: deterministic deployment and registry invariants.
- `test_predictVaultAddress*`: address prediction consistency.
- `test_basicExecution`, `test_multipleExecutions`: happy-path execution.
- `test_drawdownExceeded`, `test_cumulativeDrawdownExceeded`: risk circuit breakers.
- `test_selectorAllowlist_*`: extension parsing and selector constraints.
- `test_erc1271_*`: smart-contract authority signature path.
- `test_vaultBusy_*`: reentrancy guard behavior during execution.

## 5. Contributor Guardrails

- Do not change mandate verification ordering without explicit security review.
- Keep replay protection (`nonceThreshold` + `nonceUsed`) and revocation checks before external calls.
- Preserve deterministic salt semantics in factory (`creator` is part of salt).
- Any extension format changes must update hash/check/decode paths and tests together.

## 6. Documentation Index

- `docs/architecture.md`
- `docs/flows.md`
- `docs/onboarding.md`
