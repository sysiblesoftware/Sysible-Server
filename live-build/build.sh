#!/bin/sh
# Build the Sysible Server ISO (headless, text-mode Debian Installer). Run on a
# Debian host, or in a debian:bookworm container, with network access:  sudo ./build.sh
#
# Everything is baked in — nothing to install after first boot:
#   * Debian-native tools come from the package list (below).
#   * The Sysible packages are built here and included directly.
#   * The non-Debian vendor tools (Docker, Kubernetes, cloud CLIs,
#     k9s/sops/eza, PowerShell, Ollama) are installed by a chroot hook that
#     controls apt directly — reliable, unlike live-build's archive-key handling.
set -e
cd "$(dirname "$0")"
ROOT=$(cd .. && pwd)
if [ "$(id -u)" = 0 ]; then SUDO=; else SUDO="sudo"; fi
CODENAME="${SYSIBLE_CODENAME:-bookworm}"; export SYSIBLE_CODENAME="$CODENAME"
ARCH="${SYSIBLE_ARCH:-amd64}"; export SYSIBLE_ARCH="$ARCH"
echo "Building for architecture: $ARCH"

# --- host tooling + trust store -------------------------------------------
$SUDO apt-get update -qq || true
# cpio/wget/rsync/dosfstools/mtools are needed by live-build's
# installer_debian-installer stage (we ship the text-mode Debian Installer via
# --debian-installer live). The Workstation image used --debian-installer none
# (Calamares), so that stage never ran and these weren't required — hence
# "cpio: not found" once the server switched installers.
$SUDO apt-get install -y --no-install-recommends \
    live-build ca-certificates curl gnupg sudo openssl xorriso \
    cpio wget rsync dosfstools mtools || true
