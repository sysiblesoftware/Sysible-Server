"""Anything the ISO shows a brand on must be generated from the mark AND named
in the manifest.

The installer banner was neither. build.sh exported it, the binary hook copied
it into every graphical initrd, and it appeared at the top of every page of the
Debian Installer -- but render-branding.py did not generate it and the manifest
did not list it. So when the mark became the rack glyph, the boot artwork moved
and the banner stayed on the "S" from 18 August, and no guard could notice:
verify-branding.sh only checks files the manifest names.

Being shipped and being checked were two different sets. This keeps them one.
"""
import hashlib
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
BUILD_SH = REPO / "live-build" / "build.sh"
MANIFEST = REPO / "branding" / "logo" / "BRANDING.manifest"
IN_IMAGE = REPO / "live-build/config/includes.chroot/usr/share/sysible/branding.manifest"


def _manifest():
    """{relative path: sha256} as recorded."""
    out = {}
    for line in MANIFEST.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            digest, rel = line.split(None, 1)
            out[rel.strip()] = digest
    return out


def _exported(var):
    """The path build.sh exports for `var`, with $ROOT resolved."""
    m = re.search(rf'^export {var}="([^"]+)"', BUILD_SH.read_text(), re.M)
    assert m, f"build.sh no longer exports {var}"
    return m.group(1).replace("$ROOT/", "").replace("${ROOT}/", "")


def test_the_installer_banner_is_generated_and_checked():
    """The exact file that was stale: shown on every installer page, and until
    now invisible to every branding guard."""
    rel = _exported("SYSIBLE_INSTALLER_BANNER")
    assert (REPO / rel).is_file(), f"build.sh points at a file that is not there: {rel}"
    assert rel in _manifest(), (
        f"{rel} is shown on every installer page but is not in the branding "
        f"manifest, so nothing regenerates it and no guard can see it drift")


@pytest.mark.parametrize("rel", sorted(_manifest()))
def test_every_manifest_entry_is_present_and_current(rel):
    p = REPO / rel
    assert p.is_file(), f"the manifest names {rel}, which does not exist"
    got = hashlib.sha256(p.read_bytes()).hexdigest()
    assert got == _manifest()[rel], (
        f"{rel} has drifted from the canonical mark -- "
        f"run: python3 branding/render-branding.py")


def test_the_in_image_manifest_is_the_same_file():
    """The installed system verifies against its own copy; if the two differ it
    is checking a different set than CI did."""
    assert IN_IMAGE.read_bytes() == MANIFEST.read_bytes(), \
        "the in-image branding manifest differs from the repo one"
