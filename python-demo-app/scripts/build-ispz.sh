#!/usr/bin/env bash
# Builds out/<plugin_id>-<version>.ispz from package/<plugin_id>/: writes checksums.sha256 and zips
# the folder. Nothing is compiled; the IS installs the requirements in its own environment.
set -euo pipefail
cd "$(dirname "$0")/.."
PLUGIN_DIR=$(find package -mindepth 1 -maxdepth 1 -type d | head -1)
PLUGIN_ID=$(basename "$PLUGIN_DIR")
VERSION=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$PLUGIN_DIR/plugin-manifest.json")

find "$PLUGIN_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +
(cd "$PLUGIN_DIR" && find . -type f ! -name checksums.sha256 | sed 's|^\./||' | LC_ALL=C sort \
  | xargs sha256sum > checksums.sha256)

mkdir -p out
rm -f "out/$PLUGIN_ID-$VERSION.ispz"
(cd package && zip -qr "../out/$PLUGIN_ID-$VERSION.ispz" "$PLUGIN_ID")
echo "out/$PLUGIN_ID-$VERSION.ispz"
