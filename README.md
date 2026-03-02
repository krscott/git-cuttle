# git-cuttle

My rather opinionated Python project template.

To start a project with this template, run:
```
./init-template.sh new_project_name
```

## Documentation Structure

This repository contains several documentation files for different audiences:

- **README.md** - User-facing project documentation for developers using or deploying this project
- [**DESIGN.md**](DESIGN.md) - Normative behavior and command contracts for the CLI
- [**TROUBLESHOOTING.md**](TROUBLESHOOTING.md) - Operational recovery for rollback and git-state issues
- [**AGENTS.md**](AGENTS.md) - Comprehensive development guidelines for AI agents,
  including code style, conventions, and workflows
  (Note: CLAUDE.md is symlinked to AGENTS.md in nix dev shell)

## Development

Update dependencies
```
nix flake update
```

Start nix dev shell
```
nix develop
```

NOTE: If you rename scripts in pyproject.toml, you may need to delete and recreate .venv
