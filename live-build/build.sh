#!/bin/sh
# Build the Sysible Server ISO (headless, no GUI). Run on a Debian host, or in a
# debian:bookworm container, with network access:  sudo ./build.sh
#
# Everything a server operator needs is baked in on first boot:
#   * Debian-native tools come from config/package-lists/sysible-server.list.chroot
#   * The non-Debian vendor tools (Docker CE, kubectl, Helm, OpenTofu, k9s, SOPS)
#     are installed by the 8000 chroot hook, which drives apt / fetches official
#     release binaries directly — reliable inside the build chroot.
#
# There is intentionally NO desktop, no Calamares GUI installer and no branding
# theme here — a server image boots to a console.
set -e
cd "$(dirname "$0")"
if [ "$(id -u)" = 0 ]; then SUDO=; else SUDO="sudo"; fi
CODENAME="${SYSIBLE_CODENAME:-bookworm}"; export SYSIBLE_CODENAME="$CODENAME"
ARCH="${SYSIBLE_ARCH:-amd64}"; export SYSIBLE_ARCH="$ARCH"
echo "Building Sysible Server for architecture: $ARCH"

# --- host tooling + trust store -------------------------------------------
$SUDO apt-get update -qq || true
$SUDO apt-get install -y --no-install-recommends \
    live-build ca-certificates curl gnupg sudo xorriso || true
$SUDO update-ca-certificates || true
# If an operator dropped an intercepting-proxy CA into config/extra-ca/, trust it
# on the host AND inside the chroot so the vendor hook's HTTPS verifies.
if ls config/extra-ca/*.crt >/dev/null 2>&1; then
    $SUDO cp config/extra-ca/*.crt /usr/local/share/ca-certificates/ || true
    $SUDO update-ca-certificates || true
    mkdir -p config/includes.chroot/usr/local/share/ca-certificates
    cp config/extra-ca/*.crt config/includes.chroot/usr/local/share/ca-certificates/ || true
fi

# --- make the TARGET bootloader installable for a future installer ---------
# Keep the correct grub flavour in the live filesystem (and thus the offline
# pool) so an install-to-disk step can set up the target bootloader offline.
# Arch-selected (grub-efi-amd64 has no arm64 candidate and vice-versa).
if [ "$ARCH" = "arm64" ]; then
    printf '%s\n' grub-efi-arm64 grub-efi-arm64-bin grub-common \
        > config/package-lists/sysible-grub.list.chroot
else
    printf '%s\n' grub-efi-amd64 grub-efi-amd64-bin grub-pc-bin grub-common \
        > config/package-lists/sysible-grub.list.chroot
fi
echo "Target bootloader packages: $(tr '\n' ' ' < config/package-lists/sysible-grub.list.chroot)"

# --- assemble -------------------------------------------------------------
lb clean --purge || true
lb config
$SUDO lb build

echo "== done =="
ls -lh ./*.iso 2>/dev/null || echo "no ISO produced (check the log above)"
