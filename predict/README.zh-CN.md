# PredictClaw

[English Version / 英文版](./README.md)

PredictClaw 是一个面向 **OpenClaw** 的 `predict.fun` skill / CLI，用于浏览市场、检查钱包 readiness、查看入金地址、执行买入、查询持仓，以及在需要时分析对冲机会。

`predict/` 目录是 `mandated-vault-factory` 中的独立 Python 子项目。它拥有自己的 CLI、运行时配置和测试体系，不会改动仓库根目录的 Foundry 工作流。

## PredictClaw 的作用

PredictClaw 为 OpenClaw 提供一套稳定的 predict.fun 工作流接口：

- 浏览市场与查看单市场详情
- 检查钱包 readiness 与入金引导
- 通过 EOA 或 Predict Account 路径交易
- 记录并查询持仓
- 在启用模型能力时执行可选 hedge 分析

对于高级资金路线，PredictClaw 支持在官方 Predict Account 路径上叠加 **Vault funding overlay**。在这条路线中，**Predict Account remains** 交易身份与入金地址，而 Vault 作为资金来源。

## 安装

### 通过 ClawHub 安装

```bash
clawhub install predictclaw
cd ~/.openclaw/skills/predictclaw
uv sync
cp template.env .env
```

通过打包方式安装后，skill 目录通常就在 `~/.openclaw/skills/predictclaw`。在 OpenClaw 的一些清单或示例里，这个路径也可能写成 `{baseDir}`。

### 手动安装

1. 将仓库中的 `predict/` 目录复制或软链接到 `~/.openclaw/skills/predictclaw/`
2. 在安装后的 skill 目录执行：

```bash
cd {baseDir} && uv sync
cd {baseDir} && cp template.env .env
```

### 在仓库内本地开发

进入 `mandated-vault-factory/predict` 后执行：

```bash
uv sync
uv run pytest -q
uv run python scripts/predictclaw.py --help
```

## 配置实际上是怎么生效的

PredictClaw 本身只读取标准环境变量。当前已验证、可用的输入方式只有两种：

- 进程环境变量，例如 `export PREDICT_ENV=testnet`
- 本地 `{baseDir}/.env` 文件；`scripts/predictclaw.py` 启动时会自动加载它

如果两者同时存在，显式导出的环境变量优先，`.env` 只会补齐缺失项。

如果你的 OpenClaw 宿主版本会把配置注入成环境变量，PredictClaw 也能工作，因为它最终看到的仍然是普通 env。旧文档里提到过 `skills.entries.predictclaw.env`；现在应把它视为“某些宿主版本可能支持的便利映射”，而不是 PredictClaw 自己保证的标准配置入口。

SKILL frontmatter 的 metadata 里故意只声明通用入口变量：`PREDICT_ENV` 和 `PREDICT_WALLET_MODE`。OpenClaw 当前的 runtime metadata 是扁平的，不是按 mode 感知的；如果把所有 signer / vault 变量都塞进去，就会错误地暗示它们需要一次性全部填写。各模式自己的必填项以下面的示例和运行时配置校验为准。

## 首次配置（推荐）

1. 安装 skill 并执行 `uv sync`。
2. 先选择一个启动模板：
   - `template.env` -> 无 secret 的本地 fixture 启动
   - `template.readonly.env` -> live 只读市场读取
   - `template.eoa.env` -> 直接私钥交易
   - `template.predict-account.env` -> Predict Account 交易
   - `template.mandated-vault.env` -> 高级 vault control-plane / overlay
3. 在 `~/.openclaw/skills/predictclaw/` 中把选中的模板复制为 `.env`。
4. 只填写该模式需要的最小变量集。
5. 先用 `uv run python scripts/predictclaw.py --help` 确认安装无误。
6. 再按模式做一次验证：
   - fixture 启动 -> `uv run python scripts/predictclaw.py markets trending`
   - live read-only -> `uv run python scripts/predictclaw.py markets trending`
   - `eoa` / `predict-account` -> `uv run python scripts/predictclaw.py wallet status --json`
   - `mandated-vault` -> `uv run python scripts/predictclaw.py wallet deposit --json`

## 启动模板

