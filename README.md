# Mandated Vault Factory

ERC-1167 Clone factory for deploying **ERC-XXXX Mandated Execution** vaults — risk-constrained delegated strategy execution on ERC-4626 vaults.

## Architecture

```
VaultFactory (immutable, ownerless)
  └── cloneDeterministic() ──► MandatedVaultClone (per-user instance)
                                  ├── ERC-4626 (deposit / withdraw / mint / redeem)
                                  ├── EIP-712 signed Mandate execution
                                  ├── Merkle adapter allowlist
                                  ├── Single + cumulative drawdown circuit breaker
                                  └── 2-step authority transfer with epoch invalidation
```

| Contract | Description |
|----------|-------------|
| `VaultFactory.sol` | Ownerless ERC-1167 Clone factory with CREATE2 deterministic deployment |
| `MandatedVaultClone.sol` | Clone-compatible vault implementation (orchestrator pattern) |
| `MandateLib.sol` | Mandate field validation (steps 1-5a, 10) |
| `AdapterLib.sol` | Adapter + selector Merkle verification (steps 12, 12a) |
| `DrawdownLib.sol` | Single/cumulative drawdown circuit breaker (step 16) |

## Security Model

- **Authority-signed mandates**: Off-chain EIP-712 signatures (EOA via ECDSA or smart contract via ERC-1271)
- **Per-execution drawdown cap**: `maxDrawdownBps` limits single-execution loss
- **Cumulative drawdown cap**: `maxCumulativeDrawdownBps` limits epoch-level loss with high-water mark
- **Merkle adapter allowlist**: Only authority-approved adapters can be called
- **Selector allowlist extension**: Optional per-selector granularity
- **Nonce replay protection**: Per-nonce tracking + threshold invalidation
- **Mandate revocation**: Authority can revoke specific mandate hashes
- **Epoch management**: Authority transfer bumps epoch, invalidating all prior mandates
- **VaultBusy guard**: Prevents ERC-4626 deposits/withdrawals during `execute()`
- **ReentrancyGuard**: Standard nonReentrant on `execute()`

## Key Constraints

- `isVault()` only covers factory-deployed instances; externally deployed clones are not tracked
- Adapter proxy contracts can bypass the Merkle allowlist if they delegatecall to arbitrary targets — adapters must be audited
- **Proxy adapter codehash binding**: The adapter allowlist binds `(address, codehash)`. For upgradeable proxy adapters, `codehash` reflects the proxy bytecode (stable), not the implementation. If the implementation is upgraded after the authority signs a mandate, the Merkle proof remains valid despite the logic change. Authorities should only allowlist immutable adapters or adapters with trusted upgrade governance
- Action failure return data is capped at 4 KiB to prevent gas griefing via oversized `returndata`
- `execute()` value forwarding is disabled (`action.value` must be 0) to prevent ETH drain attacks
- Maximum 32 actions, 16 extensions, 64-deep Merkle proofs per execution
- Library-level errors (`MandateLib.TooManyActions`, `AdapterLib.SelectorNotAllowed`, etc.) are part of `MandatedVaultClone`'s ABI and should be decoded alongside `IERCXXXXMandatedVault` errors

## Quick Start

```bash
git clone --recurse-submodules https://github.com/tabilabs/mandated-vault-factory.git
cd mandated-vault-factory
forge build
forge test
```

### Build

```bash
forge build
```

### Test

```bash
forge test
```

### Coverage

```bash
forge coverage --report summary
# or, with ir-minimum for faster runs:
forge coverage --report summary --ir-minimum
```

### Contract Sizes

```bash
forge build --sizes
```

## Test Coverage (69 tests)

- **Factory**: creation, registration, events, address prediction, duplicate salt, zero-address checks, multi-creator isolation
- **Implementation**: locked against re-initialization
- **ERC-4626**: deposit/withdraw/mint/redeem
- **Mandate execution**: basic, multi-action, multi-execution, open mandate
- **Authority**: 2-step transfer, epoch mismatch, ERC-1271 valid/reject/short-return
- **Nonce**: invalidation, threshold, replay protection, threshold-only-increases
- **Revocation**: mandate hash revocation
- **Drawdown**: single exceeded, cumulative exceeded (3-execution scenario), invalid bps, zero-bps full reject, zero-assets skip
- **Extensions**: selector allowlist valid/wrong, supportsExtension, hash mismatch, encoding errors, required unsupported, non-canonical ordering, too many, too large, selector proofs length mismatch
- **Adapter**: wrong adapter, proofs mismatch, proof too deep, selector proof too deep, invalid action data, value non-zero, too many actions
- **Security**: sweepNative, VaultBusy reentrancy (inner reason verification), deadline expiry/exact boundary, unbounded open mandate, payload digest mismatch, returndata truncation (4 KiB cap), authority cache (mid-execution hijack)

## License

CC0-1.0
