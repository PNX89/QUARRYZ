#!/usr/bin/env bash
# Fetch the engine binaries this repository measures against, and verify what can be verified.
#
# Usage:  scripts/fetch_tools.sh          fetch into bin/, skipping anything already correct
#         scripts/fetch_tools.sh --check  verify what is in bin/ and download nothing
#
# WHAT IS FETCHED AND WHY IT IS NOT INSTALLED. ClickHouse ships as a single self-contained
# binary that runs `clickhouse local` with no server, no daemon and no root, so this repository
# downloads one into an ignored directory rather than asking a reader to install anything. It is
# 167 MB, which is exactly why bin/ is in .gitignore before this script exists: a sibling
# repository put 121.7 MiB of Terraform provider binaries into its git history by writing the
# download first and the ignore rule afterwards.
#
# THE CHECKSUM STORY IS UNEVEN AND THIS SCRIPT SAYS SO RATHER THAN IMPLYING OTHERWISE.
#
# ClickHouse publishes SHA512 files for twelve Linux packaging assets and NO checksum at all for
# the four bare binaries, macOS included. Across all 52 assets of a release there is no SHA256
# anywhere. Measured by enumerating them, not assumed.
#
# So there are two different levels of assurance here and they are labelled:
#
#   linux-amd64   the static .tgz, verified against the VENDOR'S OWN .sha512. A real attestation.
#   macos-aarch64 a bare binary with no vendor checksum. The SHA256 below is one THIS REPOSITORY
#                 measured on first download. That is trust-on-first-use: it proves the file has
#                 not changed since somebody here looked at it, and it proves nothing about what
#                 ClickHouse intended to publish. Calling it a checksum without that sentence
#                 would be the kind of claim this repository exists to argue against.
#
# And the moving pointer at builds.clickhouse.com/master is not used. It served a different
# build from the versioned release on the day this was written, 165,952,523 bytes against
# 167,768,378, which is the whole reason a version is pinned rather than "latest".
set -euo pipefail

VERSION="26.7.5.10"
RELEASE="v${VERSION}-stable"
BASE="https://github.com/ClickHouse/ClickHouse/releases/download/${RELEASE}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/bin"

# Measured on 28-8-2026. See the paragraph above about what this one does and does not prove.
MACOS_SHA256="1d44a9ccab535b1573afabdab41a0fe85441a88c93024c6f231698933dddba5b"

say() { printf '%s\n' "$*"; }
die() { printf 'FAIL  %s\n' "$*" >&2; exit 1; }

platform() {
  case "$(uname -s)/$(uname -m)" in
    Darwin/arm64) echo "macos-aarch64" ;;
    Linux/x86_64) echo "linux-amd64" ;;
    *) die "no ClickHouse binary is fetched for $(uname -s)/$(uname -m). The measurements in
       docs/evidence were produced on macos-aarch64 and reproduced in CI on linux-amd64." ;;
  esac
}

fetch_macos() {
  local target="$BIN/clickhouse"
  if [ -f "$target" ] && verify_macos "$target" 2>/dev/null; then
    say "ok    clickhouse ${VERSION} already present and matches the recorded hash"
    return 0
  fi
  [ "${1:-}" = "--check" ] && die "bin/clickhouse is missing or does not match. Run without --check."
  say "==> downloading clickhouse ${VERSION} for macos-aarch64 (about 167 MB)"
  curl -fsSL --retry 3 -o "$target.part" "$BASE/clickhouse-macos-aarch64"
  mv "$target.part" "$target"
  chmod +x "$target"
  verify_macos "$target" || die "the download does not match the recorded SHA256"
}

verify_macos() {
  local got
  got="$(shasum -a 256 "$1" | awk '{print $1}')"
  [ "$got" = "$MACOS_SHA256" ] || {
    printf 'recorded %s\ngot      %s\n' "$MACOS_SHA256" "$got" >&2
    return 1
  }
  say "ok    sha256 matches the hash recorded here (trust on first use, not a vendor checksum)"
}

fetch_linux() {
  local target="$BIN/clickhouse"
  local name="clickhouse-common-static-${VERSION}-amd64.tgz"
  if [ -f "$target" ] && "$target" local --version 2>/dev/null | grep -q "$VERSION"; then
    say "ok    clickhouse ${VERSION} already present"
    return 0
  fi
  [ "${1:-}" = "--check" ] && die "bin/clickhouse is missing. Run without --check."
  say "==> downloading ${name} and its vendor sha512"
  # DOWNLOADED UNDER THE VENDOR'S OWN FILENAME, so their checksum file can be used exactly as
  # published. The first version of this saved the tarball as clickhouse.tgz and rewrote the
  # filename inside the .sha512 with sed, which put ONE space where the format needs two and
  # produced "no properly formatted SHA checksum lines found". Rewriting a vendor's checksum
  # file to make it match your naming is a bad habit even when the sed is right: the file is
  # the attestation, and editing it is editing the thing being trusted.
  curl -fsSL --retry 3 -o "$BIN/$name" "$BASE/$name"
  curl -fsSL --retry 3 -o "$BIN/${name}.sha512" "$BASE/${name}.sha512"
  ( cd "$BIN" && shasum -a 512 -c "${name}.sha512" ) \
    || die "the vendor sha512 does not match the download"
  say "ok    vendor sha512 verified, unmodified, against the name they published it under"
  tar -xzf "$BIN/$name" -C "$BIN" --strip-components=3 \
    "clickhouse-common-static-${VERSION}/usr/bin/clickhouse"
  chmod +x "$target"
  rm -f "$BIN/$name" "$BIN/${name}.sha512"
}

mkdir -p "$BIN"
case "$(platform)" in
  macos-aarch64) fetch_macos "${1:-}" ;;
  linux-amd64) fetch_linux "${1:-}" ;;
esac

# The binary is only useful if it runs, and a downloaded file that will not execute is a
# different failure from one that does not match. Both are reported separately.
got="$("$BIN/clickhouse" local --query "SELECT version()" 2>/dev/null || true)"
[ "$got" = "$VERSION" ] || die "bin/clickhouse reports '${got:-nothing}', expected ${VERSION}"
say "ok    clickhouse local runs and reports ${VERSION} with no server"
