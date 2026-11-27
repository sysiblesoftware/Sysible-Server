"""The entry that reads as "install this" must boot the GRAPHICAL installer.

Reported as "why is this menu in the UEFI boot of the new sysible server", about
the optional-software question appearing as a grey newt box immediately after
GRUB. It was diagnosed then as the question being incapable of rendering
graphically -- preseed/early_command fires before the graphical frontend
exists, so db_input "can only draw newt" -- and the question was deleted from
the installer entirely on that basis (6ab10c0).

That diagnosis was wrong, and a screenshot settled it: clicking through the
graphical installer shows the SAME question, branded, with real checkboxes and
the Sysible header. It renders perfectly well.

The actual fault was the boot menu. build.sh adds the UEFI install entries,
because live-build leaves GRUB's installer entries commented out, and the first
one -- the one carrying the plain name and the `i` hotkey, the one that reads as
"install this" -- pointed at /install/vmlinuz, the TEXT installer. The
graphical entry existed two lines below and nothing suggested it was the normal
path. Everyone picked the text one and got newt.

So this pins the payload the primary entry boots, not the presence of an entry.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "live-build/build.sh"

ENTRY = re.compile(
    r"""menuentry\s+\\?"(?P<title>[^"\\]+)\\?"(?P<flags>[^{]*)\{(?P<body>.*?)\}""",
    re.S,
)


def _install_entries():
    """The install menuentries build.sh appends to the UEFI grub.cfg."""
    src = BUILD.read_text(encoding="utf-8")
    out = []
    for m in ENTRY.finditer(src):
        title = m.group("title")
        if "install" not in title.lower():
            continue
        body = m.group("body")
        # build.sh holds these as Python string literals, so a token can be
        # followed by the literal characters \n' -- stop at those, not just at
        # whitespace, or every path comes back with quoting glued to it.
        linux = re.search(r"linux\s+([^\s\\']+)", body)
        initrd = re.search(r"initrd\s+([^\s\\']+)", body)
        if not linux or not initrd:
            continue
        out.append({
            "title": title,
            "hotkey": "--hotkey" in m.group("flags"),
            "kernel": linux.group(1),
            "initrd": initrd.group(1),
        })
    return out


def test_there_are_install_entries_at_all():
    """UEFI firmware shows only commented install entries without these, which
    once left a UEFI boot unable to reach the installer at all."""
    assert _install_entries(), (
        "build.sh no longer adds UEFI install entries — a UEFI boot cannot "
        "reach the installer"
    )


def test_the_primary_entry_boots_the_graphical_installer():
    entries = _install_entries()
    first = entries[0]
    assert "gtk" in first["initrd"], (
        f"the first install entry, {first['title']!r}, boots {first['initrd']} "
        f"— the TEXT installer. Everything it asks is drawn in newt, including "
        f"the optional-software question that was reported as 'this menu in the "
        f"UEFI boot'. The graphical initrd renders the same question branded."
    )


def test_the_primary_entry_is_the_one_that_reads_as_install():
    """Plain name and the hotkey, so nobody has to know to scroll."""
    entries = _install_entries()
    first = entries[0]
    assert first["hotkey"], (
        f"the first install entry {first['title']!r} has no hotkey, so the "
        f"hotkey belongs to something else and that is what people will press"
    )
    assert not re.search(r"text|graphical|alternate", first["title"], re.I), (
        f"the primary entry is qualified as {first['title']!r}. A qualifier "
        f"reads as 'the unusual one', which is how the text installer became "
        f"the default choice."
    )


def test_a_text_installer_is_still_offered():
    """A machine whose framebuffer will not come up, or a serial console, needs
    it — removing it would trade one stuck install for another."""
    entries = _install_entries()
    text = [e for e in entries if "gtk" not in e["initrd"]]
    assert text, "no text-mode installer entry is offered any more"
    assert any(re.search(r"text", e["title"], re.I) for e in text), (
        "the text entry is not labelled as text mode, so it is indistinguishable "
        "from the graphical one in the menu"
    )


@pytest.mark.parametrize("field", ["kernel", "initrd"])
def test_every_entry_points_at_a_path_the_build_guarantees(field):
    """Hook 9400 creates install/gtk/vmlinuz (Debian ships only the gtk initrd),
    so both paths are real. A typo here is 'you need to load the kernel first'."""
    allowed = {
        "/install/vmlinuz", "/install/initrd.gz",
        "/install/gtk/vmlinuz", "/install/gtk/initrd.gz",
    }
    for e in _install_entries():
        assert e[field] in allowed, (
            f"{e['title']!r} boots {e[field]}, which nothing in the build "
            f"guarantees exists; GRUB fails with 'file not found'"
        )


def test_the_preseed_is_passed_on_every_entry():
    """It carries the bootloader fixes; without it the installed system has
    nothing to boot."""
    for e in _install_entries():
        src = BUILD.read_text(encoding="utf-8")
        assert "file=/cdrom/preseed.cfg" in src, (
            f"{e['title']!r} does not pass the preseed"
        )
