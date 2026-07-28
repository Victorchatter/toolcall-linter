# Changelog

## 0.4.0

### Added
- Reusable GitHub Action (`action.yml`) for linting transcripts in CI.
  - Inputs: `transcript`, `tools`, `format`, `fail-on-blockers`.
  - Outputs: `findings-count`, `report-path`.
- `.pre-commit-hooks.yaml` so the linter can be used as a pre-commit hook.
- `.github/workflows/selfcheck.yml` exercises the action on example data.
- README sections documenting the GitHub Action and pre-commit hook.

## 0.3.0

### Added
- `toolcall-linter infer` subcommand that builds a JSON Schema from a transcript.
  - Infers tool names, argument properties, required keys, types, and string
    enums for small value sets.
  - Writes MCP-style `tools.json` output and validates it against the source
    tape by default.

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
