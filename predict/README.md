# PredictClaw

[中文说明 / Chinese Version](./README.zh-CN.md)

PredictClaw is the predict.fun-native OpenClaw skill for browsing markets, checking wallet readiness, viewing deposit addresses, withdrawing funds, placing buys, inspecting positions, and scanning hedge opportunities.

This `predict/` directory is an isolated Python subproject inside `mandated-vault-factory`. It keeps its own CLI, runtime configuration, and tests without changing the repository's Foundry workflow.

PredictClaw's version source of truth is `predict/pyproject.toml`. When checking GitHub or building from source, use the `predict/` subdirectory; the repository root is the Foundry workspace and does not define a PredictClaw `pyproject.toml`.

## What PredictClaw Is For

PredictClaw gives OpenClaw a predictable command surface for predict.fun workflows:

- market discovery and market detail lookup
- wallet readiness and deposit guidance
- trading through EOA or Predict Account paths
- position journaling and query flows
- optional hedge analysis for users who enable model access

For the advanced funding route, PredictClaw supports a **Vault funding overlay** on top of the official Predict Account path. In that route, **Predict Account remains** the deposit address, trade identity, and order path while Vault acts as the funding source.

## Install

### ClawHub / packaged install

```bash
clawhub install predictclaw
cd ~/.openclaw/skills/predictclaw
uv sync
cp template.env .env
```

In packaged installs, the skill base directory is usually `~/.openclaw/skills/predictclaw`. In OpenClaw manifests and examples, this same location may appear as `{baseDir}`.

### Manual install

1. Copy or symlink this `predict/` folder into `~/.openclaw/skills/predictclaw/`
2. From the installed skill directory, run:

```bash
cd {baseDir} && uv sync
cd {baseDir} && cp template.env .env
```

### Local repo development

From `mandated-vault-factory/predict`:

```bash
uv sync
uv run pytest -q
uv run python scripts/predictclaw.py --help
```

## How configuration actually works

PredictClaw only reads standard environment variables. The supported, tested inputs are:

- the process environment, for example `export PREDICT_ENV=testnet`
- a local `{baseDir}/.env` file, auto-loaded by `scripts/predictclaw.py` when present

If both are present, exported environment variables win and `.env` only fills missing values.

If your OpenClaw host version injects environment variables into the skill process, that also works because PredictClaw receives normal env vars either way. Older docs used `skills.entries.predictclaw.env`; treat that as a host-version-specific convenience, not the canonical PredictClaw config surface.

The SKILL frontmatter metadata intentionally lists only the universal entry variables: `PREDICT_ENV` and `PREDICT_WALLET_MODE`. OpenClaw's runtime metadata is flat rather than mode-aware, so listing every optional signer or vault variable there would incorrectly imply they are all required at the same time. The mode-specific requirements are documented below and enforced by the runtime config validator.

## First-time setup (recommended)

1. Install the skill and run `uv sync`.
2. Pick a bootstrap file:
   - `template.env` -> secret-free local fixture bootstrap
   - `template.readonly.env` -> live read-only market reads
   - `template.eoa.env` -> direct private-key trading
   - `template.predict-account.env` -> Predict Account trading
   - `template.mandated-vault.env` -> advanced vault control-plane / overlay
3. Copy the chosen template to `.env` inside `~/.openclaw/skills/predictclaw/`.
4. Fill only the variables required for that mode.
5. Verify the install with `uv run python scripts/predictclaw.py --help`.
6. Then run a mode-appropriate command:
   - fixture bootstrap -> `uv run python scripts/predictclaw.py markets trending`
   - live read-only -> `uv run python scripts/predictclaw.py markets trending`
   - `eoa` / `predict-account` -> `uv run python scripts/predictclaw.py wallet status --json`
   - `mandated-vault` -> `uv run python scripts/predictclaw.py wallet deposit --json`

## Bootstrap templates

- `template.env` -> safest first install; uses `test-fixture` + `read-only` so the CLI can start without secrets or network access
- `template.readonly.env` -> live market reads; mainnet market reads require PREDICT_API_KEY
- `template.eoa.env` -> EOA signer flow, starting on testnet with `https://api-testnet.predict.fun`
- `template.predict-account.env` -> Predict Account signer flow, starting on testnet with `https://api-testnet.predict.fun`
- `template.mandated-vault.env` -> advanced explicit opt-in template for vault control-plane usage

