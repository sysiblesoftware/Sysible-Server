"""The install asks which Sysible apps to set up, and says so when it cannot.

    "on install it should ask to install slop"

It never did. The apps were installed only by running `install-sysible` AFTER
the install had finished — and on a headless server nothing tells you that
exists. The optional TOOLS already had this exact machinery (ask during the
install, record the answer, let the first networked boot do the work); the apps,
which are the product, did not.

The first-boot half is deliberately NOT a copy of the tools one. That script
ends with an unconditional `rm -f` of its request, commented "even if a download
failed, we don't want to retry on every boot" — so a transient DNS blip at first
boot costs you what you asked for, permanently and silently. That was reported
too, in the same session, by someone whose DNS could not reach Docker Hub.
"""
import os
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
LB = REPO / "live-build" / "config"
ASK = LB / "includes.binary" / "sysible-ask-tools"
TEMPLATES = LB / "includes.binary" / "sysible-tools.templates"
PRESEED = LB / "includes.binary" / "preseed.cfg"
HOOK = LB / "hooks" / "normal" / "9600-sysible-firstboot.hook.chroot"
FIRSTBOOT = LB / "includes.chroot" / "usr" / "lib" / "sysible" / "install-selected-apps"
UNIT = LB / "includes.chroot" / "usr" / "lib" / "systemd" / "system" / "sysible-apps-firstboot.service"
HINT = LB / "includes.chroot" / "usr" / "local" / "bin" / "sysible-hint"
SH = shutil.which("sh")


# ---- it is actually asked ---------------------------------------------------
def test_the_installer_asks_which_apps_to_set_up():
    t = TEMPLATES.read_text(encoding="utf-8")
    assert "Template: sysible/apps" in t, "there is no question to ask"
    assert "slop" in t, "the gateway is not offered"
    block = t[t.index("Template: sysible/apps"):]
    assert "Default: slop" in block, \
        "the thing that was asked for is not the default answer"
    # DECLINING. There used to be a literal "none" choice, because this was a
    # single-choice list and declining needed somewhere to click. It is a
    # checklist now -- reported as "it was all or nothing" -- so declining is
    # ticking nothing, and a "none" box sitting among real ones would be a
    # second way to say the same thing. The way to decline must still EXIST,
    # which for a multiselect means the empty answer is handled.
    assert "Type: multiselect" in block or "none" in block, \
        "there is no way to decline"
    ask = ASK.read_text(encoding="utf-8")
    assert "''|none)" in ask, "an empty selection is not handled as 'install nothing'"


def test_the_question_is_put_during_the_install():
    s = ASK.read_text(encoding="utf-8")
    assert "db_input critical sysible/apps" in s, "the question is never shown"
    assert "/tmp/sysible-apps.wanted" in s, "the answer is not recorded"


def test_declining_records_nothing_to_do():
    """'none' must not reach install-sysible as a product name."""
    s = ASK.read_text(encoding="utf-8")
    body = s[s.index("db_get sysible/apps"):]
    assert "''|none)" in body, "'none' is not special-cased"


def test_the_answer_reaches_the_installed_system():
    s = PRESEED.read_text(encoding="utf-8")
    assert "cp /tmp/sysible-apps.wanted /target/etc/sysible/apps.wanted" in s, \
        "the answer is left in the installer's ramdisk and lost at reboot"


def test_the_first_boot_unit_is_enabled_in_the_image():
    h = HOOK.read_text(encoding="utf-8")
    assert "systemctl enable sysible-apps-firstboot.service" in h, \
        "the unit ships but is never enabled, so it never runs"
    u = UNIT.read_text(encoding="utf-8")
    assert "ConditionPathExists=/etc/sysible/apps.wanted" in u
    assert "After=network-online.target" in u, \
        "it would run before the network it needs to clone and pull"
    assert "TimeoutStartSec=0" in u, \
        "cloning four repos and building containers will exceed the default timeout"


