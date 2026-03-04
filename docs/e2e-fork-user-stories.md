# E2E Fork Test User Stories: Production-Grade DeFi Protocol Integration

This document is intended for developers, strategy designers, auditors, and operations teams. It uses a "User Story + Test Flow + Production Guide" format to detail end-to-end verification of Mandated Vault on real Ethereum mainnet DeFi protocols.

## Document Goals

1. **Explain what each E2E test validates** and its significance for production deployment
2. **Provide strategy design templates** so strategy teams can reference test code to build production mandates
3. **Document production pitfalls**, including drawdown semantics, token compatibility, and Merkle tree construction

## Architectural Prerequisites

### Vault Call Pattern

```
vault → adapter.call{value:0}(data)
         ↓
    msg.sender = vault address
    msg.value  = 0 (enforced)
```

**Key takeaways**:
- The vault directly acts as `msg.sender` when calling DeFi protocols — no custom adapter contracts needed
- The `Action.adapter` field is actually the "call target address" (e.g., USDC contract, Aave Pool contract)
- All DeFi operations (approve, supply, swap, etc.) are ordinary contract calls initiated by the vault as itself

### Drawdown Circuit Breaker Semantics

`totalAssets()` = `IERC20(asset).balanceOf(vault)` — only counts the underlying asset balance.

| Operation | totalAssets Change | Required maxDrawdownBps |
|-----------|-------------------|------------------------|
| Aave supply (USDC out) | -100% | 10000 |
| Aave withdraw (USDC back) | +N% | 0 |
| Uniswap swap (USDC → WETH) | -100% | 10000 |
| Round-trip (supply + withdraw same block) | ~0% | 50 |

**Production implication**: When the authority signs a mandate, `maxDrawdownBps` must match the strategy type. Supplying all assets to a lending protocol = 100% drawdown — this is by design, not a bug.

### Merkle Adapter Allowlist

Each action's target address must be in the Merkle tree. leaf = `keccak256(abi.encode(address, address.codehash))`.

- USDC/Aave/Compound are all proxy contracts; codehash reflects the proxy bytecode (stable), not the implementation
- A strategy needs at least 2 leaves: one for token approve, one for protocol call
- Multi-protocol strategies need 3+ leaves

---

## Test Environment

| Config | Value | Notes |
|--------|-------|-------|
| Fork target | Ethereum mainnet | Real on-chain state |
| Fork block | 21,000,000 | Nov 2024, all protocols active |
| RPC source | `--fork-url` CLI argument | Not written to foundry.toml to avoid build failures in no-RPC environments |
| Skip mechanism | `vm.activeFork()` + `block.chainid == 1` | Auto-skipped without fork, no CI impact |

### Run Commands

```bash
# Run only fork tests (requires RPC)
ETH_RPC_URL=<your-mainnet-rpc-url> \
  forge test --match-path test/VaultFork.t.sol \
  --fork-url $ETH_RPC_URL --fork-block-number 21000000

# Normal CI (no fork tests, no RPC needed)
forge test --match-path 'test/Vault{Factory,Branch}.t.sol'

# Full run (fork tests auto-skip if no --fork-url)
forge test
```

---

## 如何运行 BSC Fork 测试

### 默认策略：使用 fork head

BSC fork 测试默认以当前 provider 的最新区块 head 运行，不强制回滚到固定历史块。

原因：

1. 公共 BSC RPC 经常不保留完整历史状态，强制回滚历史块容易出现基础设施错误（例如 `missing trie node`）。
2. Venus 和 Pancake 在测试网状态会持续变化，head 模式更贴近“当前已部署现实”，适合 smoke 与回归。
3. 当需要复现时，再通过环境变量显式固定 `BSC_FORK_BLOCK`，避免默认路径被历史状态可用性影响。

### 可复制命令

仅运行 BSC fork 测试（默认 head）：

```
BSC_RPC_URL=<your-bsc-testnet-rpc> \
forge test --match-test '^test_bscFork_' --fork-url "$BSC_RPC_URL" --chain-id 97
```

固定区块复现（可选 `BSC_FORK_BLOCK`）：

