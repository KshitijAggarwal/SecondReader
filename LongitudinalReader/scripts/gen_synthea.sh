#!/usr/bin/env bash
# Generate a longitudinal FHIR R4 cohort with Synthea (the same simulator behind the
# Abridge patients), biased toward modules that produce lab TRENDS so the slope
# detector has real signal. Requires Java 11+ (Synthea is a Java toolchain — that's
# why it is NOT a Python dependency in pyproject.toml).
#
#   ./scripts/gen_synthea.sh [N]     # default 30 patients
#
# Output bundles land in data/synthea/*.json and are picked up automatically by the
# cohort command (`longitudinal-reader cohort`).
set -euo pipefail

N="${1:-30}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/.synthea"
DEST="$ROOT/data/synthea"

if ! command -v java >/dev/null 2>&1; then
  echo "Java not found. Install Java 11+ (e.g. 'brew install openjdk@21') and retry." >&2
  exit 1
fi

mkdir -p "$DEST"
if [ ! -d "$WORK" ]; then
  echo "Cloning Synthea into $WORK ..."
  git clone --depth 1 https://github.com/synthetichealth/synthea.git "$WORK"
fi

cd "$WORK"
echo "Generating $N patients (full longitudinal history, FHIR R4) ..."
# years_of_history 0 = keep the FULL record, not just recent years.
./run_synthea -p "$N" \
  --exporter.fhir.export true \
  --exporter.fhir.use_us_core_ig false \
  --exporter.years_of_history 0 \
  --generate.only_alive_patients true

echo "Copying patient bundles to $DEST ..."
# Skip the hospital/practitioner roster bundles; keep per-patient records.
find "$WORK/output/fhir" -maxdepth 1 -name '*.json' \
  ! -name 'hospitalInformation*' ! -name 'practitionerInformation*' \
  -exec cp {} "$DEST/" \;

echo "Done. $(ls "$DEST"/*.json | wc -l | tr -d ' ') bundles in $DEST"
echo "Run:  longitudinal-reader cohort"
