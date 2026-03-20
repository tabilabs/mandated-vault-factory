---
name: predictclaw
description: Predict.fun skill with a PolyClaw-style CLI for markets, wallet funding, trading, positions, and hedging.
metadata: {"openclaw":{"emoji":"🔮","homepage":"https://predict.fun","requires":{"bins":["uv"],"env":["PREDICT_ENV","PREDICT_WALLET_MODE"]},"install":[{"id":"uv-brew","kind":"brew","formula":"uv","bins":["uv"],"label":"Install uv (brew)"}]}}
---

# PredictClaw

PredictClaw is the predict.fun-native OpenClaw skill for browsing markets, checking wallet readiness, viewing deposit addresses, withdrawing funds, placing buys, inspecting positions, and scanning hedge opportunities.

## Install

### ClawHub / packaged install

```bash
clawhub install predictclaw
cd ~/.openclaw/skills/predictclaw
uv sync
cp .env.example .env
```

In packaged installs, the skill base directory is usually `~/.openclaw/skills/predictclaw`. In OpenClaw manifests and examples, this same location may appear as `{baseDir}`.

### Manual install

1. Copy or symlink the repo’s `predict/` folder into `~/.openclaw/skills/predictclaw/`
2. From the installed skill directory, run:

```bash
cd {baseDir} && uv sync
cd {baseDir} && cp .env.example .env
```

## How configuration actually works

PredictClaw only reads standard environment variables. The supported, tested inputs are:

- the process environment, for example `export PREDICT_ENV=testnet`
- a local `{baseDir}/.env` file, auto-loaded by `scripts/predictclaw.py` when present

If both are present, exported environment variables win and `.env` only fills missing values.

If your OpenClaw host version injects environment variables into the skill process, that also works because PredictClaw receives normal env vars either way. Older docs used `skills.entries.predictclaw.env`; treat that as a host-version-specific convenience, not the canonical PredictClaw config surface.

The SKILL frontmatter metadata intentionally lists only the universal entry variables: `PREDICT_ENV` and `PREDICT_WALLET_MODE`. OpenClaw's runtime metadata is flat rather than mode-aware, so listing every optional signer or vault variable there would incorrectly imply they are all required at the same time. The mode-specific requirements are documented below and enforced by the runtime config validator.

## Mode reminders

1. Run `uv sync` in the installed skill directory.
2. Pick a bootstrap file:
   - `.env.example` -> secret-free local fixture bootstrap
   - `.env.readonly.example` -> live read-only market reads
   - `.env.eoa.example` -> direct private-key trading
   - `.env.predict-account.example` -> Predict Account trading
   - `.env.mandated-vault.example` -> advanced vault control-plane / overlay
3. Copy the chosen file to `.env` inside `~/.openclaw/skills/predictclaw/`.
4. Fill only the variables required for that mode.
5. Verify with:

```bash
cd {baseDir} && uv run python scripts/predictclaw.py --help
cd {baseDir} && uv run python scripts/predictclaw.py markets trending
```

`wallet status` requires signer configuration. For `read-only`, start with `markets trending` or `market <id> --json` instead.

mainnet market reads require PREDICT_API_KEY. For unauthenticated non-mainnet reads, use `PREDICT_ENV=testnet` with `https://api-testnet.predict.fun`.

`test-fixture` only knows the bundled local market IDs (`123`, `456`, `789`, `101`, `202`). Switch to the live read-only template before querying a real production market ID.

For signer-backed modes, the next verification step is:

```bash
cd {baseDir} && uv run python scripts/predictclaw.py wallet status --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet deposit --json
```

## Configuration examples

The snippets below are `.env` examples. Put them in `{baseDir}/.env` or export the same names in your shell.

`OPENROUTER_API_KEY` appears in the signer examples only for optional `hedge scan` / `hedge analyze` usage. It is not required for market, wallet, or buy flows and is only needed for non-fixture hedge analysis.

### bootstrap-safe fixture mode

```dotenv
PREDICT_ENV=test-fixture
PREDICT_WALLET_MODE=read-only
```

Use this for secret-free CLI verification and local market browsing only. It does not hit the live API.

### live read-only mode

```dotenv
PREDICT_ENV=mainnet
PREDICT_WALLET_MODE=read-only
PREDICT_API_KEY=YOUR_PREDICT_API_KEY
```