```
BSC_RPC_URL=<your-bsc-testnet-rpc> \
BSC_FORK_BLOCK=93533855 \
forge test --match-test '^test_bscFork_' --fork-url "$BSC_RPC_URL" --chain-id 97
```

固定区块并要求启动即在该块（更严格复现）：

```
BSC_RPC_URL=<your-bsc-testnet-rpc> \
BSC_FORK_BLOCK=93533855 \
forge test --match-test '^test_bscFork_' --fork-url "$BSC_RPC_URL" --fork-block-number "$BSC_FORK_BLOCK" --chain-id 97
```

### 失败排查与 RPC 建议

如果出现以下现象：

- `missing trie node`
- `header not found`
- 在固定块模式下频繁 `failed to roll fork to BSC_FORK_BLOCK`

优先按顺序处理：

1. 先去掉 `BSC_FORK_BLOCK`，确认默认 head 模式可运行。
2. 替换为稳定性更高的 BSC testnet RPC（优先付费/归档节点）。
3. 如需固定块复现，使用支持历史状态查询的 RPC，再重新执行固定块命令。

---

## Part 1: Real Token ERC-4626 Compatibility (3 Tests)

### Story 1.1: Deposit / Withdraw with Real USDC

> **As a** fund administrator,
> **I want** to confirm the vault correctly handles deposit and withdraw with real USDC (6 decimals, proxy contract),
> **So that** investors can safely deposit and withdraw funds.

**Test**: `test_fork_usdc_depositWithdraw`

**Flow**:

```
1. Create a vault with USDC as the underlying asset
2. Deal 100 USDC to bob
3. bob approve vault → deposit 100 USDC
4. Assert: shares > 0, totalAssets == 100 USDC
5. bob withdraw 50 USDC
6. Assert: shares halved, totalAssets == 50 USDC
```

**Acceptance Criteria**:
- First deposit mints shares 1:1 (vault is empty)
- After partial withdraw, shares and assets maintain correct mathematical relationship
- 6 decimals precision produces no overflow or precision loss under ERC-4626 math

**Production Notes**:
- USDC is a proxy contract; `deal()` may need `stdstore` fallback in Foundry
- In production, real users perform a two-step approve + deposit via the frontend

---

### Story 1.2: Verify 18 Decimals Handling with Real DAI

> **As a** strategy team,
> **I want** to confirm the vault correctly handles 18-decimal DAI,
> **So that** tokens with different precision can serve as the vault's underlying asset.

**Test**: `test_fork_dai_depositWithdraw`

**Flow**:

```
1. Create a vault with DAI as the underlying asset
2. bob deposit 100 DAI (100e18)
3. Assert shares and totalAssets
4. bob redeem all shares
5. Assert bob receives 100 DAI, vault totalAssets == 0
```

**Acceptance Criteria**:
- No precision loss on deposit → full redeem with 18 decimals
- Both redeem path (shares→assets) and withdraw path (assets→shares) are correct

---

### Story 1.3: Verify via Mint / Redeem Reverse Path

> **As an** integration developer,
> **I want** to verify that ERC-4626's mint (specify shares) and redeem paths work correctly with real tokens,
> **So that** the frontend can support both "deposit by amount" and "deposit by shares" UX.

**Test**: `test_fork_usdc_mintRedeem`

**Flow**:

```
1. Create USDC vault
2. Call previewMint(50e6) to preview how much USDC is needed
3. bob approve + mint 50e6 shares
4. Assert actualAssets == previewMint return value
5. bob redeem all shares → receives same USDC
```

**Acceptance Criteria**:
- `previewMint` preview matches actual consumption
- mint → redeem complete round-trip with no fund loss

---

## Part 2: Aave V3 Integration (5 Tests)

### Merkle Tree Construction

```
Aave strategy needs 2 leaves:
  leafUsdc = keccak256(abi.encode(USDC, USDC.codehash))
  leafAave = keccak256(abi.encode(AAVE_POOL, AAVE_POOL.codehash))
  root = hashPair(leafUsdc, leafAave)  // sorted
```

