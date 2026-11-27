"""The graphical installer must not call itself Debian.

Asked for directly: "All mention of debian in the graphical installer change it
to sysible." Untouched, d-i narrates a Sysible install in Debian's words --
"Debian installer main menu", "Finish the installation ... Debian GNU/Linux" --
because every visible string comes from the debconf template databases carried
in the installer's own initrd.

The danger is that the same word, lowercased, is load-bearing everywhere:

    deb.debian.org / security.debian.org    apt sources
    /EFI/debian, --bootloader-id=debian     where grub-installer writes, and
                                            what the preseed then copies to
                                            /EFI/BOOT so UEFI finds it
    debian-installer, debconf, *.deb        binaries and package names

Rewriting any of those breaks apt, breaks UEFI boot, or breaks the installer.
So the rewrite is a word-boundary match on the CAPITALISED form only, skipping
any line carrying a URL, a path or an address — and this proves both halves by
running the real hook over a real initrd.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "live-build/config/hooks/normal/9400-sysible-installer-branding.hook.binary"

# Lines a real d-i templates.dat carries, prose and identifiers side by side.
SAMPLE = """\
Name: debian-installer/main-menu
Type: text
Description: Debian installer main menu

Name: debian-installer/title
Type: text
Description: Debian GNU/Linux installer

Name: grub-installer/bootdev
Type: string
Description: Device for boot loader installation
 The Debian boot loader needs to be installed to a drive.

Name: apt-setup/mirror
Type: string
Default: deb.debian.org
Description: Archive mirror
 Packages are fetched from http://deb.debian.org/debian

Name: grub-installer/only_debian
Type: boolean
Description: Install the GRUB boot loader to the EFI path /EFI/debian

Name: finish-install/reboot_in_progress
Type: text
Description: Installation complete — Debian is now installed
"""

MUST_BECOME_SYSIBLE = [
    "Sysible installer main menu",
    "Sysible installer",                 # from "Debian GNU/Linux installer"
    "The Sysible boot loader",
    "Sysible is now installed",
]
MUST_SURVIVE_UNTOUCHED = [
    "debian-installer/main-menu",
    "debian-installer/title",
    "Default: deb.debian.org",
    "http://deb.debian.org/debian",
    "grub-installer/only_debian",
    "/EFI/debian",
]


@pytest.fixture(scope="module")
def patched(tmp_path_factory):
    if shutil.which("cpio") is None:
        pytest.skip("cpio needed to build a test initrd")
    tmp = tmp_path_factory.mktemp("words")
    iso = tmp / "iso" / "install"
    iso.mkdir(parents=True)
    src = tmp / "src"
    (src / "sbin").mkdir(parents=True)
    (src / "sbin" / "debian-installer").write_text("#!/bin/sh\n")
    db = src / "var/lib/cdebconf"
    db.mkdir(parents=True)
    (db / "templates.dat").write_text(SAMPLE)
    subprocess.run(
        f"cd {src} && find . | cpio -o -H newc --quiet | gzip -9 > {iso}/initrd.gz",
        shell=True, check=True,
    )
    preseed = tmp / "p.cfg"; preseed.write_text("d-i x\n")
    r = subprocess.run(["sh", str(HOOK)], cwd=tmp / "iso", capture_output=True, text=True,
                       env={**os.environ, "SYSIBLE_PRESEED": str(preseed)})
    assert r.returncode == 0, r.stderr
    out = tmp / "out"; out.mkdir()
    subprocess.run(f"cd {out} && gzip -dc {iso}/initrd.gz | cpio -idm --quiet",
                   shell=True, check=True)
    return (out / "var/lib/cdebconf/templates.dat").read_text(), r.stdout


@pytest.mark.parametrize("phrase", MUST_BECOME_SYSIBLE)
def test_the_visible_words_say_sysible(phrase, patched):
    text, log = patched
    assert phrase in text, (
        f"{phrase!r} is not in the installer's templates, so the graphical "
        f"installer still narrates the install in Debian's words.\n\n"
        f"hook said:\n{log[-500:]}\n\ngot:\n{text}"
    )


@pytest.mark.parametrize("ident", MUST_SURVIVE_UNTOUCHED)
def test_the_identifiers_are_untouched(ident, patched):
    text, _ = patched
    assert ident in text, (
        f"{ident!r} was rewritten. That is not branding, it is an identifier: "
        f"apt sources, the EFI path grub-installer writes and the preseed then "
        f"copies to /EFI/BOOT, or a question name d-i looks up. Changing it "
        f"breaks apt, UEFI boot, or the installer."
    )


def test_no_capitalised_debian_is_left_in_the_visible_text(patched):
    text, _ = patched
    import re
    leftover = [
        l for l in text.splitlines()
        if re.search(r"\bDebian\b", l)
    ]
    assert not leftover, "visible text still says Debian:\n  " + "\n  ".join(leftover)


def test_the_hook_reports_what_it_reworded(patched):
    _, log = patched
    assert "words=yes" in log, (
        "the hook did not report rewording this initrd, so a future change that "
        "silently stops doing it would look identical in the build log\n\n" + log
    )