If you want unauthenticated non-mainnet reads instead, set `PREDICT_ENV=testnet` and `PREDICT_API_BASE_URL=https://api-testnet.predict.fun`.

### eoa mode

```dotenv
PREDICT_ENV=testnet
PREDICT_WALLET_MODE=eoa
PREDICT_API_BASE_URL=https://api-testnet.predict.fun
PREDICT_PRIVATE_KEY=0xYOUR_EOA_PRIVATE_KEY
```

### predict-account mode

```dotenv
PREDICT_ENV=testnet
PREDICT_WALLET_MODE=predict-account
PREDICT_API_BASE_URL=https://api-testnet.predict.fun
PREDICT_ACCOUNT_ADDRESS=0xYOUR_PREDICT_ACCOUNT
PREDICT_PRIVY_PRIVATE_KEY=0xYOUR_PRIVY_EXPORTED_KEY
```

### mandated-vault mode (explicit deployed vault)

```dotenv
PREDICT_ENV=testnet
PREDICT_WALLET_MODE=mandated-vault
ERC_MANDATED_VAULT_ADDRESS=0xYOUR_DEPLOYED_VAULT
ERC_MANDATED_MCP_COMMAND=erc-mandated-mcp
ERC_MANDATED_CHAIN_ID=97
```

Add `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` when your current MCP path needs the single-key preflight signer.

### mandated-vault mode (predicted / undeployed vault)

```dotenv
PREDICT_ENV=testnet
PREDICT_WALLET_MODE=mandated-vault
ERC_MANDATED_FACTORY_ADDRESS=0xYOUR_FACTORY
ERC_MANDATED_VAULT_ASSET_ADDRESS=0xYOUR_ASSET
ERC_MANDATED_VAULT_NAME=Mandated Vault
ERC_MANDATED_VAULT_SYMBOL=MVLT
ERC_MANDATED_VAULT_AUTHORITY=0xYOUR_AUTHORITY
ERC_MANDATED_VAULT_SALT=0xYOUR_SALT
ERC_MANDATED_MCP_COMMAND=erc-mandated-mcp
ERC_MANDATED_CONTRACT_VERSION=v0.3.0-agent-contract
ERC_MANDATED_CHAIN_ID=97
```

`ERC_MANDATED_EXECUTOR_PRIVATE_KEY` is optional. When it is unset, PredictClaw reuses `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` as the executor signer for the current Preflight MVP contract.

In that path, PredictClaw asks the MCP to predict the vault address and, when the vault is still undeployed, returns create-vault preparation guidance only. It does **not** auto-broadcast.

### predict-account + vault overlay (recommended advanced funding route)

```dotenv
PREDICT_ENV=testnet
PREDICT_WALLET_MODE=predict-account
PREDICT_API_BASE_URL=https://api-testnet.predict.fun
PREDICT_ACCOUNT_ADDRESS=0xYOUR_PREDICT_ACCOUNT
PREDICT_PRIVY_PRIVATE_KEY=0xYOUR_PRIVY_EXPORTED_KEY
ERC_MANDATED_VAULT_ADDRESS=0xYOUR_DEPLOYED_VAULT
ERC_MANDATED_VAULT_ASSET_ADDRESS=0xYOUR_ASSET
ERC_MANDATED_VAULT_AUTHORITY=0xYOUR_AUTHORITY
ERC_MANDATED_AUTHORITY_PRIVATE_KEY=0xYOUR_VAULT_AUTHORITY_KEY
ERC_MANDATED_MCP_COMMAND=erc-mandated-mcp
ERC_MANDATED_CONTRACT_VERSION=v0.3.0-agent-contract
ERC_MANDATED_CHAIN_ID=97
```

In the overlay route, Predict Account remains the deposit/trading account while Vault funds the Predict Account through MCP-backed session and asset-transfer planning.

If you do **not** have an explicit deployed vault address yet, keep the same Predict Account pair and replace `ERC_MANDATED_VAULT_ADDRESS` with the full derivation tuple: `ERC_MANDATED_FACTORY_ADDRESS`, `ERC_MANDATED_VAULT_ASSET_ADDRESS`, `ERC_MANDATED_VAULT_NAME`, `ERC_MANDATED_VAULT_SYMBOL`, `ERC_MANDATED_VAULT_AUTHORITY`, and `ERC_MANDATED_VAULT_SALT`.

