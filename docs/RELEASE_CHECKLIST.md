# Release Checklist

1. Update version in `neural_blitz/constants.py` and `pyproject.toml`
2. Update `CHANGELOG.md`
3. Run quality gates:
   ```bash
   make lint
   make test
   make coverage
   docker compose config
   make docker-build
   ```
4. Commit and push to `main`
5. Tag release: `git tag vX.Y.Z && git push origin vX.Y.Z`
6. Verify GitHub Release workflow artifacts (wheel + sdist)
7. Publish to PyPI when `PYPI_API_TOKEN` secret is configured
8. Update Docker image tags if distributing images
