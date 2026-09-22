#!/usr/bin/env bash
# Stage a redistributable KotorPhasor package from artifacts that already work.
#
#   ./scripts/package_release.sh [build-dir]
#
# Requires build/kphasor.dll and build/binkw32.dll. Optionally includes
# libkphasor.so when present. Emits dist/kotorphasor-<version>.zip and prints
# its path and sha256. Does not ship game assets or corpus data.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${1:-$ROOT/build}"
VERSION="${KP_PACKAGE_VERSION:-0.1.0}"
NAME="kotorphasor-${VERSION}"
STAGE="$ROOT/dist/$NAME"
ZIP="$ROOT/dist/${NAME}.zip"

die() { echo "package_release: $*" >&2; exit 1; }

[[ -f "$BUILD/kphasor.dll" ]] || die "missing $BUILD/kphasor.dll — build first"
[[ -f "$BUILD/binkw32.dll" ]] || die "missing $BUILD/binkw32.dll — build first"

rm -rf "$STAGE"
mkdir -p "$STAGE"/{bin,data,docs/user,scripts,examples}

install -m644 "$BUILD/kphasor.dll" "$STAGE/bin/kphasor.dll"
install -m644 "$BUILD/binkw32.dll" "$STAGE/bin/binkw32.dll"
# Flat copies at package root so install_to_game.sh can treat STAGE as build-dir.
install -m644 "$BUILD/kphasor.dll" "$STAGE/kphasor.dll"
install -m644 "$BUILD/binkw32.dll" "$STAGE/binkw32.dll"
if [[ -f "$BUILD/libkphasor.so" ]]; then
  install -m644 "$BUILD/libkphasor.so" "$STAGE/bin/libkphasor.so"
  install -m644 "$BUILD/libkphasor.so" "$STAGE/libkphasor.so"
fi

install -m755 "$ROOT/scripts/install_to_game.sh" "$STAGE/install_to_game.sh"
install -m755 "$ROOT/scripts/install_to_game.sh" "$STAGE/scripts/install_to_game.sh"

cp -a "$ROOT/data/addresses" "$STAGE/data/addresses"
if [[ -d "$ROOT/data/profiles" ]]; then
  cp -a "$ROOT/data/profiles" "$STAGE/data/profiles"
fi
# Curated public demos only (cursed pack). Retired showcase fixtures stay in-repo
# for regression but are not advertising content in the release zip.
mkdir -p "$STAGE/examples"
cp -a "$ROOT/scripts/examples/cursed" "$STAGE/examples/cursed"

install -m644 "$ROOT/README.md" "$STAGE/README.md"
install -m644 "$ROOT/CONTRIBUTING.md" "$STAGE/CONTRIBUTING.md"
install -m644 "$ROOT/docs/user/install.md" "$STAGE/docs/user/install.md"
[[ -f "$ROOT/LICENSE" ]] && install -m644 "$ROOT/LICENSE" "$STAGE/LICENSE"
[[ -f "$ROOT/ATTRIBUTION.md" ]] && install -m644 "$ROOT/ATTRIBUTION.md" "$STAGE/ATTRIBUTION.md"
[[ -f "$ROOT/CHANGELOG.md" ]] && install -m644 "$ROOT/CHANGELOG.md" "$STAGE/CHANGELOG.md"

cat > "$STAGE/INSTALL.txt" <<EOF
KotorPhasor ${VERSION}

Windows (K1/K2 GOG or Steam PE):
  ./install_to_game.sh install /path/to/game/dir .

That copies kphasor.dll + proxy binkw32.dll and address tables into the game
folder. Bring your own legal game install. This package ships no game content.

See docs/user/install.md and CONTRIBUTING.md (Supported builds).
EOF

rm -f "$ZIP"
mkdir -p "$ROOT/dist"
(
  cd "$ROOT/dist"
  zip -rq "${NAME}.zip" "$NAME"
)
ZIP="$ROOT/dist/${NAME}.zip"

SUM="$(sha256sum "$ZIP" | awk '{print $1}')"
echo "$ZIP"
echo "sha256 $SUM"

python3 "$ROOT/tools/check_release_zip.py" "$ZIP"