The optional `ERC_MANDATED_FUNDING_*` envs cap Vault→Predict transfers by per-tx amount, per-window cumulative amount, and window duration. On BSC mainnet USDT, `5U = 5000000000000000000` and `10U = 10000000000000000000`.

## Wallet-mode contract

- `read-only` — browse market data only; no signer-backed wallet actions.
- `eoa` — direct signer path for wallet, trade, and funding flows.
- `predict-account` — smart-wallet funding/trading path using `PREDICT_ACCOUNT_ADDRESS` plus `PREDICT_PRIVY_PRIVATE_KEY`.
- `mandated-vault` — advanced explicit opt-in control-plane path for protected vault-only status/deposit flows.

## First-time setup

- Default local posture is `test-fixture` or `testnet`.
- `mainnet` market reads require `PREDICT_API_KEY`.
- `testnet` market reads use `https://api-testnet.predict.fun`.
- `read-only` is browse-only. Start with `markets ...`, not signer-backed wallet or trade commands.
- `wallet status requires signer configuration`.
- `eoa` requires `PREDICT_PRIVATE_KEY` and rejects Predict Account or mandated-vault inputs.
- `predict-account` requires both `PREDICT_ACCOUNT_ADDRESS` and `PREDICT_PRIVY_PRIVATE_KEY`.
- `wallet deposit` shows the funding address for the active signer mode.
- `wallet withdraw` performs safety validation before any transfer logic.
- In pure `mandated-vault`, `wallet status` and `wallet deposit` are the intended v1 entry points.
- In `predict-account + ERC_MANDATED_*` overlay, `wallet status` / `wallet deposit` expose `vault-to-predict-account` funding semantics while Predict Account remains the trade identity.
- Overlay `buy` can proceed when the Predict Account balance is sufficient; otherwise it returns deterministic `funding-required` guidance that points to `wallet deposit --json`.
- Pure `mandated-vault` needs a working `ERC_MANDATED_MCP_COMMAND`; overlay mode also needs `ERC_MANDATED_VAULT_ASSET_ADDRESS` and `ERC_MANDATED_VAULT_AUTHORITY` for funding orchestration.
- Hedge analysis uses OpenRouter; `OPENROUTER_API_KEY` is only required for non-fixture hedge analysis, and fixture mode stays secret-free.

```bash
cd {baseDir} && uv run python scripts/predictclaw.py --help
cd {baseDir} && uv run python scripts/predictclaw.py wallet status --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet deposit --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet withdraw usdt 1 0xb30741673D351135Cf96564dfD15f8e135f9C310 --json
```

## Command surface

```bash
cd {baseDir} && uv run python scripts/predictclaw.py markets trending
cd {baseDir} && uv run python scripts/predictclaw.py markets search "election"
cd {baseDir} && uv run python scripts/predictclaw.py market 123 --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet status --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet approve --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet deposit --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet withdraw usdt 1 0xb30741673D351135Cf96564dfD15f8e135f9C310 --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet withdraw bnb 0.1 0xb30741673D351135Cf96564dfD15f8e135f9C310 --json
cd {baseDir} && uv run python scripts/predictclaw.py buy 123 YES 25 --json
cd {baseDir} && uv run python scripts/predictclaw.py positions --json
cd {baseDir} && uv run python scripts/predictclaw.py position pos-123-yes --json
cd {baseDir} && uv run python scripts/predictclaw.py hedge scan --query election --json
cd {baseDir} && uv run python scripts/predictclaw.py hedge analyze 101 202 --json
```

## Environment variables

