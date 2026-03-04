# BSC Testnet Fork E2E Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为已部署在 BSC Testnet chainId=97 的 VaultFactory/VenusAdapter/PancakeSwapV3Adapter 提供 fork-based E2E 测试：Layer A 在 fork 上本地部署合约做主覆盖；Layer B 直接对已部署合约做一致性校验 + 最小 smoke（Venus+Pancake），并采用“默认 fork 到最新 head，可选 env 固定 block”的策略。

**Architecture:** 测试分两层：Layer A 复用现有 `test/VaultForkBsc.*.t.sol` 基座与 helpers，覆盖核心业务与安全语义；Layer B 读取 `deployments/bsc-testnet.json`，在 fork head 上验证链上 code/codehash/leaf 与记录一致，并用链上 factory 做最小 smoke。对外部协议波动（Venus/Pancake）采用“协议不可用则 skip、非协议问题则 fail”的分诊策略，避免假绿。

**Tech Stack:** Foundry (forge-std Test + cheatcodes), Solidity 0.8.28, OpenZeppelin, `forge-std/StdJson` JSON 解析。

---

## 0. 约束与前置约定

1. 默认 fork 到最新 head
- 不强制 roll 到常量区块。
- 仅当设置了 `BSC_FORK_BLOCK` 环境变量时，才尝试 `vm.rollFork(BSC_FORK_BLOCK)`。
- 若 roll 失败，使用 `vm.skip(true, reason)`，并在 reason 中打印 block 号与建议。

2. 两层测试职责边界
- Layer A 本地部署到 fork：语义与安全、失败模式尽量确定性覆盖。
- Layer B 链上已部署合约：部署一致性校验 + 最小 smoke，不强求完整协议路径。

3. 关于 ActionCallFailed 包装
- 外部协议或 adapter 内部 revert 往往会被 `MandatedVaultClone` 包装成 `IERCXXXXMandatedVault.ActionCallFailed(index, reason)`。
- 测试必须区分：vault 自身校验（直接 revert） vs action 执行失败（ActionCallFailed）。

---

## Task 1: 调整 BSC fork 基座，默认使用最新 head（可选固定 block）

**Files:**
- Modify: `test/VaultForkBsc.Base.t.sol`

**Steps:**
1. 新增 guard 测试：当未设置 `BSC_FORK_BLOCK` 时，不会强制 roll。
2. 修改 `setUp()`：只在 env 存在时 `vm.rollFork`；失败则 skip。
3. 运行 fork 测试集确认通过。

---

## Task 2: Layer A — 用户故事驱动测试（本地部署到 fork）

**Files:**
- Create: `test/VaultForkBsc.Security.t.sol`
- Create: `test/VaultForkBsc.CoreSemantics.t.sol`
- Modify: `test/VaultForkBsc.Venus.t.sol`, `test/VaultForkBsc.Pancake.t.sol`, `test/VaultForkBsc.Multi.t.sol`

**Coverage:**
- US-01 deterministic predict + create
- US-02B VaultBusy reenter deposit/withdraw (wrapped as ActionCallFailed)
- US-03A/B/C UnauthorizedExecutor + InvalidSignature + PayloadDigestMismatch (direct revert)
- US-04 allowlist leaf mismatch / EOA / NonZeroActionValue
- US-08 drawdown breaker (postExecution direct revert)
- US-09 nonce used / threshold / revoke
- US-10 authority epoch mismatch

---

## Task 3: Layer B — 部署一致性校验 + 最小 smoke

**Files:**
- Create: `test/helpers/BscTestnetDeploymentJson.sol`
- Create/Modify: `test/VaultForkBsc.DeployedConsistency.t.sol`
- Modify: `deployments/bsc-testnet.json`
- Modify: `foundry.toml`

**Acceptance Criteria:**
1. `deployments/bsc-testnet.json` 填充真实值：
- factory 地址
- adapters 地址
- adapterCodehashes 与 adapterLeaves

2. `foundry.toml` 配置最小 `fs_permissions`：read-only + `./deployments`。

3. 测试在 fork head 可跑：
- 静态一致性：adapter code/codehash/leaf match json。
- 最小 smoke：使用已部署 `VaultFactory` 做 `predictVaultAddress == createVault`，并断言 vault 有 code。

---

## Task 4: 文档与运行指南更新

**Files:**
- Modify: `docs/e2e-fork-user-stories.md`

**Steps:**
1. 补充运行命令：head 默认策略 + `BSC_FORK_BLOCK` 固定复现。
2. 增加 fork infra 常见失败提示（missing trie node、RPC 限流）。

---

## Task 5: 验证与质量门槛

1) 全量 BSC fork head 模式：

```
forge test --match-test '^test_bscFork_' --fork-url "$BSC_RPC_URL"
```

预期：
- Layer A 语义与安全测试 PASS。
- Venus/Pancake 若协议不可用，按分诊逻辑 skip。

2) Layer B deployed consistency：

```
forge test --match-path test/VaultForkBsc.DeployedConsistency.t.sol --fork-url "$BSC_RPC_URL"
```

---

<!-- 本计划文件是为了补齐 docs/plans 目录缺失而回填；执行记录与代码状态以仓库实际变更为准。 -->
