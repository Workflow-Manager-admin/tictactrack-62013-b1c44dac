#!/bin/bash
cd /home/kavia/workspace/code-generation/tictactrack-62013-b1c44dac/tic_tac_toe_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

