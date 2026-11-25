"""Picking "Install Sysible Server" must get the graphical installer.

Asked for as: "it should be only inside the debian style installer not a tui
based menu like I showed you" -- the blue newt dialogs.

Both entries run the SAME Debian Installer and ask the SAME debconf questions.
The only difference is the frontend, which is chosen by the initrd: the gtk one
renders them as the dark graphical dialogs, the text one as newt's blue boxes.
The entry named plainly "Install Sysible Server" used to carry the TEXT initrd,
with graphical tucked underneath it, so choosing the obvious thing got the ugly
installer.

The kernel is shared -- Debian's CD layout ships only the gtk INITRD in
install/gtk/ and one kernel at install/vmlinuz -- so this is entirely a question
of which initrd the first entry loads.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / "live-build" / "build.sh"


def _entries(gtk_present):
    """Run the real block out of build.sh for a given arch."""
    src = BUILD.read_text()
    i = src.index("    gtk = len(sys.argv) > 2")
    j = src.index("    s += entries")
    block = "\n".join(l[4:] if l.startswith("    ") else l for l in src[i:j].splitlines())
    ns = {"sys": type("A", (), {"argv": ["-", "x", "1" if gtk_present else "0"]})}
    exec(block, ns)
    out, cur = [], None
    for line in ns["entries"].splitlines():
        if line.startswith("menuentry"):
            cur = line.split('"')[1]
        elif line.strip().startswith("initrd") and cur:
            out.append((cur, line.strip().split()[-1]))
            cur = None
    return out


def test_the_plain_install_entry_is_graphical_where_graphical_exists():
    """The report, in one assertion."""
    entries = _entries(True)
    assert entries, "no installer entries are generated at all"
    name, initrd = entries[0]
    assert name == "Install Sysible Server", entries
    assert initrd.endswith("/gtk/initrd.gz"), (
        f"the obvious entry still loads the text installer: {initrd}")


def test_the_text_installer_is_still_reachable():
    """It is the fallback when the graphical one will not start, so it must
    stay on the menu -- just not as the default thing to pick."""
    entries = _entries(True)
    assert len(entries) == 2, entries
    name, initrd = entries[1]
    assert "text" in name.lower(), name
    assert initrd.endswith("/install/initrd.gz"), initrd


def test_an_arch_with_no_graphical_installer_does_not_pretend():
    """arm64 ships no gtk initrd whatsoever. It used to be offered an entry
    labelled "(graphical)" that silently booted the text installer -- a menu
    item that lies about what it does."""
    entries = _entries(False)
    assert len(entries) == 1, f"arm64 should get one honest entry: {entries}"
    name, initrd = entries[0]
    assert name == "Install Sysible Server", name
    assert "graphical" not in name.lower(), name
    assert initrd.endswith("/install/initrd.gz"), initrd


def test_both_entries_boot_the_same_shared_kernel():
    """Debian's CD layout has ONE installer kernel. An entry pointing at
    /install/gtk/vmlinuz dies with "file not found", which this build already
    rewrites -- so the generated entries must not reintroduce it."""
    src = BUILD.read_text()
    i = src.index("    gtk = len(sys.argv) > 2")
    j = src.index("    s += entries")
    assert "/install/gtk/vmlinuz" not in src[i:j], \
        "a generated entry points at a kernel that does not exist"


def test_the_preseed_is_on_every_installer_entry():
    """Without file=/cdrom/preseed.cfg the entry boots a stock Debian install:
    no Sysible questions, no bootloader fixes."""
    src = BUILD.read_text()
    i = src.index("    gtk = len(sys.argv) > 2")
    j = src.index("    s += entries")
    block = src[i:j]
    linux_lines = [l for l in block.splitlines() if "linux  /install" in l]
    assert linux_lines, block
    for l in linux_lines:
        assert "file=/cdrom/preseed.cfg" in l, l