## Real first-install paths

### A. CLI boots successfully

```bash
uv sync
uv run python scripts/predictclaw.py --help
```

### B. Secret-free local verification

Copy `template.env` and run:

```bash
uv run python scripts/predictclaw.py markets trending
```

This uses `test-fixture`, so it proves the skill boots and routes commands correctly without touching the live API.
Fixture mode only knows the bundled fixture market IDs (`123`, `456`, `789`, `101`, `202`). For real market IDs, switch to the live read-only template first.

### C. Live read-only market reads

Copy `template.readonly.env` and choose one of these paths:

- `mainnet` + valid `PREDICT_API_KEY` for live production reads
- `testnet` + `https://api-testnet.predict.fun` for unauthenticated non-mainnet reads

```bash
uv run python scripts/predictclaw.py markets trending
uv run python scripts/predictclaw.py market <market_id> --json
```

If mainnet reads fail with `401 unauthorized`, your `PREDICT_API_KEY` is missing or invalid.

### D. Signer-backed flows

wallet status requires signer configuration. `wallet status --json` is the right next step for `eoa` and `predict-account`, but it is not the first command to run in `read-only` mode.

## Configuration examples

The snippets below are `.env` examples. Put them in `{baseDir}/.env` or export the same names in your shell.

`OPENROUTER_API_KEY` only matters for non-fixture `hedge scan` / `hedge analyze` usage. It is not required for market, wallet, or buy flows.

### bootstrap-safe fixture mode

```dotenv
PREDICT_ENV=test-fixture
PREDICT_WALLET_MODE=read-only
```

Use this for secret-free CLI verification and local market browsing only. It does not hit the live API. Switch to `eoa`, `predict-account`, or `mandated-vault` before using wallet or trade subcommands.

### live read-only mode

```dotenv
PREDICT_ENV=mainnet
PREDICT_WALLET_MODE=read-only
PREDICT_API_KEY=YOUR_PREDICT_API_KEY
```

Mainnet market reads require PREDICT_API_KEY. If you want unauthenticated non-mainnet reads instead, use `PREDICT_ENV=testnet` plus `PREDICT_API_BASE_URL=https://api-testnet.predict.fun`.

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

In that path, PredictClaw asks the MCP to predict the vault address and, when the vault is still undeployed, returns create-vault preparation guidance only. It does **not** auto-broadcast and instead reports `manual-only` preparation details.

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

If you do **not** have an explicit deployed vault address yet, keep the same Predict Account pair and replace `ERC_MANDATED_VAULT_ADDRESS` with the full derivation tuple: `ERC_MANDATED_FACTORY_ADDRESS`, `ERC_MANDATED_VAULT_ASSET_ADDRESS`, `ERC_MANDATED_VAULT_NAME`, `ERC_MANDATED_VAULT_SYMBOL`, `ERC_MANDATED_VAULT_AUTHORITY`, and `ERC_MANDATED_VAULT_SALT`.

Optional overlay caps:

```dotenv
ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX=5000000000000000000
ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW=10000000000000000000
ERC_MANDATED_FUNDING_WINDOW_SECONDS=3600
```

In the overlay route, Predict Account remains the deposit/trading account while Vault funds the Predict Account through MCP-backed session and asset-transfer planning.

## Wallet Modes

PredictClaw supports four explicit wallet modes:

- `read-only` — browse market data only; no signer-backed wallet actions.
- `eoa` — direct signer path for wallet, trade, and funding flows.
- `predict-account` — smart-wallet funding/trading path using `PREDICT_ACCOUNT_ADDRESS` plus `PREDICT_PRIVY_PRIVATE_KEY`.
- `mandated-vault` — advanced explicit opt-in control-plane path for protected vault-only status/deposit flows.

### Recommended route

If you want to keep the official Predict trading identity while letting Vault supply funds, use:

- `PREDICT_WALLET_MODE=predict-account`
- plus the required `ERC_MANDATED_*` overlay inputs

