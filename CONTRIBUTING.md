# Contributing to Neural Blitz NG

Thank you for helping improve Neural Blitz NG. This project welcomes contributions that make authorized network monitoring safer, clearer, and more reliable.

## Getting started

```bash
git clone https://github.com/MiMindMendinc/neural-blitz-ng.git
cd neural-blitz-ng
make dev
make test
```

## Development workflow

1. Open an issue or comment on an existing one before large changes.
2. Create a branch from `main`.
3. Keep changes focused and well-tested.
4. Run `make lint`, `make test`, and `make coverage` before submitting.
5. Open a pull request using the template.

## Code standards

- Python 3.10+ with type hints where reasonable
- `ruff format` and `ruff check` must pass
- No features that enable unauthorized scanning, amplification, or abuse
- Document user-facing behavior in `docs/` and `README.md`

## Safety policy for contributors

Do not add:

- Target discovery or port scanning modes
- Spoofing, reflection, or amplification behavior
- Stealth, evasion, or credential-related functionality

All network testing features must include safe defaults and explicit authorized-use gates.

## Tests

- Mark integration tests with `@pytest.mark.integration`
- Prefer deterministic localhost tests
- Aim for meaningful coverage, not assertion theater

## Questions

Open a GitHub issue or contact Michigan MindMend Inc. via the repository.