- `template.env` -> 最安全的首装入口；使用 `test-fixture` + `read-only`，不需要 secrets，也不会访问网络
- `template.readonly.env` -> live 市场读取；mainnet 的市场读取需要 PREDICT_API_KEY
- `template.eoa.env` -> EOA signer 路线，从 `https://api-testnet.predict.fun` 的 testnet 起步
- `template.predict-account.env` -> Predict Account signer 路线，从 `https://api-testnet.predict.fun` 的 testnet 起步
- `template.mandated-vault.env` -> 高级显式 opt-in 的 vault control-plane 模板

## 真实首装路径

### A. 先确认 CLI 能启动

```bash
uv sync
uv run python scripts/predictclaw.py --help
```

### B. 无 secret 的本地验证

复制 `template.env` 后运行：

```bash
uv run python scripts/predictclaw.py markets trending
```

这条路径使用 `test-fixture`，只证明 skill 能正确启动、加载配置并路由命令，不会访问 live API。
fixture 模式只认识仓库自带的本地 market ID（`123`、`456`、`789`、`101`、`202`）。如果你要查询真实 market ID，请先切到 live read-only 模板。

### C. live read-only 市场读取

复制 `template.readonly.env`，再根据目标环境二选一：

- `mainnet` + 有效的 `PREDICT_API_KEY`，读取生产市场数据
- `testnet` + `https://api-testnet.predict.fun`，做非 mainnet 的匿名市场读取

```bash
uv run python scripts/predictclaw.py markets trending
uv run python scripts/predictclaw.py market <market_id> --json
```

如果 mainnet 读取返回 `401 unauthorized`，通常表示 `PREDICT_API_KEY` 缺失或无效。

### D. signer 路线

wallet status 需要 signer 配置。它适合 `eoa` 和 `predict-account` 的下一步验证，但不是 `read-only` 的第一条命令。

## 配置示例

下面的片段全部使用 `.env` 写法。你可以直接写进 `{baseDir}/.env`，也可以在 shell 里 `export` 同名变量。

`OPENROUTER_API_KEY` 只在非 fixture 的 `hedge scan` / `hedge analyze` 中需要；market、wallet、buy 流程都不依赖它。

### bootstrap-safe fixture 模式

```dotenv
PREDICT_ENV=test-fixture
PREDICT_WALLET_MODE=read-only
```

这个模式只适合无 secret 的 CLI 验证与本地市场浏览，不会访问 live API。需要执行 wallet / trade 子命令时，请切换到 `eoa`、`predict-account` 或 `mandated-vault`。

### live read-only 模式

```dotenv
PREDICT_ENV=mainnet
PREDICT_WALLET_MODE=read-only
PREDICT_API_KEY=YOUR_PREDICT_API_KEY
```

mainnet 的市场读取需要 PREDICT_API_KEY。如果你想做无 key 的非 mainnet 读取，请改用 `PREDICT_ENV=testnet`，并把 `PREDICT_API_BASE_URL` 设为 `https://api-testnet.predict.fun`。

### eoa 模式

```dotenv
PREDICT_ENV=testnet
PREDICT_WALLET_MODE=eoa
PREDICT_API_BASE_URL=https://api-testnet.predict.fun
PREDICT_PRIVATE_KEY=0xYOUR_EOA_PRIVATE_KEY
```

### predict-account 模式

```dotenv
PREDICT_ENV=testnet
PREDICT_WALLET_MODE=predict-account
PREDICT_API_BASE_URL=https://api-testnet.predict.fun
PREDICT_ACCOUNT_ADDRESS=0xYOUR_PREDICT_ACCOUNT
PREDICT_PRIVY_PRIVATE_KEY=0xYOUR_PRIVY_EXPORTED_KEY
```

### mandated-vault 模式（已知 deployed vault）

```dotenv
PREDICT_ENV=testnet
PREDICT_WALLET_MODE=mandated-vault
ERC_MANDATED_VAULT_ADDRESS=0xYOUR_DEPLOYED_VAULT
ERC_MANDATED_MCP_COMMAND=erc-mandated-mcp
ERC_MANDATED_CHAIN_ID=97
```

如果你当前的 MCP 路径需要 single-key preflight signer，再额外设置 `ERC_MANDATED_AUTHORITY_PRIVATE_KEY`。

### mandated-vault 模式（predicted / 未部署 vault）

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

`ERC_MANDATED_EXECUTOR_PRIVATE_KEY` 是可选项。未设置时，PredictClaw 会在当前 Preflight MVP 合约路径中复用 `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` 作为 executor signer。

在这条路径中，PredictClaw 会通过 MCP 预测 vault 地址；如果 vault 尚未部署，则返回 create-vault preparation 信息，而不会自动广播。该准备信息会以 `manual-only` 语义暴露。

