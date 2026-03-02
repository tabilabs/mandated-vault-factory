# Contributing

Thank you for your interest in contributing to Mandated Vault Factory.

## Getting Started

```bash
git clone --recurse-submodules https://github.com/tabilabs/mandated-vault-factory.git
cd mandated-vault-factory
forge build
forge test
```

## Development Workflow

1. Fork the repository
2. Create a feature branch from `master`
3. Make your changes
4. Run the full check suite before submitting:

```bash
forge fmt --check
forge build --sizes
forge test -vvv
```

5. Open a Pull Request with a clear description of the change

## Code Style

- Follow existing Solidity conventions in `src/`
- Use `forge fmt` for formatting
- All public/external functions must have NatSpec documentation
- Error names should be descriptive (e.g., `DrawdownExceeded`, not `Error1`)

## Testing

- All new features must include tests
- Unit tests go in `test/VaultFactory.t.sol` or `test/VaultBranch.t.sol`
- Fork-based integration tests go in `test/VaultFork.t.sol`
- Run `forge coverage --report summary` to check coverage impact

## Commit Messages

Use concise, descriptive messages:

- `Fix: resolve drawdown check off-by-one`
- `Feat: add batch nonce invalidation`
- `Test: add ERC-1271 reject scenario`
- `Docs: update architecture diagram`

## Pull Request Guidelines

- Keep PRs focused — one logical change per PR
- Reference related issues if applicable
- Ensure CI passes before requesting review

## Questions?

Open a [GitHub Discussion](https://github.com/tabilabs/mandated-vault-factory/discussions) for questions.
