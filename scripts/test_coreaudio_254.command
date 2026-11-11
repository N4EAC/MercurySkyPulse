#!/bin/zsh
set -euo pipefail
PROJECT_ROOT="${0:A:h:h}"
export MERCURY_EXECUTABLE="/private/tmp/mercury-coreaudio-254-first-fix/mercury"
exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/tools/coreaudio_254_test.py" "$@"