### Story 2.1: Aave V3 Supply — Deploy Vault Assets to Lending Market

> **As a** strategy executor,
> **I want** to supply all of the vault's USDC to Aave V3 to earn interest,
> **So that** investors' idle funds generate yield.

**Test**: `test_fork_aave_supply`

**Flow**:

```
1. Create USDC vault, deal 10,000 USDC to vault
2. Build 2-leaf Merkle tree (USDC + AAVE_POOL)
3. Build 2 actions:
   - Action 0: USDC.approve(AAVE_POOL, 10000e6)
   - Action 1: AavePool.supply(USDC, 10000e6, vault, 0)
4. Authority signs mandate (maxDrawdownBps=10000)
5. Executor executes mandate
6. Assert: vault USDC == 0, vault aUSDC ≈ 10000e6
```

**Acceptance Criteria**:
- Vault successfully authorizes Aave Pool to pull USDC
- Aave `transferFrom`s USDC from vault and mints aUSDC to vault
- maxDrawdownBps=10000 because supplying all assets = 100% drawdown

**Production Strategy Template**:

```solidity
// Production mandate parameters signed by authority
Mandate({
    executor: trustedBot,
    maxDrawdownBps: 10000,        // supply = 100% underlying outflow
    maxCumulativeDrawdownBps: 10000,
    allowedAdaptersRoot: merkle(USDC, AAVE_POOL),
    // ...
})

// Production actions submitted by executor
actions[0] = Action(USDC, 0, approve(AAVE_POOL, amount))
actions[1] = Action(AAVE_POOL, 0, supply(USDC, amount, vault, 0))
```

---

### Story 2.2: payloadDigest Binding — Restrict Executor to Predetermined Actions

> **As an** authority (signer),
> **I want** to bind the mandate to a specific action sequence, preventing the executor from substituting operations,
> **So that** even if the executor is compromised, the signature cannot be used for other operations.

**Test**: `test_fork_aave_supply_withPayloadDigestBinding`

**Flow**:

```
1. Same actions as Story 2.1
2. Additional step: m.payloadDigest = v.hashActions(actions)
3. Authority signs mandate containing payloadDigest
4. Executor executes — only the exact same actions pass validation
```

**Acceptance Criteria**:
- When `payloadDigest != bytes32(0)`, the contract verifies `keccak256(abi.encode(actions)) == payloadDigest`
- Any change to actions (amount, target, ordering) causes revert

**Production Notes**:
- High-security scenarios use payloadDigest binding: authority pre-signs specific operations, executor is merely a "submitter"
- Low-security scenarios can set `payloadDigest=0`: authority only restricts callable contract scope, executor freely composes specific operations

---

### Story 2.3: Aave V3 Withdraw — Retrieve Assets from Lending Market

> **As a** strategy executor,
> **I want** to withdraw all aUSDC from Aave V3, returning USDC to the vault,
> **So that** funds are available for investor redemption or redeployment.

**Test**: `test_fork_aave_withdraw`

**Flow**:

```
1. Pre-populate position: execute approve + supply (maxDrawdownBps=10000)
2. Second execute: AavePool.withdraw(USDC, type(uint256).max, vault)
   - maxDrawdownBps=0 (withdrawal only increases totalAssets, no drawdown)
3. Assert: vault USDC ≈ 10000e6, aUSDC == 0
```

**Acceptance Criteria**:
- Two executes use different nonces (replay protection)
- After withdrawal preAssets=0 → postAssets=10000e6, this is a positive change, does not trigger drawdown
- `type(uint256).max` means "withdraw all", Aave internally calculates the actual amount

**Production Notes**:
- `maxDrawdownBps=0` is safe for withdraw operations since totalAssets only increases
- However `maxCumulativeDrawdownBps` may need a higher value (see Compound roundTrip pitfall)

---

### Story 2.4: Aave Round-trip — Same-Block Supply + Withdraw Verifies Zero Loss

> **As an** auditor,
> **I want** to verify that supply + withdraw within the same execution leaves assets nearly unchanged,
> **So that** there is no unexpected fund leakage from protocol interaction.

