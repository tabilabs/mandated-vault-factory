# PredictClaw

`predict/` is an isolated Python subproject that adds the **PredictClaw** auxiliary tool to `mandated-vault-factory` without changing the repository’s Foundry workflow.

## What lives here

- `scripts/predictclaw.py` — top-level CLI router
- `lib/` — config, auth, REST, wallet, funding, trade, positions, and hedge services
- `tests/` — unit, integration, and smoke coverage for the Python skill package

## Local development

From `mandated-vault-factory/predict`:

```bash
uv sync
uv run pytest -q
uv run python scripts/predictclaw.py --help
```

This package keeps its own `.venv`, `.gitignore`, and test harness under `predict/`. The repository root remains responsible for Foundry-only checks.

## Contributor command surface

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

## Environment contract

The implementation uses **SDK for chain-aware/signed flows** and **REST for auth, market/orderbook data, order submission, and position queries**.

| Variable | Required | Notes |
| --- | --- | --- |
| `PREDICT_STORAGE_DIR` | No | Defaults to `~/.openclaw/predict`; stores `positions.json` |
| `PREDICT_ENV` | No | Defaults to `testnet`; accepted values are `testnet`, `mainnet`, or `test-fixture` |
| `PREDICT_API_BASE_URL` | No | Override REST base URL (default code path remains `https://api.predict.fun`) |
| `PREDICT_API_KEY` | Mainnet | Required for authenticated mainnet REST paths |
| `PREDICT_PRIVATE_KEY` | EOA mode | Direct signer path for wallet/trade/funding flows |
| `PREDICT_ACCOUNT_ADDRESS` | Predict Account mode | Smart-wallet address |
| `PREDICT_PRIVY_PRIVATE_KEY` | Predict Account mode | Privy-exported signer for the Predict Account |
| `OPENROUTER_API_KEY` | Hedge live mode | Required for non-fixture hedge analysis |
| `PREDICT_MODEL` | No | Overrides the default OpenRouter model |
| `PREDICT_SMOKE_ENV` | Smoke only | Enables the env-gated smoke suite |
| `PREDICT_SMOKE_API_BASE_URL` | Smoke only | Recommended for testnet/dev API smoke runs |
| `PREDICT_SMOKE_PRIVATE_KEY` | Smoke optional | Enables signer/JWT smoke checks |
| `PREDICT_SMOKE_ACCOUNT_ADDRESS` | Smoke optional | Predict Account smoke mode |
| `PREDICT_SMOKE_PRIVY_PRIVATE_KEY` | Smoke optional | Predict Account signer for smoke |
| `PREDICT_SMOKE_API_KEY` | Smoke optional | Supplies authenticated testnet REST access |

## Runtime modes

- **`test-fixture`** — uses local JSON fixtures and deterministic wallet/hedge/trade behavior; ideal for development, integration tests, and CI.
- **`testnet`** — intended for live but non-mainnet checks; use `PREDICT_API_BASE_URL` or `PREDICT_SMOKE_API_BASE_URL` if your target endpoint is `https://dev.predict.fun`.
- **`mainnet`** — requires `PREDICT_API_KEY` and should be treated as a live-trading environment.

## Wallet and funding notes

- `wallet status` reports signer mode, funding address, balances, and approval readiness.
- `wallet deposit` shows the active funding address and accepted assets (`BNB`, `USDT`).
- `wallet withdraw` validates checksum destination, positive amount, available balance, and BNB gas headroom before attempting transfer logic.
- In fixture mode, withdraw commands return deterministic placeholder transaction hashes instead of touching a chain.

## Positions and storage

- Local trades are journaled to `positions.json` inside `PREDICT_STORAGE_DIR`.
- Writes are atomic (`.tmp` + replace) and corrupted JSON falls back to a safe empty state.
- `positions` is tracked/journal-first by default; `positions --all` also includes unmatched remote rows labeled `source=external`.

## Hedge notes

- Hedge analysis uses OpenRouter over plain HTTP with a JSON-only contract.
- Fixture mode uses deterministic keyword- and pairing-based hedge portfolios so CLI and integration tests stay secret-free.
- The current public command surface remains PolyClaw-parity plus `wallet deposit` / `wallet withdraw`; there is no public `sell` command in v1.

## Verification layers

```bash
# unit + command tests
uv run pytest -q

# fixture-backed end-to-end CLI checks
uv run pytest tests/integration -q

# env-gated smoke (passes or skips)
uv run pytest tests/smoke/test_testnet_smoke.py -q
```
