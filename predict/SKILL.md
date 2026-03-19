---
name: predictclaw
description: Predict.fun skill with a PolyClaw-style CLI for markets, wallet funding, trading, positions, and hedging.
metadata: {"openclaw":{"emoji":"🔮","homepage":"https://predict.fun","primaryEnv":"PREDICT_PRIVATE_KEY","requires":{"bins":["uv"],"env":["PREDICT_ENV","PREDICT_PRIVATE_KEY","PREDICT_ACCOUNT_ADDRESS","PREDICT_PRIVY_PRIVATE_KEY","PREDICT_API_KEY","OPENROUTER_API_KEY"]},"install":[{"id":"uv-brew","kind":"brew","formula":"uv","bins":["uv"],"label":"Install uv (brew)"}]}}
---

# PredictClaw

PredictClaw is the predict.fun-native OpenClaw skill for browsing markets, checking wallet readiness, viewing deposit addresses, withdrawing funds, placing buys, inspecting positions, and scanning hedge opportunities.

## Manual install

1. Copy or symlink the repo’s `predict/` folder into `~/.openclaw/skills/predictclaw/`
2. From the installed skill directory, run:

```bash
cd {baseDir} && uv sync
```

When a packaged distribution exists, the preferred future path is:

```bash
clawhub install predictclaw
```

## OpenClaw config snippets

Both examples below belong inside `skills.entries.predictclaw.env`.

### EOA mode

```yaml
skills:
  entries:
    predictclaw:
      env:
        PREDICT_ENV: testnet
        PREDICT_API_BASE_URL: https://dev.predict.fun
        PREDICT_PRIVATE_KEY: 0xYOUR_EOA_PRIVATE_KEY
        OPENROUTER_API_KEY: sk-or-v1-...
```

### Predict Account mode

```yaml
skills:
  entries:
    predictclaw:
      env:
        PREDICT_ENV: testnet
        PREDICT_API_BASE_URL: https://dev.predict.fun
        PREDICT_ACCOUNT_ADDRESS: 0xYOUR_PREDICT_ACCOUNT
        PREDICT_PRIVY_PRIVATE_KEY: 0xYOUR_PRIVY_EXPORTED_KEY
        OPENROUTER_API_KEY: sk-or-v1-...
```

## First-time setup

- Default local posture is `test-fixture` or `testnet`.
- `mainnet` requires `PREDICT_API_KEY`.
- `wallet deposit` shows the funding address for the active signer mode.
- `wallet withdraw` performs safety validation before any transfer logic.
- Hedge analysis uses OpenRouter; fixture mode stays secret-free.

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
| `PREDICT_ENV` | Defaults to `testnet`; accepted values are `testnet`, `mainnet`, or `test-fixture` |
| `PREDICT_API_BASE_URL` | Optional REST base override |
| `PREDICT_API_KEY` | Mainnet-authenticated predict.fun API access |
| `PREDICT_PRIVATE_KEY` | EOA trading and funding path |
| `PREDICT_ACCOUNT_ADDRESS` | Predict Account smart-wallet address |
| `PREDICT_PRIVY_PRIVATE_KEY` | Privy-exported signer for Predict Account mode |
| `OPENROUTER_API_KEY` | Hedge analysis model access |
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
