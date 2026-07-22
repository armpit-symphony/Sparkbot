#! /usr/bin/env bash

set -e
set -x

cd backend
uv run python -c "import app.main; import json; print(json.dumps(app.main.app.openapi()))" > ../openapi.json
cd ..
mv openapi.json frontend/
# Keep this command generation-only. Handwritten frontend lint is a separate
# pre-commit concern and must not be invoked as an SDK-generation side effect.
bun run --filter frontend generate-client
