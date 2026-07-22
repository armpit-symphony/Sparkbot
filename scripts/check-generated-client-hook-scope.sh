#! /usr/bin/env bash

set -e

generator_script="scripts/generate-client.sh"
precommit_config=".pre-commit-config.yaml"

if grep -Eq 'bun run( --filter frontend)? lint' "$generator_script"; then
  echo "generated-client generation must not invoke whole-frontend lint" >&2
  exit 1
fi

grep -Fq 'bun run --filter frontend generate-client' "$generator_script"
grep -Fq 'id: generate-frontend-sdk' "$precommit_config"
grep -Fq 'entry: bash ./scripts/generate-client.sh' "$precommit_config"
grep -Fq 'entry: npm run lint' "$precommit_config"
grep -Fq 'exclude: ^frontend/src/client/' "$precommit_config"
# End of generated-client scope regression guard.