| Variable | Purpose |
| --- | --- |
| `PREDICT_STORAGE_DIR` | Local journal and position storage |
| `PREDICT_ENV` | Defaults to `testnet` in code; `.env.example` intentionally bootstraps `test-fixture`; accepted values are `testnet`, `mainnet`, or `test-fixture` |
| `PREDICT_WALLET_MODE` | Explicit mode override: `read-only`, `eoa`, `predict-account`, or `mandated-vault` |
| `PREDICT_API_BASE_URL` | Optional REST base override; leave empty to use the env-specific default (`api-testnet.predict.fun` for `testnet`, ignored in `test-fixture`, `api.predict.fun` for `mainnet`) |
| `PREDICT_API_KEY` | Mainnet-authenticated predict.fun API access; required for mainnet market reads and trading |
| `PREDICT_PRIVATE_KEY` | EOA trading and funding path |
| `PREDICT_ACCOUNT_ADDRESS` | Predict Account smart-wallet address |
| `PREDICT_PRIVY_PRIVATE_KEY` | Privy-exported signer for Predict Account mode |
| `ERC_MANDATED_VAULT_ADDRESS` | Explicit deployed mandated vault address |
| `ERC_MANDATED_FACTORY_ADDRESS` | Factory address used to predict a vault when no explicit vault address is supplied |
| `ERC_MANDATED_VAULT_ASSET_ADDRESS` | ERC-4626 asset used in mandated-vault prediction/create preparation |
| `ERC_MANDATED_VAULT_NAME` | Vault name used in mandated-vault prediction/create preparation |
| `ERC_MANDATED_VAULT_SYMBOL` | Vault symbol used in mandated-vault prediction/create preparation |
| `ERC_MANDATED_VAULT_AUTHORITY` | Authority address and create-vault `from` address for manual preparation |
| `ERC_MANDATED_VAULT_SALT` | Deterministic salt used for vault prediction/create preparation |
| `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` | Preflight Vault signer key for the current single-key MVP contract |
| `ERC_MANDATED_EXECUTOR_PRIVATE_KEY` | Optional dedicated executor signer; falls back to `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` when unset |
| `ERC_MANDATED_MCP_COMMAND` | MCP launcher command (defaults to `erc-mandated-mcp`) |
| `ERC_MANDATED_CONTRACT_VERSION` | Passed through to the mandated-vault MCP client |
| `ERC_MANDATED_CHAIN_ID` | Optional explicit chain selection for the MCP bridge |
| `ERC_MANDATED_ALLOWED_ADAPTERS_ROOT` | Optional 32-byte hex `allowedAdaptersRoot` used for Vault execution mandates; defaults to `0x11…11` for the current single-key MVP / PoC path |
| `ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX` | Optional Vault→Predict funding-policy `maxAmountPerTx` in raw token units |
| `ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW` | Optional Vault→Predict funding-policy `maxAmountPerWindow` in raw token units |
| `ERC_MANDATED_FUNDING_WINDOW_SECONDS` | Optional Vault→Predict funding-policy `windowSeconds` |
| `OPENROUTER_API_KEY` | Optional OpenRouter credential; only required for non-fixture hedge analysis |
| `PREDICT_MODEL` | OpenRouter model override |
| `PREDICT_SMOKE_ENV` | Enables the smoke suite |
| `PREDICT_SMOKE_API_BASE_URL` | Optional smoke REST base override |
| `PREDICT_SMOKE_PRIVATE_KEY` | Enables signer/JWT smoke checks |
| `PREDICT_SMOKE_ACCOUNT_ADDRESS` | Predict Account smoke mode |
| `PREDICT_SMOKE_PRIVY_PRIVATE_KEY` | Predict Account smoke signer |
| `PREDICT_SMOKE_API_KEY` | Smoke REST auth |

## Architecture note

- **SDK for chain-aware/signed flows**
- **REST for auth, data, order submission, and query**

## Safety notes

- Do not treat fixture mode as proof of funded-wallet behavior.
- Do not assume live liquidity from testnet or mainnet docs alone.
- Keep only limited funds on automation keys.
- Withdrawal commands are public; transfer validation happens before chain interaction, but users still own the operational risk.
- `mandated-vault` is an advanced explicit opt-in mode. Only enable it when you intentionally want MCP-assisted vault control-plane behavior.
- `predict-account + ERC_MANDATED_*` is the recommended advanced trading route when you want Vault to fund the Predict Account while keeping the official Predict Account order model.
- Explicit-vs-predicted vault semantics: `ERC_MANDATED_VAULT_ADDRESS` targets an existing vault directly; otherwise PredictClaw uses the derivation tuple to ask the MCP for the predicted vault address.
- If a predicted vault is undeployed, `wallet deposit` can return create-vault preparation details (`predictedVault`, transaction summary, `manual-only`) without broadcasting.
- Trust boundary: the MCP orchestrates transport and preparation; the vault contract policy authorizes what the vault can actually execute.
- Pure `mandated-vault` does not provide predict.fun trading parity. `wallet approve`, `wallet withdraw`, `buy`, `positions`, `position`, `hedge scan`, and `hedge analyze` fail closed with `unsupported-in-mandated-vault-v1`.
- Overlay funding currently plans the vault leg and surfaces deterministic `funding-required` guidance when buy needs top-up; it does not auto-execute the funding leg in the current local signer context.
