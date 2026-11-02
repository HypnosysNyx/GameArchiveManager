#!/usr/bin/env bash
# Run the shared source tree; never install packages or download tools.
set -euo pipefail
case "${1:---gui}" in
  --gui|gui) module=gui.app ;;
  --cli|cli) module=main ;;
  --help|-h) printf 'Usage: bash scripts/linux_run.sh [--gui|--cli]\nSet PYTHON to select a Python 3.10+ interpreter.\n'; exit 0 ;;
  *) printf 'Usage: bash scripts/linux_run.sh [--gui|--cli]\n' >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  printf 'Only one GUI/CLI option is supported.\n' >&2
  exit 2
fi
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$project_root"
exec "${PYTHON:-python3}" -B -m "$module"
