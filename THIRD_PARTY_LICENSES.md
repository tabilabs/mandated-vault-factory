# Third-Party License Notes

This repository depends on third-party libraries under `lib/`.

## Primary dependency licenses

- `lib/openzeppelin-contracts-upgradeable/**`: MIT
- `lib/forge-std/**`: MIT OR Apache-2.0

## AGPL components (test/tooling scope only)

The following transitive dependencies include AGPL-3.0 license files:

- `lib/openzeppelin-contracts-upgradeable/lib/erc4626-tests/**`
- `lib/openzeppelin-contracts-upgradeable/lib/halmos-cheatcodes/**`

### Policy

1. AGPL-licensed components are allowed **only** for testing/tooling in this repository.
2. Production artifacts must not package, copy, or redistribute AGPL-licensed source/binaries.
3. CI enforces this boundary via `scripts/check-licenses.sh`.
