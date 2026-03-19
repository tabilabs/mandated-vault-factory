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

# PredictClaw (Python skill package)
cd predict
uv sync
uv run pytest -q
uv run python scripts/predictclaw.py --help
```

## 3. Recommended Reading Order

1. `src/interfaces/IERC8192MandatedVault.sol` (domain interface and error model)
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

## 7. PredictClaw Contributor Notes

- The Python skill package lives in `predict/` and keeps its own `.venv`, tests, and `env.example` for source checkouts.
- For packaged installs, create `~/.openclaw/skills/predictclaw/.env` and paste the mode-specific snippet from `predict/README.md`; this is the recommended first-time config path.
- Use `PREDICT_ENV=test-fixture` for secret-free CLI and integration verification.
- `predict/SKILL.md` is OpenClaw-facing install/use documentation; `predict/README.md` is repo-local contributor documentation.
- Do not add public CLI verbs beyond the current command contract without updating tests, docs, and `scripts/predictclaw.py --help` together.
- PredictClaw supports four wallet modes: `read-only`, `eoa`, `predict-account`, and `mandated-vault`.
- `mandated-vault` is an advanced explicit opt-in path. Set `PREDICT_WALLET_MODE=mandated-vault` only when you intentionally want MCP-assisted mandated-vault control-plane behavior.
- The preferred advanced trading route is `PREDICT_WALLET_MODE=predict-account` plus `ERC_MANDATED_*` overlay so Vault funds the Predict Account through `vault-to-predict-account` planning while Predict Account remains the official trading account.
- For mandated-vault targeting, use `ERC_MANDATED_VAULT_ADDRESS` when you already know the deployed vault address. Otherwise supply the full derivation tuple (`ERC_MANDATED_FACTORY_ADDRESS`, `ERC_MANDATED_VAULT_ASSET_ADDRESS`, `ERC_MANDATED_VAULT_NAME`, `ERC_MANDATED_VAULT_SYMBOL`, `ERC_MANDATED_VAULT_AUTHORITY`, `ERC_MANDATED_VAULT_SALT`) so `wallet status` / `wallet deposit` can work with the MCP-predicted vault address.
- If the predicted vault is undeployed, `wallet deposit` returns create-vault preparation guidance only; PredictClaw does not auto-broadcast. The MCP orchestrates the preparation flow, while the vault contract policy remains the authorization root.
- Overlay buy keeps the official Predict Account path when funded and otherwise returns deterministic `funding-required` guidance pointing to `wallet deposit --json`.
- v1 limitation: pure mandated-vault does not provide predict.fun trading parity. `wallet approve`, `wallet withdraw`, `buy`, `positions`, `position`, `hedge scan`, and `hedge analyze` stay blocked with `unsupported-in-mandated-vault-v1`.
