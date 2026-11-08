"""The installer a server operator actually sees must not be stock Debian.

Reported as "Sysible Server's installation looks like something from 1995".

The binary hook did brand the installer — but only the GRAPHICAL one. Swapping
the banner needs usr/share/graphics and appending the palette needs a gtkrc,
and a text-mode initrd has neither, so both steps were correctly skipped and
d-i's newt frontend stayed stock: blue background, grey dialogs, red
highlights.

That is not an edge case. The hook's own notes record that arm64 ships NO
graphical installer at all, so on arm64 the unbranded text installer is the
only one anyone ever sees — and the fallback that makes install/gtk/ work there
copies the TEXT installer into it, so even the menu entry marked "Graphical
install" lands on the unbranded one.

libnewt reads NEWT_COLORS from the environment, and /sbin/debian-installer
sources every /lib/debian-installer-startup.d/* script before the frontend
starts, so a script dropped there colours the whole install. The colours match
sysible-tools on the installed system, so the installer and the system it
installs look like one product.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / \
    "live-build/config/hooks/normal/9400-sysible-installer-branding.hook.binary"
TOOLS = Path(__file__).resolve().parents[1] / \
    "live-build/config/includes.chroot/usr/local/bin/sysible-tools"
TEXT = HOOK.read_text(encoding="utf-8")


def _palette(blob):
    """name=fg,bg pairs out of a NEWT_COLORS blob."""
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r'^([a-z]+)=([^\n\']*)$', blob, re.M)}


def _hook_palette():
    m = re.search(r"SYSIBLE_NEWT_COLORS='(.*?)'", TEXT, re.S)
    assert m, "the hook defines no SYSIBLE_NEWT_COLORS palette"
    return _palette(m.group(1))


def test_the_hook_carries_a_text_mode_palette():
    p = _hook_palette()
    assert len(p) >= 15, f"palette looks truncated: {sorted(p)}"


@pytest.mark.skipif(shutil.which("cpio") is None, reason="cpio needed to build a test initrd")
def test_a_text_mode_initrd_really_comes_out_branded(tmp_path):
    """RUN the hook against an initrd with no graphics in it at all.

    A first version of this test read the hook's source and tried to prove the
    palette write was not inside the graphics-only branch. It passed when the
    write was re-gated with a different shell construct — i.e. it did not catch
    the very defect it was written for. Reading source to infer behaviour was
    the mistake; this builds a real initrd and looks at what comes out.
    """
    iso = tmp_path / "iso" / "install"
    iso.mkdir(parents=True)
    src = tmp_path / "src"
    (src / "sbin").mkdir(parents=True)
    (src / "sbin" / "debian-installer").write_text("#!/bin/sh\n")
    # deliberately NO usr/share/graphics and NO gtkrc — this is the stock-blue one
    subprocess.run(f"cd {src} && find . | cpio -o -H newc --quiet | gzip -9 > {iso}/initrd.gz",
                   shell=True, check=True)

    banner = tmp_path / "b.png"; banner.write_bytes(b"BANNER")
    preseed = tmp_path / "p.cfg"; preseed.write_text("d-i x\n")
    r = subprocess.run(["sh", str(HOOK)], cwd=tmp_path / "iso", capture_output=True, text=True,
                       env={**os.environ, "SYSIBLE_INSTALLER_BANNER": str(banner),
                            "SYSIBLE_PRESEED": str(preseed)})
    assert r.returncode == 0, r.stderr

    out = tmp_path / "out"; out.mkdir()
    subprocess.run(f"cd {out} && gzip -dc {iso}/initrd.gz | cpio -idm --quiet",
                   shell=True, check=True)
    script = out / "lib/debian-installer-startup.d/S99sysible-palette"
    assert script.is_file(), (
        "a text-mode initrd came out with no palette script. This is the "
        "original bug: branding gated behind graphics being present, which "
        "leaves arm64 — where no graphical installer ships at all — on stock "
        "Debian blue.\nhook said:\n" + r.stdout[-700:]
    )
    assert os.access(script, os.X_OK), "the startup script is not executable"
    body = script.read_text()
    assert "NEWT_COLORS" in body and "green" in body
    assert (out / "etc/newt/palette").is_file(), "no /etc/newt/palette fallback"
    # and it must still be valid shell, since d-i SOURCES it
    assert subprocess.run(["sh", "-n", str(script)]).returncode == 0


def test_the_installer_matches_the_installed_system():
    """One product. If sysible-tools is restyled, this should move with it."""
    tools = TOOLS.read_text(encoding="utf-8")
    m = re.search(r"NEWT_COLORS='(.*?)'", tools, re.S)
    assert m, "sysible-tools no longer defines a palette to match"
    installed, installer = _palette(m.group(1)), _hook_palette()
    shared = set(installed) & set(installer)
    assert len(shared) >= 15, f"only {len(shared)} keys in common"
    differing = {k: (installed[k], installer[k]) for k in shared
                 if installed[k] != installer[k]}
    assert not differing, (
        "the installer and the installed system disagree on colours "
        f"(installed, installer): {differing}"
    )


def test_it_is_not_the_stock_debian_look():
    """Stock d-i is blue and red. Ours is black and green."""
    p = _hook_palette()
    joined = " ".join(p.values())
    assert "blue" not in joined, "stock Debian blue is back in the palette"
    assert "red" not in joined, "stock Debian red is back in the palette"
    assert "green" in joined, "no brand green anywhere in the palette"
    assert p.get("root", "").endswith("black"), f"root is {p.get('root')!r}, not black"


def test_a_failure_to_brand_is_reported_not_silent():
    """Everything in this hook is best-effort so it can never fail the build —
    which means the only thing standing between a stock installer and shipping
    one is that it says so."""
    assert "no initrd got the text palette" in TEXT, \
        "a build that brands nothing would pass without a word"
