#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${PROJECT_DIR}/scripts/bootstrap.sh"