# ---- the first-boot run, EXECUTED -------------------------------------------
@pytest.fixture()
def firstboot(tmp_path):
    """Run install-selected-apps against a fake install-sysible, with every
    path redirected into tmp_path."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "etc" / "sysible").mkdir(parents=True)
    (tmp_path / "var" / "lib" / "sysible").mkdir(parents=True)
    (tmp_path / "var" / "log").mkdir(parents=True)
    calls = tmp_path / "calls"
    (tmp_path / "bin" / "install-sysible").write_text(
        '#!/bin/sh\necho "install-sysible $*" >> "$CALLS"\n'
        '[ "$FAKE_OK" = 1 ] && exit 0\necho "fake failure" >&2; exit 1\n')
    (tmp_path / "bin" / "install-sysible").chmod(0o755)
    script = FIRSTBOOT.read_text(encoding="utf-8")
    for a, b in (
        ("/etc/sysible/apps.wanted", f"{tmp_path}/etc/sysible/apps.wanted"),
        ("/var/lib/sysible/apps-firstboot.tries", f"{tmp_path}/var/lib/sysible/tries"),
        ("/var/log/sysible-apps-firstboot.log", f"{tmp_path}/var/log/fb.log"),
        ("/etc/sysible/apps-failed", f"{tmp_path}/etc/sysible/apps-failed"),
        ("mkdir -p /etc/sysible", f"mkdir -p {tmp_path}/etc/sysible"),
    ):
        script = script.replace(a, b)
    run_sh = tmp_path / "run.sh"
    run_sh.write_text(script)

    class R:
        want = tmp_path / "etc" / "sysible" / "apps.wanted"
        failed = tmp_path / "etc" / "sysible" / "apps-failed"
        log = tmp_path / "var" / "log" / "fb.log"

        def run(self, ok):
            env = {**os.environ, "PATH": f"{tmp_path}/bin:{os.environ['PATH']}",
                   "CALLS": str(calls), "FAKE_OK": "1" if ok else "0"}
            subprocess.run([SH, str(run_sh)], env=env, timeout=60,
                           capture_output=True, text=True)

        def calls(self):
            return [l for l in (calls.read_text().splitlines() if calls.exists() else []) if l.strip()]
    return R()


pytestmark = pytest.mark.skipif(not SH, reason="no sh on this machine")


def test_it_installs_what_was_chosen(firstboot):
    firstboot.want.write_text("slop\n")
    firstboot.run(ok=True)
    # -y: a first boot has no terminal and nobody watching it.
    assert firstboot.calls() == ["install-sysible -y slop"]
    assert not firstboot.want.exists(), "a successful run must not repeat next boot"


def test_declining_runs_nothing(firstboot):
    firstboot.want.write_text("none\n")
    firstboot.run(ok=True)
    assert firstboot.calls() == [], "'none' was handed to install-sysible as a product"


def test_a_failure_is_retried_rather_than_silently_discarded(firstboot):
    """THE difference from install-selected-tools. One bad boot must not cost
    the operator the thing they asked for."""
    firstboot.want.write_text("slop\n")
    firstboot.run(ok=False)
    assert firstboot.want.exists(), \
        "the request was thrown away on the first failure — exactly the reported bug"
    firstboot.run(ok=True)
    assert len(firstboot.calls()) == 2, "it did not retry on the next boot"
    assert not firstboot.want.exists()


def test_it_gives_up_eventually_and_leaves_something_that_speaks(firstboot):
    """Giving up is allowed. Giving up quietly is not."""
    firstboot.want.write_text("slop\n")
    for _ in range(5):
        firstboot.run(ok=False)
    assert len(firstboot.calls()) == 3, \
        f"retried forever instead of stopping: {firstboot.calls()}"
    assert not firstboot.want.exists(), "it never stops trying"
    assert firstboot.failed.read_text().strip() == "slop", \
        "it gave up with nothing to show for it"


def test_the_log_says_which_attempt_it_was(firstboot):
    firstboot.want.write_text("slop\n")
    firstboot.run(ok=False)
    assert "attempt 1 of 3" in firstboot.log.read_text()


# ---- and the machine says so at login ---------------------------------------
def test_login_says_the_setup_is_pending_or_failed():
    h = HINT.read_text(encoding="utf-8")
    assert '"$ETC/apps.wanted"' in h, "a pending setup is invisible at login"
    assert '"$ETC/apps-failed"' in h, "a failed setup is invisible at login"
    assert "sysible-apps-firstboot.log" in h, "it does not point at the reason"