### predict-account + vault overlay（推荐的高级资金路线）

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

在 overlay 路线中，Predict Account remains 入金地址与交易身份，而 Vault 通过 MCP 支持的 session / asset-transfer 规划来为 Predict Account 提供资金。

如果你还没有显式的 vault 地址，保留同一组 Predict Account 凭据，并把 `ERC_MANDATED_VAULT_ADDRESS` 改成完整 derivation tuple：`ERC_MANDATED_FACTORY_ADDRESS`、`ERC_MANDATED_VAULT_ASSET_ADDRESS`、`ERC_MANDATED_VAULT_NAME`、`ERC_MANDATED_VAULT_SYMBOL`、`ERC_MANDATED_VAULT_AUTHORITY`、`ERC_MANDATED_VAULT_SALT`。

可选的 overlay 限额：

```dotenv
ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX=5000000000000000000
ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW=10000000000000000000
ERC_MANDATED_FUNDING_WINDOW_SECONDS=3600
```

这些变量会限制 Vault→Predict 的单笔额度、窗口累计额度和窗口时长。以 BSC mainnet USDT 为例：`5U = 5000000000000000000`，`10U = 10000000000000000000`。

## 钱包模式

PredictClaw 支持四种显式 wallet mode：

- `read-only` — 仅浏览市场数据，不允许 signer-backed 钱包动作。
- `eoa` — 直接私钥 signer 路径，用于钱包、交易和资金相关流程。
- `predict-account` — 使用 `PREDICT_ACCOUNT_ADDRESS` 与 `PREDICT_PRIVY_PRIVATE_KEY` 的官方 Predict Account 路径。
- `mandated-vault` — 高级显式 opt-in control-plane 路径，仅用于受保护的 vault 状态与入金准备流程。

### 推荐路线

如果你希望保留官方 Predict 交易身份，同时由 Vault 提供资金，请使用：

- `PREDICT_WALLET_MODE=predict-account`
- 再叠加所需的 `ERC_MANDATED_*` overlay 输入

这样在 `wallet status --json` 与 `wallet deposit --json` 中会暴露 `vault-to-predict-account` 语义。

### pure mandated-vault 边界

`mandated-vault` 是一个高级显式 opt-in 模式，只适合你明确需要 MCP 辅助的 vault control-plane 时使用。

pure `mandated-vault` 不提供 predict.fun trading parity。`wallet approve`、`wallet withdraw`、`buy`、`positions`、`position`、`hedge scan`、`hedge analyze` 都会 fail closed，并返回 `unsupported-in-mandated-vault-v1`。

### 常见配置错误

- `read-only` 只能浏览市场；不要直接跑 signer-backed 的 wallet / trade 命令。
- `wallet status` 需要 signer 配置；在 `read-only` 下请先跑 `markets trending` 或 `market <id> --json`。
- mainnet 的市场读取需要 `PREDICT_API_KEY`；没配会在配置阶段直接失败，配错通常会返回 `401 unauthorized`。
- `testnet` 的市场读取应使用 `https://api-testnet.predict.fun`；旧的 `https://dev.predict.fun` 已不再匹配当前 API 合约。
- `eoa` 必须配置 `PREDICT_PRIVATE_KEY`，并且不能混用 Predict Account 或 mandated-vault 输入。
- `predict-account` 必须同时配置 `PREDICT_ACCOUNT_ADDRESS` 和 `PREDICT_PRIVY_PRIVATE_KEY`。
- `mainnet` 必须配置 `PREDICT_API_KEY`。
- pure `mandated-vault` 需要一个可用的 `ERC_MANDATED_MCP_COMMAND`；overlay 模式还需要 `ERC_MANDATED_VAULT_ASSET_ADDRESS` 与 `ERC_MANDATED_VAULT_AUTHORITY` 才能完成 funding orchestration。

## `ERC_MANDATED_MCP_COMMAND` / `@erc-mandated/mcp` 依赖说明

`ERC_MANDATED_MCP_COMMAND` 是 PredictClaw 与 mandated-vault MCP runtime 通信时使用的启动命令，默认值为 `erc-mandated-mcp`。

它在实际工作流中的作用有三层：

1. **Vault 预测与准备** — 当只有 derivation tuple 时，用 MCP 预测 vault 地址并生成准备信息。
2. **Vault overlay 编排** — 在 overlay 模式下暴露 `vault-to-predict-account` 路由、funding-policy 上下文与会话规划。
3. **控制面安全边界** — 当 MCP 不存在或不可用时，PredictClaw 会显式 fail closed，而不是静默猜测。

