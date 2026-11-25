"""No architecture ships an install entry that quietly drops you into newt.

"Install Sysible Server" was reported landing in the blue text-mode installer
three separate times. Each fix changed a MENU; none of them checked the
artifact, and the guards written alongside them asserted on the build's own
output or on a hand-written fixture. So the ISO kept shipping and the report
kept coming back.

Two things close it:

  * 9300-sysible-gtk-installer fetches the graphical installer on arm64, which
    live-build never does -- lb_binary_debian-installer limits the download to
    amd64/i386. Debian publishes one for arm64 all the same. Verified against
    the real archive, not assumed: cdrom/gtk/initrd.gz for arm64 bookworm is
    50,748,002 bytes and contains etc/gtk-2.0/gtkrc and
    usr/share/graphics/logo_installer.png, while cdrom/initrd.gz beside it is
    22,103,479 bytes and contains neither.
  * check-install-entries.py reads the menus OUT OF THE FINISHED ISO and fails
    the build if an entry a person would plainly pick boots a text initrd.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "live-build/check-install-entries.py"
HOOK = ROOT / "live-build/config/hooks/normal/9300-sysible-gtk-installer.hook.binary"
BRANDING = ROOT / "live-build/config/hooks/normal/9400-sysible-installer-branding.hook.binary"
BUILD = ROOT / "live-build/build.sh"


def run_check(text, arch="amd64", tmp_path=None):
    f = tmp_path / "menu.cfg"
    f.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, str(CHECK), "--arch", arch, str(f)],
                          capture_output=True, text=True, timeout=60)


# --- the hook that gets arm64 a graphical installer -------------------------
def test_the_arm64_hook_exists_and_runs_before_the_branding_hook():
    """9400 creates a FALLBACK gtk initrd by copying the text one when none is
    present. Arriving after it would mean the copy wins and the real installer
    is never used."""
    assert HOOK.is_file(), "there is no hook to fetch the arm64 graphical installer"
    assert HOOK.stat().st_mode & 0o111, "the hook is not executable"
    assert HOOK.name < BRANDING.name, (
        f"{HOOK.name} must sort before {BRANDING.name}; live-build runs hooks "
        f"in name order and 9400's fallback only fires when the file is absent")


def test_the_hook_asks_debian_for_the_architecture_it_is_building():
    src = HOOK.read_text(encoding="utf-8")
    assert "installer-$ARCH/current/images/cdrom/gtk/initrd.gz" in src, (
        "the hook does not request the cdrom graphical initrd for the arch "
        "being built")
    assert "deb.debian.org" in src


def test_the_hook_refuses_anything_that_is_not_the_graphical_installer():
    """A mirror can answer with an error page, or with the text initrd. Both
    would restore the exact bug this hook exists to fix."""
    src = HOOK.read_text(encoding="utf-8")
    assert re.search(r"^\s*if ! gzip -t ", src, re.M), (
        "the hook does not check it got a gzip at all")
    # The PROBE line, not the word anywhere in the file. Checking for "gtkrc"
    # as a substring passed while the probe was disabled, because the comment
    # above it still said gtkrc.
    probe = [l for l in src.splitlines()
             if re.search(r"\bgrep\s+-qE\b", l)
             and "gtkrc" in l and "usr/share/graphics" in l]
    assert probe, (
        "the hook has no live grep that proves the download carries the gtk "
        "payload; a mirror serving the TEXT initrd would be accepted")


def test_the_hook_fails_rather_than_falling_back():
    """Silent fallback to the text installer is what shipped three times.

    Precise, not blanket: the hook has one `|| true`, on the cpio LISTING, and
    that is correct -- an unreadable archive yields an empty listing, which the
    grep immediately below then rejects. What must never be swallowed is the
    DOWNLOAD failing.
    """
    src = HOOK.read_text(encoding="utf-8")
    assert "set -e" in src

    dl = re.search(r"if ! wget[^\n]*\n(.*?)\nfi\n", src, re.S)
    assert dl, "the hook does not guard the download at all"
    assert "exit 1" in dl.group(1), (
        "a failed download does not stop the build, so hook 9400 would copy "
        "the TEXT initrd to the graphical path and the ISO would ship newt")
    assert "|| true" not in dl.group(1), "the download failure is swallowed"

    # Every `|| true` in the file must be the listing one.
    for n, line in enumerate(src.splitlines(), 1):
        if "|| true" in line:
            assert "cpio -t" in line, (
                f"line {n} swallows a failure that is not the cpio listing: "
                f"{line.strip()}")

    # And a non-graphical download is rejected rather than kept.
    assert src.count("rm -f \"$DEST.new\"") >= 2, (
        "a rejected download is left in place at the graphical path")


# --- the checker ------------------------------------------------------------
PLAIN_TEXT = (
    "default install\n"
    "label install\n\tmenu label Install Sysible Server\n\tinitrd /install/initrd.gz\n"
)
ALL_GOOD = (
    "label installstart\n\tmenu label Install Sysible Server\n\tinitrd /install/gtk/initrd.gz\n"
    "label installtext\n\tmenu label Install Sysible Server (text mode)\n\tinitrd /install/initrd.gz\n"
    "label expert\n\tmenu label Expert install\n\tinitrd /install/initrd.gz\n"
    "label rescue\n\tmenu label Rescue mode\n\tinitrd /install/initrd.gz\n"
)
GRUB_GOOD = (
    'menuentry "Install Sysible Server" --hotkey=i {\n'
    '    linux  /install/vmlinuz file=/cdrom/preseed.cfg\n'
    '    initrd /install/gtk/initrd.gz\n}\n'
    'menuentry "Install Sysible Server (text mode)" {\n'
    '    linux  /install/vmlinuz file=/cdrom/preseed.cfg\n'
    '    initrd /install/initrd.gz\n}\n'
)


@pytest.mark.parametrize("arch", ["amd64", "arm64"])
def test_a_plain_entry_on_the_text_installer_fails_on_every_arch(arch, tmp_path):
    """This is the reported bug, stated as a test. arm64 is included because
    Debian ships it a graphical installer too."""
    r = run_check(PLAIN_TEXT, arch, tmp_path)
    assert r.returncode != 0, (
        f"arch={arch}: a plain 'Install Sysible Server' booting the TEXT initrd "
        f"was accepted:\n{r.stdout}\n{r.stderr}")
    assert "lands in newt" in r.stderr


@pytest.mark.parametrize("arch", ["amd64", "arm64"])
def test_declared_variants_are_left_alone(arch, tmp_path):
    """Expert, rescue and an explicit text-mode entry are text by intent."""
    r = run_check(ALL_GOOD, arch, tmp_path)
    assert r.returncode == 0, f"arch={arch}: a correct menu was rejected:\n{r.stdout}\n{r.stderr}"


def test_it_reads_grub_menus_too(tmp_path):
    r = run_check(GRUB_GOOD, "amd64", tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Install Sysible Server" in r.stdout


def test_a_menu_with_no_graphical_entry_at_all_fails(tmp_path):
    r = run_check(
        "label a\n\tmenu label Install Sysible Server (text mode)\n\tinitrd /install/initrd.gz\n",
        "amd64", tmp_path)
    assert r.returncode != 0, (
        "a menu whose ONLY install entry is text-mode was accepted; the "
        "graphical installer is then missing or unreferenced")


# --- and the build actually runs it ----------------------------------------
def test_the_build_checks_the_finished_iso_not_its_own_output():
    src = BUILD.read_text(encoding="utf-8")
    # INVOKED, not merely mentioned. Checking for the filename as a substring
    # passed while the call had been replaced by `true`.
    m = re.search(r"^\s*if python3 \"\$PWD/check-install-entries\.py\"", src, re.M)
    assert m, (
        "the build does not actually run check-install-entries.py as a command "
        "whose exit status it acts on")
    assert "xorriso" in src[:m.start()], (
        "the checker must run on menus extracted from the built ISO")
    blk = src[max(0, m.start() - 1500):m.start() + 600]
    assert "install.cfg" in blk and "grub.cfg" in src, (
        "both menus must be checked -- BIOS and UEFI are different files, and "
        "fixing only one is how this shipped twice")
    assert "gate_fail=1" in src[m.start():m.start() + 600], (
        "a failing check must fail the build")
