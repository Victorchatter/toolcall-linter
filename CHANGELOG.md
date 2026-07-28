# Changelog

## 0.2.0

### Added
- `--format sarif` output for CI integration.
  - SARIF includes `runs[0].results` with `ruleId`, `message.text`, and
    `locations[0].physicalLocation` mapped to the transcript file and line number.
- GitHub Actions example in README showing SARIF upload to fail a PR on violations.
- `selfcheck.py` validates SARIF output against the SARIF 2.1.0 JSON schema.

## 0.1.0

### Added
- Initial release: local, offline linter that validates agent transcript tool
  calls against declared JSON Schemas.
