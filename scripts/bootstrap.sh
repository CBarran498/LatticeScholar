#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check --upgrade pip
fi

"${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check "${PROJECT_DIR}"
exec "${VENV_DIR}/bin/latticescholar" "$@"

