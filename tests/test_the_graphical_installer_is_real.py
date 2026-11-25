"""The boot menu's plain "Install Sysible Server" entry must boot the GRAPHICAL
installer, not the newt TUI.

HOW IT SHIPPED BROKEN, because the shape of the bug is the point:

  * auto/config passed `--debian-installer live` and never
    `--debian-installer-gui true`. live-build's own lb_binary_debian-installer
    sets DOWNLOAD_GTK_INSTALLER=0 unless that is exactly "true", so the
    graphical initrd was never downloaded.
  * config/hooks/normal/9400-sysible-installer-branding then CREATED
    install/gtk/initrd.gz by copying the TEXT initrd, so the menu entry would
    resolve rather than die with "file not found". Its log line says
    "(falls back to the text installer)".
  * the payload gate checked `[ -f binary/install/gtk/initrd.gz ]`, which the
    copy satisfied. Green build, published ISO, newt installer.

Existence was never the question. These guards ask about CONTENT and about the
one config flag that decides whether there is anything real to find.
"""
import os
import re
import shutil
import subprocess
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AUTO_CONFIG = os.path.join(ROOT, "live-build", "auto", "config")
BUILD_SH = os.path.join(ROOT, "live-build", "build.sh")
HOOK = os.path.join(ROOT, "live-build", "config", "hooks", "normal",
                    "9400-sysible-installer-branding.hook.binary")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_auto_config_asks_for_the_graphical_installer():
    """Without this flag there is no graphical installer to boot, whatever the
    menu says."""
    s = _read(AUTO_CONFIG)
    # Tolerate whitespace and line continuations; insist on the value.
    assert re.search(r"--debian-installer-gui\s+true", s), (
        "auto/config does not pass --debian-installer-gui true, so live-build "
        "sets DOWNLOAD_GTK_INSTALLER=0 and never fetches the graphical "
        "installer. The branding hook then fabricates install/gtk/initrd.gz "
        "from the TEXT initrd and the menu's graphical entry boots newt.")


def test_the_menu_decides_on_content_not_on_the_path_existing():
    """The fallback copy makes the path exist on every build, so `-f` is not a
    test of anything."""
    s = _read(BUILD_SH)
    m = re.search(r"GTK_INITRD=0\n(.{0,900}?)echo \"GRUB-DEBUG", s, re.S)
    assert m, "could not find the GTK_INITRD decision in build.sh"
    block = m.group(1)
    assert "cpio" in block and ("gtkrc" in block or "usr/share/graphics" in block), (
        "build.sh decides whether to offer a graphical menu entry without "
        "looking INSIDE the initrd. The branding hook's fallback copy makes "
        "`[ -f ... ]` true on every build, including the ones with no "
        "graphical installer at all:\n" + block)


def test_the_hook_still_only_fills_the_gap_it_documents():
    """The fallback is correct for arm64, which genuinely has no graphical
    installer. It must stay a fallback -- it must not overwrite a real one."""
    s = _read(HOOK)
    assert 'if [ ! -f "$d/gtk/initrd.gz" ]' in s, (
        "the branding hook's gtk fallback no longer guards on absence, so it "
        "could overwrite a REAL graphical initrd with the text one")


def _initrd(tmp_path, name, entries):
    """A real gzipped newc cpio archive, built the way the ISO's are."""
    src = tmp_path / (name + ".d")
    for rel in entries:
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    listing = subprocess.run(["find", "."], cwd=src, capture_output=True, text=True,
                             check=True).stdout
    cpio = subprocess.run(["cpio", "-o", "-H", "newc", "--quiet"], cwd=src,
                          input=listing.encode(), capture_output=True, check=True).stdout
    out = tmp_path / name
    out.write_bytes(subprocess.run(["gzip", "-9", "-c"], input=cpio,
                                   capture_output=True, check=True).stdout)
    return out


# The discriminator exactly as build.sh runs it.
PROBE = (
    "_gl=$(gzip -dc \"$1\" 2>/dev/null | cpio -t --quiet 2>/dev/null || true); "
    "printf '%s\\n' \"$_gl\" | grep -qE '(^|/)gtkrc$|usr/share/graphics/'"
)


def _probe(initrd):
    if not shutil.which("cpio"):
        pytest.skip("cpio is not installed on this runner")
    return subprocess.run(["sh", "-c", PROBE, "sh", str(initrd)]).returncode == 0


def test_the_probe_tells_a_real_graphical_initrd_from_the_text_one(tmp_path):
    """The whole fix rests on this one predicate, so exercise it on real
    archives rather than trusting the regex by eye."""
    if not shutil.which("cpio"):
        pytest.skip("cpio is not installed on this runner")

    text = _initrd(tmp_path, "text-initrd.gz", [
        "preseed.cfg", "sbin/debian-installer", "lib/debian-installer/exit"])
    gtk = _initrd(tmp_path, "gtk-initrd.gz", [
        "preseed.cfg", "sbin/debian-installer",
        "usr/share/graphics/logo_installer.png",
        "etc/gtk-2.0/gtkrc"])

    assert not _probe(text), (
        "the probe accepted the TEXT initrd as graphical — this is the exact "
        "copy the branding hook leaves at install/gtk/initrd.gz, so the gate "
        "would pass on an ISO that boots newt")
    assert _probe(gtk), (
        "the probe rejected a REAL graphical initrd, which would fail the "
        "build on a correct ISO")


def test_the_gate_refuses_a_fabricated_gtk_initrd():
    """And the gate has to ACT on the probe, on the arch that has a graphical
    installer to find."""
    s = _read(BUILD_SH)
    m = re.search(r"THE GRAPHICAL INSTALLER IS REAL.{0,2600}?gate_fail=1", s, re.S)
    assert m, ("build.sh has no gate that fails the build on a fabricated "
               "install/gtk/initrd.gz")
    block = m.group(0)
    assert "amd64" in block, "the gate must not fail arm64, which has no graphical installer"
    assert "cpio" in block, "the gate must look inside the initrd"
