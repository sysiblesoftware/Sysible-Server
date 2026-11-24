"""Three firmware modes, three grub flavours, one offline pool.

    "The 'grub-efi-ia32' package failed to install into /target/. Without the
     GRUB boot loader, the installed system will not boot."

d-i's grub-installer apt-installs a flavour METApackage chosen by the firmware:
grub-pc for BIOS, grub-efi-ia32 for 32-bit UEFI, grub-efi-amd64 for 64-bit. The
pool held only the last of the three, so 64-bit UEFI was the only firmware this
image could actually finish an install on -- which is also why the earlier
BIOS attempt died at the same step with a different package name.

And the safety net that exists to catch exactly that chose its target from
`uname -m`, so on an amd64 CPU behind 32-bit firmware it would have asked for
a 64-bit grub that 32-bit firmware cannot load, and failed one step later.

SECURE BOOT is the same class of gap seen from the other side: Workstation
ships shim-signed + grub-efi-<arch>-signed and boots on a stock Secure-Boot
machine; Server, from the same build system, shipped neither and was simply
rejected by the firmware.
"""
import os
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
BUILD = (REPO / "live-build" / "build.sh").read_text(encoding="utf-8")
PRESEED = (REPO / "live-build" / "config" / "includes.binary" / "preseed.cfg").read_text(encoding="utf-8")
SH = shutil.which("sh")


def _amd64_pool():
    """The package list this build writes for amd64.

    COMMENTS ARE STRIPPED FIRST. The first version of this did not, and the
    comments above the list name grub-efi-ia32-bin several times explaining why
    it is there -- so deleting it from the actual printf still "passed". A guard
    satisfied by its own explanation, which is the same trap as one tripped by
    it. Found by mutation.
    """
    blk = BUILD[BUILD.index('if [ "$ARCH" = "arm64" ]'):]
    blk = blk[blk.index("else"):blk.index("> config/package-lists/sysible-grub.list.chroot", blk.index("else"))]
    code = "\n".join(l for l in blk.split("\n") if not l.strip().startswith("#"))
    return set(re.findall(r"[a-z0-9][a-z0-9.+-]*", code.replace("printf", " ").replace("%s", " ")))


# ---- the pool has a flavour for every firmware ------------------------------
@pytest.mark.parametrize("pkg,why", [
    ("grub-efi-amd64-bin", "64-bit UEFI"),
    ("grub-efi-ia32-bin", "32-bit UEFI — the reported failure"),
    ("grub-pc-bin", "legacy BIOS"),
])
def test_the_offline_pool_can_boot_each_firmware(pkg, why):
    assert pkg in _amd64_pool(), f"nothing in the pool can install GRUB for {why}"


def test_the_metapackages_are_still_kept_out():
    """grub-pc and grub-efi-ia32 CONFLICT with grub-efi-amd64; only one can be
    installed in the chroot, which is why the -bin packages are used."""
    pool = _amd64_pool()
    for meta in ("grub-pc", "grub-efi-ia32"):
        assert meta not in pool, \
            f"{meta} conflicts with grub-efi-amd64 and would break the build"


def test_the_image_can_boot_a_secure_boot_machine():
    """Workstation has shipped this for some time; Server had neither package,
    so its ISO was rejected until someone turned Secure Boot off."""
    pool = _amd64_pool()
    assert "shim-signed" in pool, \
        "no Microsoft-signed shim: Secure Boot firmware rejects the ISO outright"
    assert "grub-efi-amd64-signed" in pool, \
        "shim has no Debian-signed grub to chainload"


# ---- and the net actually installs it, per firmware -------------------------
@pytest.fixture()
def bootloader(tmp_path):
    """Extract the real in-target script from the preseed and run it against
    fake firmware. Reading the shell cannot tell you which branch it takes."""
    joined = PRESEED[PRESEED.index("d-i preseed/late_command string"):]
    joined = joined[:joined.index("\n\n")] if "\n\n" in joined else joined
    joined = joined.replace("\\\n", "")
    m = re.search(r"in-target sh -c '(.*)' \|\| true", joined, re.S)
    assert m, "could not find the in-target bootloader script"
    script = m.group(1).replace("\\\\", "\\")

    (tmp_path / "bin").mkdir()
    (tmp_path / "boot" / "efi" / "EFI" / "debian").mkdir(parents=True)
    (tmp_path / "var" / "log").mkdir(parents=True)
    calls = tmp_path / "calls"
    for t in ("grub-install", "update-grub", "apt-get"):
        f = tmp_path / "bin" / t
        f.write_text(f'#!/bin/sh\necho "{t} $*" >> "$CALLS"\nexit 0\n'); f.chmod(0o755)
    gp = tmp_path / "bin" / "grub-probe"
    gp.write_text('#!/bin/sh\necho "grub-probe $*" >> "$CALLS"\necho /dev/sda\n'); gp.chmod(0o755)

    efi = tmp_path / "sys" / "firmware" / "efi"
    script = (script
              .replace("/sys/firmware/efi/fw_platform_size", str(efi / "fw_platform_size"))
              .replace("-d /sys/firmware/efi", f"-d {efi}")
              .replace("/boot/efi", str(tmp_path / "boot" / "efi"))
              .replace("L=/var/log/sysible-bootloader.log", f"L={tmp_path}/var/log/bl.log"))
    run = tmp_path / "run.sh"; run.write_text(script)

    class R:
        def run(self, firmware):
            if firmware is None:
                shutil.rmtree(efi, ignore_errors=True)
            else:
                efi.mkdir(parents=True, exist_ok=True)
                (efi / "fw_platform_size").write_text(f"{firmware}\n")
            calls.write_text("")
            subprocess.run([SH, str(run)], timeout=60, capture_output=True, text=True,
                           env={**os.environ, "PATH": f"{tmp_path}/bin:{os.environ['PATH']}",
                                "CALLS": str(calls)})
            return calls.read_text()
    return R()


pytestmark = pytest.mark.skipif(not SH, reason="no sh on this machine")


@pytest.mark.parametrize("firmware,target,pkg", [
    (64, "x86_64-efi", "grub-efi-amd64-bin"),
    (32, "i386-efi", "grub-efi-ia32-bin"),
])
def test_uefi_follows_the_firmware_not_the_cpu(bootloader, firmware, target, pkg):
    """`uname -m` says amd64 in both cases. A 64-bit grub cannot be loaded by
    32-bit firmware at all, so choosing by CPU is choosing wrong."""
    out = bootloader.run(firmware)
    assert f"grub-install --target={target}" in out, \
        f"{firmware}-bit firmware got the wrong grub target:\n{out}"
    assert pkg in out, f"{firmware}-bit firmware did not fetch {pkg}"


def test_bios_still_writes_the_mbr(bootloader):
    out = bootloader.run(None)
    assert "grub-install --target=i386-pc" in out, out
    # Match the TARGET, not the string "grub-efi": `--target=x86_64-efi`
    # contains no "grub-efi", so the first version of this missed exactly the
    # mistake it was written for.
    assert "-efi" not in out, f"it tried an EFI install on a BIOS machine:\n{out}"


def test_a_32_bit_install_lands_at_the_path_the_firmware_looks_for(bootloader):
    """The removable-media fallback is per-architecture: BOOTIA32.EFI, not
    BOOTX64.EFI, or 32-bit firmware finds nothing."""
    joined = PRESEED.replace("\\\n", "")
    assert "BOOTIA32.EFI" in joined, "the 32-bit fallback path is never written"
