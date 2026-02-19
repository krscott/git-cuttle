# Design Document

This document outlines the design, architecture, and components of the `py-start` application. It serves as a comprehensive guide for understanding and reproducing the system's functionality.

## Overview

`py-start` is a Command Line Interface (CLI) application built with Python. It serves as a foundational template for Python projects, featuring structured argument parsing, environment variable configuration, type-safe code, and logging.

## Architecture

The application follows a clean separation of concerns:

1.  **Entry Point (`__main__.py`)**: Handles CLI interaction, argument parsing, configuration loading, and application bootstrapping.
2.  **Core Logic (`lib.py`)**: Contains the business logic and domain-specific functionality, independent of the CLI interface.

## Components

### 1. CLI Entry Point
*   **File**: `py_start/__main__.py`
*   **Function**: `main()`
*   **Responsibilities**:
    *   Sets the process title using `setproctitle`.
    *   Loads environment variables from `.env` files using `python-dotenv`.
    *   Parses command-line arguments.
    *   Configures the logging system.
    *   Invokes the core business logic.

### 2. Configuration & Argument Parsing
*   **Mechanism**: `argparse` with a custom Action (`EnvAction`).
*   **Features**:
    *   Supports command-line flags (e.g., `-v`, `--verbose`).
    *   Supports environment variable fallbacks (e.g., `PYSTART_VERBOSE`).
    *   `EnvAction` class handles the logic: CLI arg > Env Var > Default value.
*   **Data Model**: `CliOpts` dataclass encapsulates all configuration options, ensuring type safety when passing settings around.

### 3. Core Logic
*   **File**: `py_start/lib.py`
*   **Responsibilities**:
    *   Implements the primary functionality (currently a greeting system).
    *   Defines domain data models (e.g., `Options`).
    *   Designed to be testable and reusable, decoupled from `argparse`.

### 4. Logging
*   **Library**: Standard Python `logging`.
*   **Configuration**: Configured in `main()` based on the verbosity flag.
*   **Behavior**:
    *   Default level: `INFO`.
    *   Verbose level: `DEBUG`.
    *   Uses a simple message format.

## Data Flow

1.  User invokes the CLI (e.g., `pystart World`).
2.  `main()` initializes and loads environment variables.
3.  `CliOpts.parse_args()` processes arguments and environment variables.
4.  A `CliOpts` object is created, containing an `app_opts` (`Options`) instance and CLI-specific flags.
5.  Logging is configured based on `CliOpts.verbose`.
6.  `greet(cli_opts.app_opts)` is called, executing the core logic.
7.  Output is printed to the console or logged.

## Reproducibility Guide

To reproduce this application, an agent should:

1.  **Setup Project Structure**: Create `py_start/` package and `tests/` directory.
2.  **Define Dependencies**: Configure `pyproject.toml` with `python-dotenv` and `setproctitle`.
3.  **Implement `EnvAction`**: Create the custom `argparse.Action` to support environment variable fallbacks.
4.  **Create Data Models**: Define `Options` and `CliOpts` dataclasses for type-safe configuration.
5.  **Implement Logic**: Write the core functionality in `lib.py`.
6.  **Wire Entry Point**: specific `main()` function to orchestrate config, logging, and execution.
7.  **Add Type Hints**: Ensure all code is strictly typed for `pyright` and `mypy` compliance.