This route exposes `vault-to-predict-account` semantics in `wallet status --json` and `wallet deposit --json`.

### Pure mandated-vault boundaries

`mandated-vault` is an advanced explicit opt-in mode. Only enable it when you intentionally want MCP-assisted vault control-plane behavior.

Pure `mandated-vault` does **not** provide predict.fun trading parity. `wallet approve`, `wallet withdraw`, `buy`, `positions`, `position`, `hedge scan`, and `hedge analyze` fail closed with `unsupported-in-mandated-vault-v1`.

### Common configuration mistakes

- `read-only` is browse-only. Start with `markets ...`, not signer-backed wallet or trade commands.
- `wallet status` requires signer configuration. In `read-only`, start with `markets trending` or `market <id> --json` instead.
- `mainnet` market reads require `PREDICT_API_KEY`; missing keys fail early and invalid keys return `401 unauthorized`.
- `testnet` market reads use `https://api-testnet.predict.fun`; the older `https://dev.predict.fun` endpoint no longer matches the current API contract.
- `eoa` requires `PREDICT_PRIVATE_KEY` and rejects Predict Account or mandated-vault inputs.
- `predict-account` requires both `PREDICT_ACCOUNT_ADDRESS` and `PREDICT_PRIVY_PRIVATE_KEY`.
- `mainnet` requires `PREDICT_API_KEY`.
- pure `mandated-vault` needs a working `ERC_MANDATED_MCP_COMMAND`; overlay mode also needs `ERC_MANDATED_VAULT_ASSET_ADDRESS` and `ERC_MANDATED_VAULT_AUTHORITY` for funding orchestration.

## The mandated MCP dependency (`ERC_MANDATED_MCP_COMMAND`)

`ERC_MANDATED_MCP_COMMAND` is the launcher command that PredictClaw uses to talk to the mandated-vault MCP runtime. The default value is `erc-mandated-mcp`.

This is the practical bridge between PredictClaw and the Vault control plane:

1. **Vault prediction / preparation** — predict a vault address when only the derivation tuple is available.
2. **Vault overlay orchestration** — expose `vault-to-predict-account` routing, funding-policy context, and session planning.
3. **Control-plane safety boundary** — if the MCP is missing or unhealthy, PredictClaw surfaces a fail-closed error instead of silently guessing.

If your environment packages that runtime through something like an `@erc-mandated/mcp` package, point `ERC_MANDATED_MCP_COMMAND` at the launcher it installs. PredictClaw's public contract is the command path, not a hard-coded package manager dependency.

The MCP orchestrates transport and preparation; the vault contract policy authorizes what the vault can actually execute.

## Command Surface

```bash
uv run python scripts/predictclaw.py markets trending
uv run python scripts/predictclaw.py markets search "election"
uv run python scripts/predictclaw.py market 123 --json
uv run python scripts/predictclaw.py wallet status --json
uv run python scripts/predictclaw.py wallet approve --json
uv run python scripts/predictclaw.py wallet deposit --json
uv run python scripts/predictclaw.py wallet withdraw usdt 1 0xb30741673D351135Cf96564dfD15f8e135f9C310 --json
uv run python scripts/predictclaw.py wallet withdraw bnb 0.1 0xb30741673D351135Cf96564dfD15f8e135f9C310 --json
uv run python scripts/predictclaw.py buy 123 YES 25 --json
uv run python scripts/predictclaw.py positions --json
uv run python scripts/predictclaw.py position pos-123-yes --json
uv run python scripts/predictclaw.py hedge scan --query election --json
uv run python scripts/predictclaw.py hedge analyze 101 202 --json
```

## Core workflow notes

- `wallet status` reports signer mode, funding address, balances, and approval readiness.
- `wallet deposit` shows the active funding address and accepted assets (`BNB`, `USDT`).
- `wallet withdraw` validates checksum destination, positive amount, available balance, and BNB gas headroom before attempting transfer logic.
- In fixture mode, withdraw commands return deterministic placeholder transaction hashes instead of touching a chain.
- In `predict-account + ERC_MANDATED_*` overlay, `wallet status` / `wallet deposit` expose:
  - `predictAccountAddress`
  - `tradeSignerAddress`
  - `vaultAddress`
  - `fundingRoute = vault-to-predict-account`