$SUDO update-ca-certificates || true
if ls config/extra-ca/*.crt >/dev/null 2>&1; then
    $SUDO cp config/extra-ca/*.crt /usr/local/share/ca-certificates/ || true
    $SUDO update-ca-certificates || true
    # Also trust it INSIDE the chroot so the vendor hook's HTTPS verifies on an
    # inspected network (includes.chroot is copied in before hooks run).
    mkdir -p config/includes.chroot/usr/local/share/ca-certificates
    cp config/extra-ca/*.crt config/includes.chroot/usr/local/share/ca-certificates/ || true
fi

# --- build the Sysible packages and include them directly ------------------
if ! ls "$ROOT"/dist/*.deb >/dev/null 2>&1; then
    echo "== building Sysible packages =="
    # SYSIBLE_SKIP_SYSTERM: SysTerm is the GUI (GTK/VTE) terminal — a headless
    # server image must never build or ship it, or it would land in packages.chroot
    # and get installed (pulling a GUI stack). Skip it for the server build.
    SYSIBLE_SKIP_SYSTERM=1 "$ROOT/scripts/build-all.sh"
fi
mkdir -p config/packages.chroot
cp "$ROOT"/dist/*.deb config/packages.chroot/ 2>/dev/null || true
echo "Included $(ls config/packages.chroot/*.deb 2>/dev/null | wc -l) Sysible package(s) directly."

# --- expand the metapackage into the Debian-native toolkit -----------------
# Every package in sysible-server's Depends/Recommends/Suggests EXCEPT the
# sysible-* ones (included directly), systerm (its own repo), the vendor /
# GitHub-binary tools (installed by the hook, since they aren't in Debian), and
# the GUI/desktop packages (this is a HEADLESS server image — no GNOME, no
# Calamares, no desktop apps). One source of truth: the metapackage control.
awk '
    BEGIN {
        split("docker-ce docker-compose-plugin containerd.io kubectl helm k9s opentofu azure-cli google-cloud-cli codium sops eza", v, " ")
        for (i in v) VEND[v[i]] = 1
        # GUI / desktop packages from the workstation metapackage — excluded so
        # the headless server image never pulls a desktop stack.
        split("gnome-core calamares systerm wireshark virt-manager virt-viewer libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-gnome open-vm-tools-desktop", g, " ")
        for (i in g) VEND[g[i]] = 1
    }
    /^Description:/ { f=0 }
    /^(Depends|Recommends|Suggests):/ { f=1 }
    f {
        line=$0; sub(/^(Depends|Recommends|Suggests):/,"",line)
        if (line ~ /^[[:space:]]*#/) next
        n=split(line, a, ",")
        for (i=1;i<=n;i++) {
            gsub(/^[[:space:]]+|[[:space:]]+$/,"",a[i])
            split(a[i], b, /[[:space:]]/); name=b[1]
            if (name ~ /^[a-z0-9][a-z0-9.+-]+$/ && name !~ /^sysible-/ && name != "systerm" && !(name in VEND))
                print name
        }
    }
' "$ROOT/packages/sysible-meta/debian/control" | sort -u \
    > config/package-lists/sysible-toolkit.list.chroot
echo "Debian toolkit: $(grep -c . config/package-lists/sysible-toolkit.list.chroot) packages (vendor tools via hook)."

# --- make the TARGET bootloader installable offline -------------------------
# The Debian Installer makes the freshly-partitioned target bootable with GRUB.
# On an offline install it can only pull .debs from the ISO's own pool, and that
# pool contains ONLY packages that are installed in the live chroot. live-build's
# `--bootloaders grub-efi` sets up the ISO's *own* EFI boot but does NOT install
# the grub-efi-<arch> package in the filesystem — so neither the unpacked target
# nor the pool has it, and the installed system would fail to bootload:
#   E: Package 'grub-efi-amd64' has no installation candidate
#   chroot: failed to run command '/usr/sbin/update-grub': No such file or dir
# Install the correct grub flavour into the live system so it is (a) already
# present in the target after unpackfs and (b) available in the offline pool for
# the installer's grub step. Arch-selected here (the list is shared across arches,
# and grub-efi-amd64 has no arm64 candidate / vice-versa, which would abort the build).
if [ "$ARCH" = "arm64" ]; then
    printf '%s\n' grub-efi-arm64 grub-efi-arm64-bin grub-common \
        > config/package-lists/sysible-grub.list.chroot
else
    # amd64: grub-efi-amd64 covers UEFI targets (the common case, incl. VMs).
    # grub-pc-bin coexists with grub-efi (only the grub-pc metapackage conflicts)
    # so BIOS grub-install has its modules in the pool too.
    printf '%s\n' grub-efi-amd64 grub-efi-amd64-bin grub-pc-bin grub-common \
        > config/package-lists/sysible-grub.list.chroot
fi
echo "Target bootloader packages: $(tr '\n' ' ' < config/package-lists/sysible-grub.list.chroot)"

# --- assemble -------------------------------------------------------------
# Boot branding is done with source-level bootloader overrides that live-build
# consumes while building the ISO: config/bootloaders/isolinux/ (BIOS menu title
# + Sysible splash) and config/binary_grub/ (UEFI background). These are checked
# in, not generated, so they don't depend on where a given live-build keeps its
# templates.
lb clean --purge || true
lb config
$SUDO lb build

# --- brand GRUB (UEFI, incl. arm64) in the finished ISO --------------------
# Unlike isolinux, GRUB's grub.cfg is generated during binary_iso and is not
# override-able via config here, so edit it in the finished ISO with xorriso,
# which rewrites data files while KEEPING the El Torito + isohybrid/GPT boot
# structures (-boot_image any keep). Rebrand the entry titles and add a Sysible
# background. The release checksums are computed after this, so they match.
echo "GRUB-DEBUG: pwd=$(pwd)"
echo "GRUB-DEBUG: isos here: $(ls -1 ./*.iso 2>/dev/null | tr '\n' ' ')"
echo "GRUB-DEBUG: xorriso=$(command -v xorriso 2>/dev/null || echo NONE)"
ISO=$(find . -maxdepth 1 -name '*.hybrid.iso' 2>/dev/null | head -1)
echo "GRUB-DEBUG: selected ISO=[$ISO]"
if [ -n "$ISO" ]; then
    echo "===== branding GRUB + isolinux boot menu in $ISO ====="
    WORK=$(mktemp -d)
    $SUDO xorriso -osirrox on -indev "$ISO" -extract /boot/grub/grub.cfg "$WORK/grub.cfg" 2>/dev/null || true
    $SUDO xorriso -osirrox on -indev "$ISO" -extract /isolinux/live.cfg "$WORK/live.cfg" 2>/dev/null || true
    if [ -s "$WORK/grub.cfg" ]; then
        echo "-- grub.cfg BEFORE --"; grep -iE 'menuentry|background_image|Live system|Debian' "$WORK/grub.cfg" | head
        cp config/branding/splash.png "$WORK/sysible-splash.png"
        # GRUB: rebrand the live entry titles and add the Sysible background/theme.
        # We do NOT hand-add an install entry: `--debian-installer live` makes
        # live-build generate its own "… Installer" menu entries for the text-mode
        # Debian Installer, so the boot menu already offers Install/Rescue.
        python3 - "$WORK/grub.cfg" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p).read()
s = re.sub(r'Live system \((.*?) fail-safe mode\)', r'Sysible Server (Live, safe graphics) [\1]', s)
s = re.sub(r'Live system \((.*?)\)', r'Sysible Server (Live) [\1]', s)
s = s.replace('Debian GNU/Linux', 'Sysible Server')
# Brand the live GRUB menu with the Sysible THEME (dark hex background, centered
# mark, GREEN TEXT highlight — not a solid bar — and the "GNU GRUB version" line
# hidden). This MUST be APPENDED, not prepended: live-build's generated grub.cfg
# sets its own background/colours/theme as it is sourced, and GRUB honours the
# LAST directive when it renders the menu, so a prepended block is silently
# overridden (why arm64 kept the stock blue menu). Appended, ours win. gfxterm +
# a font are already up by this point (the stock menu renders text), so the theme
# has what it needs; we re-assert them for safety. The colour lines are only a
# fallback if the theme file can't load — light-green/black is green text on a
# transparent background (no garish highlight bar), never stock blue.
vis = ('\n\n# --- Sysible branding (appended last so it wins) ---\n'
       'insmod all_video\ninsmod efi_gop\ninsmod efi_uga\ninsmod gfxterm\ninsmod png\n'
       # gfxmode: let the firmware report its native mode (auto). Forcing a fixed
       # 16:9 mode (tried earlier) does NOT cure the "stretched/tall" look reported
       # under VMware Fusion on Apple Silicon — that stretch is the hypervisor
       # scaling one GOP mode to a differently-shaped VM window, not GRUB's choice,
       # and forcing a mode the window can't match only adds black bars/pillarbox.
       # gfxpayload=keep hands the same framebuffer to the kernel so the console
       # doesn't re-stretch. (VM-side fix: Fusion → Settings → Display, use full
       # resolution / disable stretch scaling.)
       'set gfxmode=auto\nset gfxpayload=keep\nterminal_output gfxterm\n'
       'loadfont ($root)/boot/grub/fonts/unicode.pf2\n'
       'set color_normal=light-gray/black\n'
       'set menu_color_normal=light-gray/black\n'
       'set menu_color_highlight=light-green/black\n'
       'set theme=($root)/boot/grub/themes/sysible/theme.txt\n'
       'export theme\n')
open(p, 'w').write(s + vis)
PY
        # isolinux (BIOS): rebrand the live entry labels. No hand-added install
        # entry — live-build's Debian-Installer integration provides its own.
        MAP_LIVE=""
        if [ -s "$WORK/live.cfg" ]; then
            echo "-- isolinux live.cfg BEFORE --"; grep -iE 'label|menu label|append' "$WORK/live.cfg" | head
            python3 - "$WORK/live.cfg" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p).read()
s = re.sub(r'(menu label \^?)Live system \((.*?) fail-safe mode\)', r'\1Sysible Server (Live, safe) [\2]', s)
s = re.sub(r'(menu label \^?)Live system \((.*?)\)', r'\1Sysible Server (Live) [\2]', s)
open(p, 'w').write(s)
PY
            MAP_LIVE="-map $WORK/live.cfg /isolinux/live.cfg"
        fi
        # Ship the Sysible GRUB theme onto the ISO's own boot filesystem so the
        # live menu (set theme=... above) can load it. The same theme dir is also
        # in the installed system via includes.chroot, so live + installed match.
        THEME_SRC="$PWD/config/includes.chroot/boot/grub/themes/sysible"
        MAP_THEME=""
        [ -d "$THEME_SRC" ] && MAP_THEME="-map $THEME_SRC /boot/grub/themes/sysible"
        $SUDO xorriso -boot_image any keep -dev "$ISO" \
            -map "$WORK/grub.cfg" /boot/grub/grub.cfg \
            -map "$WORK/sysible-splash.png" /boot/grub/sysible-splash.png \
            $MAP_THEME \
            $MAP_LIVE \
            -commit 2>&1 | tail -4
        # Post-commit verification is debug-only and MUST NOT fail the build.
        # On arm64 there is no isolinux, so extracting /isolinux/live.cfg errors;
        # guard every check with `|| true` so the (already-committed) branding
        # isn't undone by a failing diagnostic under `set -e`.
        echo "-- isolinux live.cfg AFTER --"
        $SUDO xorriso -osirrox on -indev "$ISO" -extract /isolinux/live.cfg "$WORK/live-after.cfg" 2>/dev/null || true
        grep -iE 'menu label|label install' "$WORK/live-after.cfg" 2>/dev/null | head || true
        echo "-- grub.cfg AFTER (re-extracted from ISO) --"
        $SUDO xorriso -osirrox on -indev "$ISO" -extract /boot/grub/grub.cfg "$WORK/after.cfg" 2>/dev/null || true
        grep -iE 'menuentry|background_image|Sysible|Live system' "$WORK/after.cfg" 2>/dev/null | head -20 || true
        echo "-- boot structures still present? --"
        $SUDO xorriso -indev "$ISO" -report_el_torito plain 2>&1 | grep -iE 'El Torito|Boot|Platform|catalog' | head || true
        $SUDO xorriso -indev "$ISO" -report_system_area plain 2>&1 | grep -iE 'ISO|MBR|GPT|isohybrid|System area type' | head || true
    else
        echo "!! could not extract /boot/grub/grub.cfg from $ISO"
    fi
    rm -rf "$WORK"
    echo "===== end GRUB branding ====="
fi

# --- verify boot branding landed in the built tree -------------------------
# binary/ persists after lb build, so we can prove the overrides were consumed
# without downloading the ISO. Look for our title + splash in the assembled tree.
echo "===== POST-BUILD boot-branding verification ====="
for f in $(find binary -maxdepth 4 -name 'menu.cfg' -o -maxdepth 4 -name 'grub.cfg' 2>/dev/null); do
    echo "----- $f -----"
    grep -iE 'menu title|menuentry|background_image|set (menu_)?color|Sysible|Debian' "$f" 2>/dev/null | head -20
done
echo "----- splash images in built tree -----"
find binary -maxdepth 4 -name 'splash.*' -exec ls -la {} \; 2>/dev/null
for sp in $(find binary -maxdepth 4 -name 'splash.png' 2>/dev/null); do
    echo "md5 $sp vs our override:"; md5sum "$sp" config/bootloaders/isolinux/splash.png 2>/dev/null
done
echo "===== end verification ====="