如果你的环境通过类似 `@erc-mandated/mcp` 的包来提供这套 runtime，那么你真正需要给 PredictClaw 配置的是该 runtime 对应的启动命令，也就是 `ERC_MANDATED_MCP_COMMAND`。PredictClaw 对外公开的契约是“命令入口”，而不是某个固定的包管理器依赖。

MCP orchestrates transport and preparation; the vault contract policy authorizes what the vault can actually execute.

## 命令面

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

## 核心工作流说明

- `wallet status` 会报告 signer mode、funding address、余额和 approval readiness。
- `wallet deposit` 会展示当前有效的 funding address 与可接受资产（`BNB`、`USDT`）。
- `wallet withdraw` 在尝试执行转账逻辑前会先验证目标地址 checksum、金额为正、余额充足以及 BNB gas 余量。
- 在 fixture 模式下，withdraw 会返回确定性的占位 tx hash，而不会触链。
- 在 `predict-account + ERC_MANDATED_*` overlay 中，`wallet status` / `wallet deposit` 会暴露：
  - `predictAccountAddress`
  - `tradeSignerAddress`
  - `vaultAddress`
  - `fundingRoute = vault-to-predict-account`
- Predict Account remains 入金地址与交易账户。
- 资金目标是 Predict Account，而不是 Vault，也不是 owner EOA。
- 可选的 Vault funding-policy 环境变量允许你限制 Vault→Predict 转账的单笔额度、窗口累计额度和窗口时长。
- 这些 funding-policy 金额使用 raw token units；以 BSC mainnet USDT（18 decimals）为例：`5 U = 5000000000000000000`，`10 U = 10000000000000000000`。
- 如果 Predict Account 已有足够余额，`buy` 会继续走官方 Predict Account 下单路径。
- 如果余额不足，`buy` 会以确定性的 `funding-required` 引导失败，并提示用户查看 `wallet deposit --json`；当前本地 signer 上下文不会自动执行 vault 资金腿。

## 运行模式

- `test-fixture` — 使用本地 JSON fixture 和确定性的 wallet / hedge / trade 行为，适合开发、集成测试、CI，以及无 secret 的首装验证。
- `testnet` — 用于 live 但非 mainnet 的检查；当前 REST 端点是 `https://api-testnet.predict.fun`，市场读取不需要 `PREDICT_API_KEY`。
- `mainnet` — 需要 `PREDICT_API_KEY`，即使只是市场读取也应视为真实交易环境。

## 环境变量