- Predict Account remains the deposit address / trading account.
- The funding target is the Predict Account, not the Vault and not the owner EOA.
- Optional Vault funding-policy envs let you cap Vault→Predict transfers by per-tx amount, cumulative window amount, and window duration.
- Those funding-policy amounts use raw token units; for BSC mainnet USDT (18 decimals), `5 U = 5000000000000000000` and `10 U = 10000000000000000000`.
- If the Predict Account already has enough balance, `buy` continues through the normal official Predict Account order path.
- If balance is short, `buy` fails cleanly with deterministic `funding-required` guidance and points users to `wallet deposit --json`; it does not auto-execute the vault funding leg in the current local signer context.

## Runtime Modes

- `test-fixture` — uses local JSON fixtures and deterministic wallet/hedge/trade behavior; ideal for development, integration tests, and secret-free first-install verification.
- `testnet` — intended for live but non-mainnet checks; the current REST endpoint is `https://api-testnet.predict.fun` and market reads do not require `PREDICT_API_KEY`.
- `mainnet` — requires `PREDICT_API_KEY` even for market reads and should be treated as a live-trading environment.

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `PREDICT_STORAGE_DIR` | Local journal and position storage |
| `PREDICT_ENV` | Defaults to `testnet` in code; `template.env` intentionally bootstraps `test-fixture`; accepted values are `testnet`, `mainnet`, or `test-fixture` |
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
| `OPENROUTER_API_KEY` | Hedge analysis model access |
| `PREDICT_MODEL` | OpenRouter model override |
| `PREDICT_SMOKE_ENV` | Enables the smoke suite |
| `PREDICT_SMOKE_API_BASE_URL` | Optional smoke REST base override |
| `PREDICT_SMOKE_PRIVATE_KEY` | Enables signer/JWT smoke checks |
| `PREDICT_SMOKE_ACCOUNT_ADDRESS` | Predict Account smoke mode |
| `PREDICT_SMOKE_PRIVY_PRIVATE_KEY` | Predict Account smoke signer |
| `PREDICT_SMOKE_API_KEY` | Smoke REST auth |

## Hedge notes

- Hedge analysis uses OpenRouter over plain HTTP with a JSON-only contract.
- `OPENROUTER_API_KEY` is only required for non-fixture hedge analysis.
- Fixture mode uses deterministic keyword- and pairing-based hedge portfolios so CLI and integration tests stay secret-free.
- The current public command surface remains PolyClaw-parity plus `wallet deposit` / `wallet withdraw`; there is no public `sell` command in v1.

## Project Layout

- `scripts/predictclaw.py` — top-level CLI router
- `scripts/` — command-specific entry points
- `lib/` — config, auth, REST, wallet, funding, trade, positions, hedge, and MCP bridge logic
- `tests/` — unit, integration, and smoke coverage for the Python skill package

## Verification Layers

```bash
# unit + command tests
uv run pytest -q

# fixture-backed end-to-end CLI checks
uv run pytest tests/integration -q

# env-gated smoke (passes or skips)
uv run pytest tests/smoke/test_testnet_smoke.py -q
```

## Safety Notes

- Do not treat fixture mode as proof of funded-wallet behavior.
- Do not assume live liquidity from testnet or mainnet docs alone.
- Keep only limited funds on automation keys.
- Withdrawal commands are public; transfer validation happens before chain interaction, but users still own the operational risk.
- `predict-account + ERC_MANDATED_*` is the recommended advanced trading route when you want Vault to fund the Predict Account while keeping the official Predict Account order model.
- Explicit-vs-predicted vault semantics: `ERC_MANDATED_VAULT_ADDRESS` targets an existing vault directly; otherwise PredictClaw uses the derivation tuple to ask the MCP for the predicted vault address.
- If a predicted vault is undeployed, `wallet deposit` can return create-vault preparation details (`predictedVault`, transaction summary, `manual-only`) without broadcasting.
- Pure `mandated-vault` does not provide predict.fun trading parity and intentionally fails closed for unsupported paths with `unsupported-in-mandated-vault-v1`.
