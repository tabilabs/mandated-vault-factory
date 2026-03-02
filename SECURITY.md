# Security Policy

## Scope

This policy covers smart contracts in the `src/` directory of this repository.

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` branch (pre-audit) | Yes |

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Please report vulnerabilities via email:

- **Email**: lancy@tabilabs.org
- **Subject prefix**: `[SECURITY] mandated-vault-factory`
- **Response SLA**: We aim to acknowledge within 48 hours and provide an initial assessment within 7 days.

### What to Include

- Description of the vulnerability
- Steps to reproduce (PoC preferred)
- Impact assessment (funds at risk, affected functions)
- Suggested fix (if any)

## Disclosure Policy

- We follow coordinated disclosure: please allow up to 90 days for a fix before public disclosure.
- Credit will be given to reporters in the fix commit and any published advisory, unless anonymity is requested.

## Known Limitations

The following are documented design trade-offs, not vulnerabilities:

- Proxy adapter `codehash` binding reflects proxy bytecode, not implementation — see README "Key Constraints"
- `execute()` does not forward ETH (`action.value` must be 0)
- Return data from failed actions is truncated to 4 KiB

## Adapter Governance Requirements

When computing/signing `allowedAdaptersRoot`, maintainers must complete these checks:

1. Verify whether each adapter is upgradeable (proxy) or immutable.
2. For upgradeable adapters, record current implementation address and upgrade admin.
3. If implementation/governance state changes, revoke affected mandates and re-sign a new root.
4. Keep emergency response runbooks for authority key rotation and nonce invalidation.
5. Prefer immutable adapters for long-lived mandates.

These controls are mandatory because Merkle binding uses `(adapter, codehash)` and cannot independently pin proxy implementations.

## Audit Status

This codebase has not yet undergone a formal third-party audit. Use at your own risk.
