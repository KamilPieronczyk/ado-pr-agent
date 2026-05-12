#!/usr/bin/env bash
# Make this script executable with: chmod +x infra/package.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT="${SCRIPT_DIR}/../app.zip"
cd "$SCRIPT_DIR"
rm -f "$OUTPUT"
zip -j "$OUTPUT" mainTemplate.json createUiDefinition.json
echo "Created: $OUTPUT"
echo "Contents:"
unzip -l "$OUTPUT"
