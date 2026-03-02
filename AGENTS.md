# Agent Guide for git-cuttle

This document is to provide agents information to avoid common mistakes.

## Quick Reference

| Action | Command |
|--------|---------|
| Type check | `python -m pyright` |
| Type check | `python -m mypy .` |
| Run tests | `python -m pytest` |
| Format code | `./format.sh` |

## Environment & Dependencies

### Adding Dependencies

1. Add to `pyproject.toml` (`dependencies` or `optional-dependencies.dev`)
2. Add corresponding Nix package to `default.nix`
3. Run `pip install -e '.[dev]'`

Always use `pip install -e '.[dev]'`, never `pip install <package>` directly.

### Nix Environment

**missing .venv**
  - If .venv is not present, but nix exists on the system, do not create the
    virtual environment yourself. Ask the user to restart the agent from
    within a new `nix develop` environment.

**Tools can't find packages installed in venv:**
  - Running tools directly (e.g., `pytest`, `mypy`, `pyright`) uses Nix environment versions, which can't see venv packages
  - **Solution: Always use `python -m <tool>`** - this uses the venv's python and sees all venv packages
  - This is especially important after adding new dependencies
  - Examples: `python -m pytest`, `python -m mypy .`, `python -m pyright`

**mypy and type stubs:**
  - For packages without built-in type hints, add stub packages to dev dependencies
  - Example: `tqdm` requires `types-tqdm` in `[project.optional-dependencies.dev]`
  - If stub packages aren't available, add mypy override in `pyproject.toml`:
    ```toml
    [[tool.mypy.overrides]]
    module = "package_name"
    ignore_missing_imports = true
    ```

## Build, Test, and Lint

### Type Checking

Both mypy and pyright must pass. However, for non-trival pyright issues, it may
be better to set the error to be ignored in the config.

### Testing
* Use pytest fixtures for setup/teardown
* Minimize use of mocks

## Code Style

### Type Hints
Use modern Python 3.10+ syntax:

```python
# BAD
def log_messages(messages: List[Optional[str]]):
    ...

# GOOD
def log_messages(messages: list[str | None]) -> None:
    ...
```

### Imports
Imports go at the top of the file. Don't include within functions unless absolutely necessary.

### Error Handling
* Prefer returning values over throwing exceptions.
* Prefer general Exception classes over specific

### File System
Use `pathlib.Path` instead of `os.path`.

### Data-Oriented Design
* Follow data-oriented design principles to keep code simple and maintainable.
* Prefer composition over inheritance
* Make data easy to inspect, test, and serialize

## Documentation

### DESIGN.md
This file serves as a blueprint for the application's architecture and design. If you make significant changes to...

*   The architecture (e.g., adding modules, changing entry points)
*   The interface (e.g., CLI arguments, environment variables)
*   The core functionality
*   The data flow

...you **must** update `DESIGN.md` to reflect these changes. An AI agent should be able to read `DESIGN.md` and reproduce the current state of the application.