**Test**: `test_fork_aave_roundTrip`

**Flow**:

```
1. Vault holds 10,000 USDC
2. Single execute with 3 actions:
   - approve(AAVE_POOL, amount)
   - supply(USDC, amount, vault, 0)
   - withdraw(USDC, type(uint256).max, vault)
3. maxDrawdownBps=50 (~0.5%) — allows minimal rounding difference
4. Assert post ≈ pre (assertApproxEqAbs, tolerance 2 wei)
```

**Acceptance Criteria**:
- Same-block supply + withdraw produces no interest accrual, totalAssets should fully recover
- Rounding tolerance within 2 wei (Aave internal precision handling)

---

### Story 2.5: Drawdown Circuit Breaker Trigger — Over-Limit Operations Rejected

> **As an** authority (risk signer),
> **I want** transactions to automatically revert when the executor attempts to move assets beyond the allowed ratio,
> **So that** even if the executor is malicious or erroneous, over-limit operations are impossible.

**Test**: `test_fork_aave_drawdownTriggered`

**Flow**:

```
1. Vault holds 10,000 USDC
2. Actions: supply 60% USDC (6,000 USDC) to Aave
3. Mandate sets maxDrawdownBps=5000 (50%)
4. Executor executes → vm.expectRevert(DrawdownExceeded.selector)
```

**Acceptance Criteria**:
- supply 6,000/10,000 = 60% drawdown > 50% limit → revert
- Funds not actually moved (transaction rolled back)

**Production Notes**:
- `maxDrawdownBps` is the "single-execution loss cap" granted by the authority to the executor
- Production strategies should match precisely: partial supply uses proportional value (e.g., 5000), full supply uses 10000

---

## Part 3: Uniswap V3 Integration (3 Tests)

### Story 3.1: Token Swap — Vault Swaps via Uniswap

> **As a** strategy executor,
> **I want** to swap the vault's USDC for WETH via Uniswap V3,
> **So that** multi-asset allocation strategies can be implemented.

**Test**: `test_fork_uniswap_swapExact`

**Flow**:

```
1. Vault holds 10,000 USDC
2. Build Merkle tree: USDC + UNISWAP_ROUTER
3. Actions:
   - USDC.approve(UNISWAP_ROUTER, amount)
   - SwapRouter.exactInputSingle({
       tokenIn: USDC, tokenOut: WETH,
       fee: 500 (0.05% pool),
       recipient: vault,
       deadline: block.timestamp + 1,
       amountIn: amount,
       amountOutMinimum: 0,
       sqrtPriceLimitX96: 0
     })
4. maxDrawdownBps=10000 (after swap, underlying asset USDC goes to zero)
5. Assert: vault USDC == 0, vault WETH > 0
```

**Acceptance Criteria**:
- Vault successfully executes swap via Uniswap
- WETH credited to vault (recipient set to vault address)
- drawdown = 100% (underlying asset entirely converted to non-underlying asset)

**Production Notes**:
- `deadline` must be >= `block.timestamp`; setting to 0 will revert
- `fee=500` is the highest liquidity pool for USDC/WETH (0.05%); production may use 3000 or 10000
- `amountOutMinimum=0` is for testing only; production must set reasonable slippage protection

---

### Story 3.2: Selector Allowlist — Restrict Callable Functions

> **As an** authority,
> **I want** to restrict callable function signatures beyond the contract-level adapter allowlist,
> **So that** the executor can only execute approve + swap, and cannot call any other function.

**Test**: `test_fork_uniswap_withSelectorAllowlist`

**Flow**:

```
1. Build selector allowlist extension:
   - selLeaf0 = keccak256(abi.encode(USDC, approve.selector))
   - selLeaf1 = keccak256(abi.encode(UNISWAP_ROUTER, exactInputSingle.selector))
   - selRoot = hashPair(selLeaf0, selLeaf1)
2. Build Extension array:
   Extension({
     id: bytes4(keccak256("erc-xxxx:selector-allowlist@v1")),
     required: false,
     data: abi.encode(selRoot, selectorProofs)
   })
3. mandate.extensionsHash = keccak256(abi.encode(extensions))
4. Executor executes with extensions parameter
5. Assert: swap succeeds (approve + exactInputSingle are both in the allowlist)
```

