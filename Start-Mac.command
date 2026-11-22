#!/bin/bash
set -u
cd -- "$(dirname -- "$0")" || exit 1

if [ -f ./Hyperpass-Research-Web ]; then
    if [ ! -x ./Hyperpass-Research-Web ]; then
        chmod u+x ./Hyperpass-Research-Web || exit 1
    fi
    ./Hyperpass-Research-Web "$@"
    result=$?
    printf '\nHyperpass Research Web stopped. You can close this window.\n'
    exit "$result"
fi

if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
    python3 ./app.py "$@"
    result=$?
    printf '\nHyperpass Research Web stopped. You can close this window.\n'
    exit "$result"
fi

printf '\nPython 3.11 or newer is required for this source package.\n'
printf 'Install the macOS Python package from https://www.python.org/downloads/macos/\n'
printf 'Then open Start-Mac.command again. No pip, npm, or Codex setup is required.\n\n'
read -r -p 'Press Return to close this window. ' _answer
exit 1
