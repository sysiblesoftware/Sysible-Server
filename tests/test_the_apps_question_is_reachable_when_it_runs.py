"""The apps question must be where early_command can reach it: the initrd.

Reported twice -- "I got fairly far in the install process and did not see a
menu to install slop, slep or controller", then "I still didn't see a menu to
install SLOP or slep". The question existed, the templates existed, every
static assertion about them passed, and it was never asked.

The chain:

  * hook 9400 puts preseed.cfg at the ROOT OF THE INSTALLER INITRD, because d-i
    auto-loads it from there with no kernel argument. Its own comment says so.
  * preseed/early_command runs as soon as that preseed is read -- before
    cdrom-detect has mounted any media.
  * the early_command was `sh /cdrom/sysible-ask-tools`, and the script loaded
    its templates from /cdrom too. Neither file was in the initrd; they shipped
    only on the ISO root, which is reached THROUGH that not-yet-existing mount.
  * so sh exited "can't open", the deliberate `|| true` swallowed it exactly as
    designed, and nothing anywhere said the prompt had gone missing.

Every existing test on this feature read the script's TEXT. None asked whether
the file could be opened at the moment it is run, which is the only thing that
turned out to matter. So this file packs a real initrd, runs the hook over it,
and unpacks it again.
"""
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / "live-build" / "build.sh"
HOOK = ROOT / "live-build/config/hooks/normal/9400-sysible-installer-branding.hook.binary"
BIN = ROOT / "live-build" / "config" / "includes.binary"
PRESEED = BIN / "preseed.cfg"
ASK = BIN / "sysible-ask-tools"
TEMPLATES = BIN / "sysible-tools.templates"

NEEDED = ("preseed.cfg", "sysible-ask-tools", "sysible-tools.templates")


@pytest.fixture()
def staged(tmp_path):
    """A binary/ tree holding one gzipped cpio initrd, as live-build leaves it."""
    if not shutil.which("cpio"):
        pytest.skip("cpio not available")
    src = tmp_path / "initrd-src"
    (src / "usr" / "share" / "graphics").mkdir(parents=True)
    (src / "etc").mkdir()
    (src / "etc" / "placeholder").write_text("x\n")
    stage = tmp_path / "binary" / "install"
    stage.mkdir(parents=True)
    initrd = stage / "initrd.gz"
    listing = subprocess.run(["sh", "-c", "find . | cpio -o -H newc --quiet | gzip -9"],
                             cwd=src, capture_output=True, timeout=120)
    assert listing.returncode == 0, listing.stderr
    initrd.write_bytes(listing.stdout)
    return tmp_path / "binary", initrd


def _run_hook(binary_dir):
    env = {
        **os.environ,
        "SYSIBLE_PRESEED": str(PRESEED),
        "SYSIBLE_ASK_TOOLS": str(ASK),
        "SYSIBLE_ASK_TEMPLATES": str(TEMPLATES),
        "SYSIBLE_INSTALLER_BANNER": "",
    }
    return subprocess.run(["sh", str(HOOK)], cwd=binary_dir, env=env,
                          capture_output=True, text=True, timeout=600)


def _initrd_contents(initrd):
    r = subprocess.run(["sh", "-c", f"gzip -dc {initrd!s} | cpio -t --quiet"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return {l.lstrip("./") for l in r.stdout.split()}


def test_the_hook_puts_the_question_in_the_initrd_with_the_preseed(staged):
    """The fix, exercised rather than read. Pack an initrd, run the real hook
    over it, unpack it: all three files must be at the root, because that is
    the only place early_command can open them."""
    binary_dir, initrd = staged
    r = _run_hook(binary_dir)
    assert r.returncode == 0, f"hook failed: {r.stdout}\n{r.stderr}"
    names = _initrd_contents(initrd)
    missing = [n for n in NEEDED if n not in names]
    assert not missing, f"not in the initrd: {missing}; it holds {sorted(names)}"


def test_the_script_in_the_initrd_is_executable(staged):
    binary_dir, initrd = staged
    assert _run_hook(binary_dir).returncode == 0
    r = subprocess.run(["sh", "-c", f"gzip -dc {initrd!s} | cpio -tv --quiet"],
                       capture_output=True, text=True, timeout=120)
    line = [l for l in r.stdout.splitlines() if l.endswith("sysible-ask-tools")]
    assert line, r.stdout
    assert "x" in line[0].split()[0], f"not executable in the initrd: {line[0]}"


def test_early_command_looks_in_the_initrd_first():
    """/cdrom is not mounted when this runs. If the initrd copy is not tried
    FIRST the fix is inert -- the fallbacks are for an hd-media install."""
    line = [l for l in PRESEED.read_text().splitlines()
            if l.startswith("d-i preseed/early_command")]
    assert line, "there is no early_command"
    cmd = line[0]
    assert "/sysible-ask-tools" in cmd, cmd
    i, j = cmd.index("/sysible-ask-tools"), cmd.index("/cdrom/sysible-ask-tools")
    assert i < j, f"the initrd copy is not tried before /cdrom: {cmd}"


def test_the_templates_are_looked_for_in_the_initrd_first():
    """debconf-loadtemplate on a missing file loads nothing and says nothing;
    db_input then has no template to show, which looks exactly like a question
    that was never asked."""
    line = [l for l in ASK.read_text().splitlines() if l.startswith("for T in")]
    assert line, "the template search loop is gone"
    paths = line[0].split()[3:]
    assert paths[0] == "/sysible-tools.templates", f"search order is {paths}"
    assert any(p.startswith("/cdrom/") for p in paths), f"no hd-media fallback: {paths}"


def test_the_early_command_still_cannot_fail_the_install():
    """An OPTIONAL prompt must never abort an otherwise-good install with
    "Failed to run preseeded command"."""
    cmd = [l for l in PRESEED.read_text().splitlines()
           if l.startswith("d-i preseed/early_command")][0]
    assert cmd.rstrip().endswith("|| true"), cmd


def test_the_build_refuses_an_iso_whose_initrd_lacks_them():
    """The miss was invisible precisely because `|| true` is correct. So the
    BUILD has to be what notices, the way it already does for the preseed."""
    b = BUILD.read_text()
    code = "\n".join(l for l in b.splitlines() if not l.lstrip().startswith("#"))
    for need in ("sysible-ask-tools", "sysible-tools.templates"):
        assert need in code, f"the build never checks the initrd for {need}"
    assert "would never ask which apps to set up" in b, \
        "the gate does not fail the build with a named reason"


def test_build_sh_hands_the_hook_both_payloads():
    code = "\n".join(l for l in BUILD.read_text().splitlines()
                     if not l.lstrip().startswith("#"))
    for var in ("SYSIBLE_ASK_TOOLS", "SYSIBLE_ASK_TEMPLATES"):
        assert f"export {var}=" in code, f"build.sh never exports {var}"


def test_they_still_ship_on_the_iso_root_too():
    """An hd-media install finds the ISO-root copy, not the initrd one."""
    for f in (ASK, TEMPLATES, PRESEED):
        assert f.is_file(), f"{f.name} no longer ships in includes.binary/"