**Acceptance Criteria**:
- Selector allowlist is a fine-grained complement to the adapter allowlist
- Different functions on the same contract can be independently allowed/denied
- Extensions are bound to the mandate signature via `extensionsHash`

**Production Notes**:
- Selector allowlist is an optional extension; it does not affect mandates that don't use it
- Recommended for high-security scenarios: restrict executor to only approve + specific protocol entry functions
- Selector allowlist Merkle leaf = `keccak256(abi.encode(adapter, selector))`

---

### Story 3.3: Slippage Protection — Uniswap Internal Revert Propagated Correctly

> **As a** risk control system,
> **I want** the entire execution to roll back when swap conditions are not met (e.g., slippage exceeded),
> **So that** investor funds are not swapped under unfavorable conditions.

**Test**: `test_fork_uniswap_slippageProtection`

**Flow**:

```
1. Same as Story 3.1, but amountOutMinimum = type(uint256).max
2. Uniswap cannot produce that much WETH → internal revert
3. Vault catches and wraps as ActionCallFailed
4. Assert: vm.expectPartialRevert(ActionCallFailed.selector)
```

**Acceptance Criteria**:
- External contract revert is caught by the vault's `_executeActions`
- Original revert reason preserved in `ActionCallFailed(index, returndata)`
- Entire execution rolls back, funds untouched

---

## Part 4: Compound V3 Integration (2 Tests)

### Story 4.1: Compound V3 Supply

> **As a** strategy executor,
> **I want** to supply the vault's USDC to Compound V3 (Comet) to earn interest,
> **So that** the vault is verified compatible with another major lending protocol.

**Test**: `test_fork_compound_supply`

**Flow**:

```
1. Vault holds 10,000 USDC
2. Merkle tree: USDC + COMPOUND_COMET
3. Actions: approve(COMET, amount) + Comet.supply(USDC, amount)
4. maxDrawdownBps=10000
5. Assert: vault USDC == 0, IComet(COMET).balanceOf(vault) > 0
```

**Acceptance Criteria**:
- Compound V3's `supply(asset, amount)` has a different interface from Aave's `supply(asset, amount, onBehalfOf, ref)`, but the vault can call both directly
- Comet balance is queried via `IComet.balanceOf`, not via an ERC-20 aToken

---

### Story 4.2: Compound Round-trip — Supply + Withdraw Complete Loop

> **As an** auditor,
> **I want** to verify that Compound supply + withdraw returns funds intact to the vault,
> **So that** there is no fund leakage.

**Test**: `test_fork_compound_roundTrip`

**Flow**:

```
1. First execute: approve + supply (maxDrawdownBps=10000)
2. Read Comet balance
3. Second execute: Comet.withdraw(USDC, cometBalance)
   - maxDrawdownBps=0
   - maxCumulativeDrawdownBps=10000  ← critical!
4. Assert: vault USDC ≈ 10000e6 (tolerance 10 wei)
```

**Acceptance Criteria**:
- supply + withdraw round-trip fund loss <= 10 wei (Compound rounding)

**Production Pitfall**:

> **Pitfall**: Initially set `maxCumulativeDrawdownBps=0` for the withdraw mandate, causing `CumulativeDrawdownExceeded` revert.
>
> **Root cause**: After supply, `_epochAssets` was updated to 0 (because totalAssets dropped to 0). When the epoch's high-water mark is 10,000 USDC but current is 0, cumulative drawdown is already 100%. Withdrawal bringing back funds is "positive", but the epoch state machine has already recorded 100% cumulative decline.
>
> **Fix**: The withdraw mandate must explicitly set `maxCumulativeDrawdownBps=10000`, allowing 100% cumulative change range within the epoch.
>
> **Production lesson**: When implementing supply-then-withdraw across multiple executes, each execute independently validates cumulative drawdown. Strategy design must account for epoch state evolution.

---

## Part 5: Multi-Protocol Combination Strategy (2 Tests)

