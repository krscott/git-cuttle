#!/usr/bin/env bash
set -euo pipefail
shopt -s globstar

isort .
black .

if command -v nix >/dev/null; then
    set -x
    nix fmt ./**/*.nix
fi
