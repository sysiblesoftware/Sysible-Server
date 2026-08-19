#!/bin/sh
# Mirror the Debian base into YOUR OWN apt repo (repo.sysible.com/debian) with
# aptly, so the Sysible distros pull their base packages from Sysible instead of
# deb.debian.org. Companion to publish-repo.sh (which publishes the Sysible-built
# .debs); this one mirrors the Debian upstream.
#
# FILTERED by default: only the packages the distros actually install, plus their
# dependencies and the debootstrap essential/required/important set — a few GB,
# not the ~hundreds of GB of a full Debian mirror. Pass a package-list file (one
# name per line; '#' comments ok) to define "what we ship"; the distro build
# emits exactly this at live-build/config/package-lists/*.list.chroot, and the
# metapackage Depends expand the rest.
#
# Usage:
#   ./mirror-debian.sh [PKG_LIST_FILE ...]
#
# Environment:
#   SYSIBLE_CODENAME        Debian suite            (default bookworm)
#   SYSIBLE_ARCHES          comma arch list         (default amd64,arm64)
#   SYSIBLE_GPG_KEY         signing key id/email    (default maintainers@sysible.com)
#   SYSIBLE_APTLY_ENDPOINT  aptly publish endpoint  (default "" = local FS; R2/S3: "s3:sysible:")
#   SYSIBLE_MIRROR_PREFIX   publish prefix under the endpoint (default "debian")
#   SYSIBLE_FULL_MIRROR=1   mirror EVERYTHING (no filter) — hundreds of GB
#   GNUPGHOME               must hold the private signing key
#
# Run this on your repo host (or CI with R2 creds). It is the slow, bandwidth-
# heavy step; live-build only *points at* the result (see auto/config's
# SYSIBLE_BASE_MIRROR switch). Re-run to refresh (e.g. after a Debian point
# release or security update); publishing is idempotent.
set -e

CODENAME="${SYSIBLE_CODENAME:-bookworm}"
ARCHES="${SYSIBLE_ARCHES:-amd64,arm64}"
GPGKEY="${SYSIBLE_GPG_KEY:-maintainers@sysible.com}"
ENDPOINT="${SYSIBLE_APTLY_ENDPOINT:-}"
PREFIX="${SYSIBLE_MIRROR_PREFIX:-debian}"
COMPONENTS="main contrib non-free non-free-firmware"
PUB="${ENDPOINT}${PREFIX}"     # e.g. "s3:sysible:debian" or just "debian" (local FS)

command -v aptly >/dev/null 2>&1 || { echo "aptly not installed (apt-get install aptly)" >&2; exit 1; }

# A signing key is required — the published base repo is signed by Sysible, and
# the distros trust it via sysible-archive-keyring. Refuse rather than sign with
# a key clients don't have (same rule as publish-repo.sh).
if ! gpg --list-secret-keys "$GPGKEY" >/dev/null 2>&1; then
    echo "ERROR: no signing key for '$GPGKEY' in GNUPGHOME=${GNUPGHOME:-$HOME/.gnupg}." >&2
    echo "Import the Sysible archive private key first (the same key publish-repo.sh uses)." >&2
    exit 1
fi

# --- build the aptly -filter from the shipped package lists -----------------
# Always include the base system (essential/required/important) so debootstrap
# and a minimal boot work; then add every package the distros install by name.
FILTER=""
if [ "${SYSIBLE_FULL_MIRROR:-0}" != "1" ]; then
    FILTER="Priority (required) | Priority (important) | Priority (standard)"
    for f in "$@"; do
        [ -f "$f" ] || { echo "package list not found: $f" >&2; exit 1; }
        while IFS= read -r pkg; do
            case "$pkg" in ''|\#*) continue ;; esac
            pkg=$(printf '%s' "$pkg" | tr -d ' \t')
            [ -n "$pkg" ] && FILTER="$FILTER | \$Source ($pkg) | $pkg"
        done < "$f"
    done
    echo "== filtered mirror ($CODENAME, $ARCHES): $(printf '%s' "$FILTER" | tr '|' '\n' | grep -c .) filter terms =="
else
    echo "== FULL mirror ($CODENAME, $ARCHES) — this is hundreds of GB =="
fi

# --- define/update the two mirrors (archive + security) ---------------------
mirror_one() {
    _name="$1"; _url="$2"; _suite="$3"
    if ! aptly mirror show "$_name" >/dev/null 2>&1; then
        if [ -n "$FILTER" ]; then
            aptly mirror create -architectures="$ARCHES" -filter="$FILTER" -filter-with-deps \
                "$_name" "$_url" "$_suite" $COMPONENTS
        else
            aptly mirror create -architectures="$ARCHES" "$_name" "$_url" "$_suite" $COMPONENTS
        fi
    fi
    aptly mirror update "$_name"
}
mirror_one "debian-${CODENAME}"          "http://deb.debian.org/debian"           "$CODENAME"
mirror_one "debian-${CODENAME}-security" "http://security.debian.org/debian-security" "${CODENAME}-security"

# --- snapshot + publish under repo.sysible.com/debian -----------------------
STAMP_A="snap-${CODENAME}"
STAMP_S="snap-${CODENAME}-security"
aptly snapshot create "$STAMP_A" from mirror "debian-${CODENAME}" 2>/dev/null \
    || { aptly snapshot drop "$STAMP_A" 2>/dev/null || true; aptly snapshot create "$STAMP_A" from mirror "debian-${CODENAME}"; }
aptly snapshot create "$STAMP_S" from mirror "debian-${CODENAME}-security" 2>/dev/null \
    || { aptly snapshot drop "$STAMP_S" 2>/dev/null || true; aptly snapshot create "$STAMP_S" from mirror "debian-${CODENAME}-security"; }

# Republish fresh (drop-then-create), so a re-run fully regenerates the tree —
# matches publish-repo.sh, safe against an ephemeral/wiped publish dir.
aptly publish drop "$CODENAME" "$PUB" 2>/dev/null || true
aptly publish snapshot -component=main -distribution="$CODENAME" -gpg-key="$GPGKEY" "$STAMP_A" "$PUB"
aptly publish drop "${CODENAME}-security" "$PUB" 2>/dev/null || true
aptly publish snapshot -component=main -distribution="${CODENAME}-security" -gpg-key="$GPGKEY" "$STAMP_S" "$PUB"

echo "== done: published Debian base to ${PUB} ($CODENAME + ${CODENAME}-security) =="
echo "   Point the distros at it by building with:"
echo "     SYSIBLE_BASE_MIRROR=https://repo.sysible.com/${PREFIX} ./build.sh"