### Story 5.1: Split Strategy — 50% Aave + 50% Uniswap

> **As a** strategy team,
> **I want** to operate multiple DeFi protocols within a single mandate execution,
> **So that** complex asset allocation strategies can be implemented.

**Test**: `test_fork_multiProtocol_aaveAndUniswap`

**Flow**:

```
1. Vault holds 10,000 USDC
2. Build 3-leaf Merkle tree: USDC + AAVE_POOL + UNISWAP_ROUTER
3. 4 actions (single execute):
   - USDC.approve(AAVE_POOL, 5000e6)
   - AavePool.supply(USDC, 5000e6, vault, 0)
   - USDC.approve(UNISWAP_ROUTER, 5000e6)
   - SwapRouter.exactInputSingle(USDC→WETH, 5000e6)
4. Proof mapping:
   - action[0] USDC proof = treeProofs[0]
   - action[1] AAVE proof = treeProofs[1]
   - action[2] USDC proof = treeProofs[0]  // reused!
   - action[3] ROUTER proof = treeProofs[2]
5. maxDrawdownBps=10000
6. Assert: USDC==0, aUSDC>0, WETH>0
```

**Acceptance Criteria**:
- 3-leaf Merkle tree correctly constructed (padded to 4; last leaf self-duplicated)
- USDC proof reused by two approve actions without issue
- `adapterProofs.length == actions.length`, even if proofs repeat, the array must be fully populated

**Production Strategy Template**:

```solidity
// 3-leaf Merkle tree construction
bytes32 leafUsdc = keccak256(abi.encode(USDC, USDC.codehash));
bytes32 leafAave = keccak256(abi.encode(AAVE_POOL, AAVE_POOL.codehash));
bytes32 leafRouter = keccak256(abi.encode(UNISWAP_ROUTER, UNISWAP_ROUTER.codehash));

// buildTree3 internally pads to 4 leaves: [USDC, AAVE, ROUTER, ROUTER]
(root, proofs) = MerkleHelper.buildTree3(leafUsdc, leafAave, leafRouter);

// Proof mapping rules:
// proofs[0] = USDC proof → used for all USDC.approve actions
// proofs[1] = AAVE proof → used for AavePool.supply
// proofs[2] = ROUTER proof → used for SwapRouter.exactInputSingle
```

---

### Story 5.2: Independent Merkle Proof Verification

> **As a** security auditor,
> **I want** to independently verify that MerkleHelper-generated proofs are compatible with the OpenZeppelin MerkleProof library,
> **So that** the custom Merkle tooling has no implementation bugs.

**Test**: `test_fork_multiProtocol_merkleProof`

**Flow**:

```
1. Build 3-leaf Merkle tree
2. For each leaf, verify with OZ MerkleProof.verify(proof, root, leaf)
3. Three assertTrue calls verify USDC, Aave, and Router proofs respectively
```

**Acceptance Criteria**:
- MerkleHelper's sorted-pair hashing is fully compatible with OZ MerkleProof
- Each leaf's proof can be verified independently without interference

---

## Part 6: Full Lifecycle (1 Test)

### Story 6.1: Complete DeFi Vault Lifecycle from Deployment to Redemption

> **As a** product owner,
> **I want** to verify the vault's complete lifecycle: deploy→deposit→strategy execute→strategy unwind→redeem,
> **So that** the end-to-end user experience has no breakpoints.

**Test**: `test_fork_fullLifecycle`

**Flow**:

```
 1. Deploy VaultFactory (completed in setUp)
 2. Create USDC vault (creator=alice)
 3. Bob deposits 10,000 USDC (deposit)
    → Assert shares == 10000e6 (1:1 first deposit)
 4. Authority signs mandate: supply all to Aave
 5. Executor executes mandate (approve + supply)
 6. Assert vault's aUSDC ≈ 10,000e6
 7. Authority signs new mandate: withdraw all
 8. Executor executes mandate (withdraw)
 9. Bob redeems all shares (redeem)
10. Assert Bob receives ≈ 10,000 USDC (same block = exact equality)
```