| 变量 | 作用 |
| --- | --- |
| `PREDICT_STORAGE_DIR` | 本地 journal 与持仓存储 |
| `PREDICT_ENV` | 代码默认是 `testnet`；`template.env` 刻意以 `test-fixture` 做 bootstrap；可选 `testnet`、`mainnet`、`test-fixture` |
| `PREDICT_WALLET_MODE` | 显式模式覆盖：`read-only`、`eoa`、`predict-account`、`mandated-vault` |
| `PREDICT_API_BASE_URL` | 可选 REST base override；留空时按环境自动选择（`testnet` -> `api-testnet.predict.fun`，`test-fixture` -> 忽略，`mainnet` -> `api.predict.fun`） |
| `PREDICT_API_KEY` | mainnet 认证后的 predict.fun API 访问；mainnet 市场读取与交易都需要它 |
| `PREDICT_PRIVATE_KEY` | EOA 交易与资金路径 |
| `PREDICT_ACCOUNT_ADDRESS` | Predict Account 智能钱包地址 |
| `PREDICT_PRIVY_PRIVATE_KEY` | Predict Account 模式下的 Privy 导出 signer |
| `ERC_MANDATED_VAULT_ADDRESS` | 已知部署好的 mandated vault 显式地址 |
| `ERC_MANDATED_FACTORY_ADDRESS` | 当未提供显式 vault 地址时，用于预测 vault 的 factory 地址 |
| `ERC_MANDATED_VAULT_ASSET_ADDRESS` | mandated-vault 预测 / create 准备时使用的 ERC-4626 资产 |
| `ERC_MANDATED_VAULT_NAME` | mandated-vault 预测 / create 准备时使用的 Vault 名称 |
| `ERC_MANDATED_VAULT_SYMBOL` | mandated-vault 预测 / create 准备时使用的 Vault 符号 |
| `ERC_MANDATED_VAULT_AUTHORITY` | Authority 地址，以及手动 create-vault 准备中的 `from` 地址 |
| `ERC_MANDATED_VAULT_SALT` | 用于 vault 预测 / create 准备的确定性 salt |
| `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` | 当前单密钥 MVP 合约路径的 Preflight Vault signer key |
| `ERC_MANDATED_EXECUTOR_PRIVATE_KEY` | 可选的 executor signer；未设置时回退到 `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` |
| `ERC_MANDATED_MCP_COMMAND` | MCP 启动命令（默认 `erc-mandated-mcp`） |
| `ERC_MANDATED_CONTRACT_VERSION` | 透传给 mandated-vault MCP client 的版本号 |
| `ERC_MANDATED_CHAIN_ID` | MCP bridge 的可选显式链选择 |
| `ERC_MANDATED_ALLOWED_ADAPTERS_ROOT` | 可选的 32-byte hex `allowedAdaptersRoot`，用于 Vault 执行 mandate；当前单密钥 MVP / PoC 路径默认 `0x11…11` |
| `ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX` | 可选的 Vault→Predict funding-policy `maxAmountPerTx`（raw token units） |
| `ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW` | 可选的 Vault→Predict funding-policy `maxAmountPerWindow`（raw token units） |
| `ERC_MANDATED_FUNDING_WINDOW_SECONDS` | 可选的 Vault→Predict funding-policy `windowSeconds` |
| `OPENROUTER_API_KEY` | hedge analysis 模型访问 |
| `PREDICT_MODEL` | OpenRouter 模型覆盖 |
| `PREDICT_SMOKE_ENV` | 启用 smoke suite |
| `PREDICT_SMOKE_API_BASE_URL` | 可选 smoke REST base override |
| `PREDICT_SMOKE_PRIVATE_KEY` | 启用 signer/JWT smoke 检查 |
| `PREDICT_SMOKE_ACCOUNT_ADDRESS` | Predict Account smoke 模式 |
| `PREDICT_SMOKE_PRIVY_PRIVATE_KEY` | Predict Account smoke signer |
| `PREDICT_SMOKE_API_KEY` | smoke REST auth |

## Hedge 说明

- Hedge analysis 通过 OpenRouter 的纯 HTTP JSON 合约实现。
- `OPENROUTER_API_KEY` 只在非 fixture 的 hedge analysis 中需要。
- fixture 模式使用确定性的关键字 / 配对逻辑，因此 CLI 与 integration tests 可以保持 secret-free。
- 当前公开命令面仍是 PolyClaw 对齐加上 `wallet deposit` / `wallet withdraw`；v1 仍没有公开 `sell` 命令。

## 项目结构

- `scripts/predictclaw.py` — 顶层 CLI router
- `scripts/` — 各命令入口脚本
- `lib/` — config、auth、REST、wallet、funding、trade、positions、hedge 与 MCP bridge 逻辑
- `tests/` — Python skill package 的 unit、integration、smoke 覆盖

## 验证层

```bash
# unit + command tests
uv run pytest -q

# fixture-backed end-to-end CLI checks
uv run pytest tests/integration -q

# env-gated smoke (passes or skips)
uv run pytest tests/smoke/test_testnet_smoke.py -q
```

## 安全说明

- 不要把 fixture 模式视作 funded-wallet 行为的证明。
- 不要仅凭 testnet 或 mainnet 文档就假设 live liquidity 一定存在。
- 自动化密钥应只保留有限资金。
- Withdraw 命令是公开能力；虽然转账前会做验证，但实际操作风险仍由用户承担。
- `predict-account + ERC_MANDATED_*` 是推荐的高级交易路线：Vault 给 Predict Account 提供资金，但 Predict Account 保持官方订单模型。
- 显式 vault 与 predicted vault 语义：`ERC_MANDATED_VAULT_ADDRESS` 直接指向已有 vault；否则 PredictClaw 会使用 derivation tuple 通过 MCP 预测 vault 地址。
- 如果 predicted vault 尚未部署，`wallet deposit` 可以返回包含 `predictedVault`、交易摘要和 `manual-only` 的 create-vault preparation 信息，但不会自动广播。
- pure `mandated-vault` 不提供 predict.fun trading parity，并会对不支持的路径以 `unsupported-in-mandated-vault-v1` 明确 fail closed。
