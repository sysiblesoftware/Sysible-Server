"""A BIOS boot must reach the same installer a UEFI boot does.

The graphical-installer default was applied to grub.cfg and called done. It was
never applied to isolinux. grub.cfg is the UEFI menu; /isolinux/install.cfg is
the BIOS one, and they are different files with different syntax. So a UEFI
boot got the dark graphical installer while a BIOS boot still landed in newt's
blue dialogs — reported from a real install, after the fix had been described
as shipped.

The build's own comment recorded the gap without anyone noticing it was one:

    # isolinux (BIOS): rebrand the live entry labels. No hand-added install
    # entry — live-build's Debian-Installer integration provides its own.

It rebranded live.cfg and left install.cfg stock.

These tests RUN the rewrite against a stock Debian install.cfg rather than
asserting on strings build.sh emits. The previous round of tests checked that
build.sh printed the right menuentry text, which it did — and the ISO still
booted the wrong installer, because nothing checked that the change reached the
artifact. The last test here is that check.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REWRITE = ROOT / "live-build/rewrite-installcfg.py"
BUILD = ROOT / "live-build/build.sh"

# Debian's stock isolinux install menu, as live-build's --debian-installer
# integration writes it.
STOCK = """label install
\tmenu label ^Install
\tlinux /install/vmlinuz
\tinitrd /install/initrd.gz
\tappend vga=788 --- quiet
label installgui
\tmenu label ^Graphical install
\tlinux /install/gtk/vmlinuz
\tinitrd /install/gtk/initrd.gz
\tappend video=vesa:ywrap,mtrr vga=788 --- quiet
"""


def rewritten(text=STOCK):
    r = subprocess.run(["python3", str(REWRITE)], input=text,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def entry(cfg, label):
    """The body of the `label <name>` block."""
    m = re.search(rf"^label\s+{label}\b(.*?)(?=^label\s|\Z)", cfg, re.M | re.S)
    assert m, f"no `label {label}` block in:\n{cfg}"
    return m.group(1)


def test_the_graphical_entry_is_the_default():
    """Pressing enter must not land in newt."""
    cfg = rewritten()
    m = re.search(r"^default\s+(\S+)", cfg, re.M)
    assert m, "install.cfg sets no default, so isolinux falls back to the first label"
    assert m.group(1) == "installgui", \
        f"the default BIOS install entry is {m.group(1)!r}, not the graphical one"


def test_the_plain_name_belongs_to_the_graphical_entry():
    cfg = rewritten()
    assert "Install Sysible Server" in entry(cfg, "installgui")
    assert "text mode" not in entry(cfg, "installgui")


def test_the_newt_entry_says_so():
    """It stays available — it is the fallback when the graphical frontend will
    not start — but it must not be the one that looks like the normal choice."""
    cfg = rewritten()
    assert "text mode" in entry(cfg, "install"), \
        "the newt entry is not marked as text mode, so both entries read alike"


def test_the_graphical_entry_keeps_the_gtk_initrd():
    """The frontend is chosen by the INITRD. Lose this and the entry is just the
    newt installer wearing a different label."""
    assert "/install/gtk/initrd.gz" in entry(rewritten(), "installgui")


def test_the_gtk_kernel_path_that_does_not_exist_is_repointed():
    """Debian's CD layout ships one installer kernel at install/vmlinuz; only
    the INITRD lives under install/gtk/. Stock install.cfg points at
    /install/gtk/vmlinuz anyway, which fails to boot."""
    cfg = rewritten()
    assert "/install/gtk/vmlinuz" not in cfg
    assert "linux /install/vmlinuz" in entry(cfg, "installgui")


def test_the_rewrite_is_idempotent():
    """The build may re-run over an already-branded ISO."""
    once = rewritten()
    assert rewritten(once) == once


def test_the_rewrite_actually_reaches_the_iso():
    """THE TEST THAT WAS MISSING. A rewrite that is never mapped back onto the
    ISO changes nothing a user boots — which is exactly how the GRUB-only fix
    passed its tests and still shipped a newt installer over BIOS."""
    b = BUILD.read_text(encoding="utf-8")
    code = "\n".join(l for l in b.splitlines() if not l.lstrip().startswith("#"))
    assert "rewrite-installcfg.py" in code, "build.sh never runs the rewrite"
    assert "-extract /isolinux/install.cfg" in code, \
        "build.sh never pulls install.cfg off the ISO, so there is nothing to rewrite"
    assert re.search(r"-map\s+\"?\$\{?WORK\}?/install\.cfg\"?\s+/isolinux/install\.cfg", code), \
        "the rewritten install.cfg is never mapped back onto the ISO"
    # and it must be passed to the xorriso invocation, not merely assigned
    assert "$MAP_INSTALL" in code, \
        "MAP_INSTALL is built but never handed to xorriso -- the rewrite would be dead code"