**Acceptance Criteria**:
- 10-step complete loop, no step failures
- Bob's withdrawal amount differs from deposit by <= 2 wei
- Intermediate steps (supply/withdraw) do not impact final user experience

**This test is the ultimate validation for production deployment confidence.**

---

## Part 7: Security Boundaries (3 Tests)

### Story 7.1: Unauthorized Protocol Blocked

> **As a** security engineer,
> **I want** to confirm the executor cannot call contracts outside the Merkle tree,
> **So that** even if the executor is compromised, it can only operate on protocols explicitly allowed by the authority.

**Test**: `test_fork_unauthorizedProtocol`

**Flow**:

```
1. Merkle root = USDC leaf only (single leaf = root)
2. Attempt to call AAVE_POOL (not in Merkle tree)
3. Provide empty proof (bytes32[](0))
4. Assert revert: AdapterNotAllowed
```

**Acceptance Criteria**:
- Merkle proof verification failure → immediate revert
- Execution never reaches the action execution stage

---

### Story 7.2: Selector Allowlist Blocks Unauthorized Functions

> **As an** authority,
> **I want** to restrict callable functions even if the contract is in the adapter allowlist,
> **So that** the executor cannot call borrow(), flashLoan(), or other dangerous functions.

**Test**: `test_fork_selectorBlock`

**Flow**:

```
1. Adapter allowlist: both USDC + AAVE_POOL are allowed
2. Selector allowlist: only USDC.approve + AavePool.supply allowed
3. Executor attempts to call AavePool.withdraw (not in selector allowlist)
4. Assert revert: SelectorNotAllowed
```

**Acceptance Criteria**:
- Adapter passes (AAVE_POOL is in the Merkle tree)
- Selector fails (withdraw.selector is not in the selector allowlist)
- Two defense layers operate independently

**Production Notes**:
- Selector allowlist is the second gate in a defense-in-depth strategy
- Recommended for high-risk protocols: only allow supply/withdraw, deny borrow/flashLoan/liquidate

---

### Story 7.3: Proxy Contract Codehash Stability Verification

> **As a** security researcher,
> **I want** to confirm that proxy contract codehash remains stable across different blocks,
> **So that** I understand codehash binding behavior in proxy upgrade scenarios.

**Test**: `test_fork_proxyCodehashStability`

**Flow**:

```
1. Record codehash of USDC/Aave/Compound at FORK_BLOCK
2. Assert all codehash != 0 (contracts exist)
3. vm.rollFork(FORK_BLOCK + 1)
4. Assert codehash unchanged
5. Assert Merkle leaf determinism: same leaf = reusable
```

**Acceptance Criteria**:
- Proxy contract codehash reflects the proxy bytecode (stable), not the implementation bytecode
- Codehash is stable across blocks → Merkle proofs remain valid when executed at different blocks

**Production Implications (Known Limitation)**:
- After a proxy implementation upgrade, codehash does not change → Merkle proof remains valid
- This means the adapter allowlist cannot detect malicious upgrades at the implementation layer
- This is a known limitation documented in the design specification

---

## Part 8: Token Edge Compatibility (1 Test)

### Story 8.1: USDT Non-Standard ERC-20 Compatibility

> **As an** integration developer,
> **I want** to confirm that a vault with USDT as the underlying asset works correctly,
> **So that** the vault can support the market's largest non-standard ERC-20 token.

**Test**: `test_fork_usdt_asVaultAsset`

**Flow**:

```
1. Create a vault with USDT as the underlying asset
2. Deal 100 USDT to bob
3. bob approve vault (using low-level call, not IERC20 interface)
   (bool ok,) = USDT.call(abi.encodeWithSelector(
     IERC20.approve.selector, address(v), depositAmt
   ))
4. bob deposit 100 USDT
5. bob withdraw all
6. Assert totalAssets == 0
```

**Acceptance Criteria**:
- USDT's `approve()` does not return `bool` (non-standard), but the vault's `SafeERC20` handles it correctly
- deposit / withdraw paths work normally

**Production Pitfall**:

