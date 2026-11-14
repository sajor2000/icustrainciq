#!/bin/bash
# Write fuzzball/ready/: every workflow of the final cohort, fully rendered (no @TOKEN@ left), ready for
#   fuzzball workflow validate fuzzball/ready/<file> && fuzzball workflow start fuzzball/ready/<file> --name <name>
# It only writes text and downloads one public tarball (to hash it): it starts nothing and talks to no cluster.
#   scripts/make_ready.sh            # code = origin/main
#   scripts/make_ready.sh <40-hex>   # code = that commit (it must be on GitHub)
# The commit decides what t7-code publishes to the cluster, so run this again after every merge to main,
# commit fuzzball/ready/, and run t7-code again.
set -euo pipefail
cd "$(dirname "$0")/.."
REF="${1:-$(git rev-parse origin/main)}"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "commit must be a full 40-hex sha, got: $REF"; exit 1; }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
curl -fsSL "https://codeload.github.com/sajor2000/icustrainciq/tar.gz/$REF" -o "$TMP/code.tar.gz"
SHA=$(shasum -a 256 "$TMP/code.tar.gz" | cut -d' ' -f1)
tar -tzf "$TMP/code.tar.gz" | grep -q '/backend/requirements/t7-model.txt$' || { echo "commit $REF has no backend/"; exit 1; }
OUT=fuzzball/ready; mkdir -p "$OUT"; rm -f "$OUT"/*.fz
r() { python3 scripts/render_fz.py "fuzzball/$1.fz" "${@:3}" -o "$OUT/$2.fz"; }
r t7-code     t7-code          --code-ref "$REF" --code-sha256 "$SHA"
r t7-fit      t7-fit           --cohort
r t7-ward     t7-ward          --cohort
r t7-twin     t7-twin          --cohort
r t7-forecast t7-forecast-unit --cohort --scope unit
r t7-forecast t7-forecast-room12 --cohort --scope room --room 12
if grep -l '@[A-Z0-9_][A-Z0-9_]*@' "$OUT"/*.fz; then echo "a token is left in the files above"; exit 1; fi
printf '%s\n' "$REF" > "$OUT/CODE_REF"; printf '%s\n' "$SHA" > "$OUT/CODE_SHA256"
echo "wrote $OUT for commit $REF (tarball sha256 $SHA)"; ls "$OUT"
