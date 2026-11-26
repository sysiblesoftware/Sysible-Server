"""The Debian installer must not put a Sysible question in front of anyone.

There was a preseed/early_command that ran sysible-ask-tools and drew a debconf
multiselect. It was reported four times, in escalating terms, as the blue
text-mode dialogs appearing in the middle of an install.

IT WAS NOT A MISSING GRAPHICAL INSTALLER. That was fixed separately and
verified: ISO #93 and #96 both carry Debian's real gtk initrd -- 55,067,630
bytes against 22,812,306 for the text one, and hook 9400 reports branding=yes
on it, which only happens for an initrd carrying the gtk payload -- and both
the UEFI GRUB entry and the BIOS entry boot it. The question still rendered in
newt on both.

So the frontend was never the variable. preseed/early_command fires when the
preseed is READ, which is before the graphical frontend exists; db_input at
that point can only be text-mode. Shipping the right initrd cannot fix a
question asked before there is a GUI to ask it in.

Nothing was lost by removing it. Nothing offered there was installable during
the install -- no network guarantee, no package archive -- so every answer was
written to a file and acted on at first boot. That still works; the choice is
now made after the install with `sudo sysible-tools` and `install-sysible`.

These guards exist so it cannot come back by accident.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LB = ROOT / "live-build"
PRESEED = LB / "config/includes.binary/preseed.cfg"
BINARY = LB / "config/includes.binary"
BUILD = LB / "build.sh"
BRANDING = LB / "config/hooks/normal/9400-sysible-installer-branding.hook.binary"


def _live(path):
    """The file with comment lines stripped, so a comment ABOUT the removal
    does not read as the thing itself."""
    return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                     if not l.lstrip().startswith("#"))


def test_the_preseed_runs_no_command_of_ours():
    live = _live(PRESEED)
    assert "early_command" not in live, (
        "preseed/early_command is back. It fires before the graphical frontend "
        "exists, so anything it asks is a newt dialog:\n" + live)


def test_the_question_is_not_on_the_iso_at_all():
    for name in ("sysible-ask-tools", "sysible-tools.templates"):
        assert not (BINARY / name).exists(), (
            f"{name} is back in the binary includes; hook 9400 would put it in "
            f"the initrd and something would run it")


def test_the_build_does_not_ship_the_question():
    src = BUILD.read_text(encoding="utf-8")
    for var in ("SYSIBLE_ASK_TOOLS", "SYSIBLE_ASK_TEMPLATES"):
        assert var not in src, f"build.sh still exports {var}"


def test_the_branding_hook_does_not_inject_it():
    live = _live(BRANDING)
    for frag in ("ASK_TOOLS", "ASK_TEMPLATES", "sysible-ask-tools"):
        assert frag not in live, (
            f"the branding hook still handles {frag}, so the question would be "
            f"placed in the installer initrd")


def test_the_preseed_does_not_carry_answers_into_the_target():
    live = _live(PRESEED)
    assert "tools.wanted" not in live and "apps.wanted" not in live, (
        "late_command still copies an answer file the installer no longer "
        "produces")


@pytest.mark.parametrize("tool,why", [
    ("sysible-tools", "the optional/licensed tools"),
    ("install-sysible", "the Sysible apps"),
])
def test_the_post_install_route_still_exists(tool, why):
    """Removing the question is only acceptable because this is how the choice
    is made instead. If it goes, the software becomes unreachable."""
    hits = list(ROOT.rglob(tool))
    hits = [h for h in hits if ".git" not in h.parts and "__pycache__" not in h.parts]
    assert hits, f"{tool} is gone, and it is the only way to choose {why}"


def test_the_first_boot_units_still_honour_an_existing_file():
    """An image built before the removal may have written one. It must still be
    acted on rather than ignored."""
    unit = LB / "config/includes.chroot/usr/lib/systemd/system/sysible-tools-firstboot.service"
    assert unit.is_file(), "the first-boot unit was removed along with the question"
    assert "ConditionPathExists" in unit.read_text(encoding="utf-8"), (
        "without the condition this unit runs on every boot with nothing to do")