> **Pitfall**: Initially used `IERC20(USDT).approve(address(v), amount)`, ABI decode reverted (USDT.approve does not return bool).
>
> **Fix**: Test code uses low-level `call` for approve. The actual vault contract internally uses OZ's `SafeERC20`, which automatically handles non-standard return values.
>
> **Production lesson**: Test code calling USDT directly must use low-level call or `SafeERC20.forceApprove`. The vault contract itself has no such issue (ERC4626Upgradeable internally uses SafeERC20).

---

## Production Usage Guide

### Strategy Design Checklist

| Step | Content | Reference Tests |
|------|---------|----------------|
| 1. Identify target protocols | List contract addresses to call | Part 2-4 |
| 2. Build Merkle tree | Compute leaf for each contract, build tree and proofs | Story 5.1, 5.2 |
| 3. Design actions | List approve + protocol call sequence | Story 2.1 |
| 4. Calculate drawdown | Determine maxDrawdownBps based on strategy type | Story 2.5 |
| 5. Consider cumulative | Set reasonable maxCumulativeDrawdownBps for multi-execute | Story 4.2 |
| 6. Optional selector restriction | Add selector allowlist for high-risk protocols | Story 3.2, 7.2 |
| 7. Optional payload binding | Bind payloadDigest for high-security scenarios | Story 2.2 |
| 8. Test round-trip | Verify supply + withdraw loop on fork first | Story 2.4, 4.2 |

### Drawdown Parameter Quick Reference

| Strategy Type | maxDrawdownBps | maxCumulativeDrawdownBps | Notes |
|--------------|---------------|-------------------------|-------|
| Full supply | 10000 | 10000 | 100% underlying outflow |
| Partial supply (X%) | X * 100 | 10000 | Proportional limit |
| Round-trip (same execute) | 50 | 10000 | Near-zero loss |
| Withdraw only | 0 | 10000 | Only increases |
| Swap (non-underlying asset) | 10000 | 10000 | Underlying fully converted |

### CI Integration Recommendations

```yaml
# GitHub Actions example
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: foundry-rs/foundry-toolchain@v1
      - run: forge test --match-path 'test/Vault{Factory,Branch}.t.sol'

  fork-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: foundry-rs/foundry-toolchain@v1
      - run: |
          forge test --match-path test/VaultFork.t.sol \
            --fork-url ${{ secrets.ETH_RPC_URL }} \
            --fork-block-number 21000000
```

**Recommendations**:
- Unit tests (69): Run on every PR, no RPC needed
- Fork tests (20): Run on merge to main or manual trigger, requires RPC quota
- Fork test RPC: Use a paid provider or Foundry local cache to avoid rate limits

---

## File Inventory

| File | Lines | Content |
|------|-------|---------|
| `test/VaultFork.t.sol` | ~900 | 20 E2E fork tests |
| `test/helpers/ForkConstants.sol` | ~53 | Mainnet address constants + protocol interfaces |
| `test/helpers/MerkleHelper.sol` | ~56 | Merkle tree construction library (2/3/4 leaves) |

## Test Overview

| Part | Count | Coverage | Key Validation |
|------|-------|----------|---------------|
| 1. Token compatibility | 3 | USDC/DAI deposit-withdraw-mint-redeem | ERC-4626 correctness across token decimals |
| 2. Aave V3 | 5 | supply/withdraw/roundTrip/drawdown/payloadDigest | Complete lending protocol integration |
| 3. Uniswap V3 | 3 | swap/selectorAllowlist/slippage | DEX integration + extension security |
| 4. Compound V3 | 2 | supply/roundTrip | Second lending protocol |
| 5. Multi-protocol | 2 | Aave+Uniswap split/Merkle proof verification | Multi-protocol strategy feasibility |
| 6. Full lifecycle | 1 | deploy→deposit→supply→withdraw→redeem | End-to-end user experience |
| 7. Security boundaries | 3 | unauthorized protocol/selector block/codehash stability | Defense-in-depth verification |
| 8. Token edge | 1 | USDT non-standard approve | Non-standard token compatibility |
| **Total** | **20** | | **89 passed (incl. 69 unit tests), 0 failed, 1 skipped** |
