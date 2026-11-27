"""The installer must ASK which software to set up — and it stopped asking.

Reported, twice: "Sysible server didn't prompt me or ask if I wanted to install
slop, terraform, nothing!" The install then came up with the platform starting
anyway, because the question's DEFAULT was taken without the question ever
being shown.

Four separate pieces have to line up for the prompt to appear, and a blanket
revert (836cf3b) dropped three of them while leaving the fourth in place, so
each file looked internally reasonable and the chain was broken end to end:

  1. build.sh exports SYSIBLE_ASK_TOOLS / SYSIBLE_ASK_TEMPLATES
  2. hook 9400 copies both INTO every installer initrd
  3. preseed's early_command looks for the script at the initrd root FIRST
  4. the script looks for its templates at the initrd root FIRST

Why the initrd root and not /cdrom: the preseed is auto-loaded from the initrd,
and preseed/early_command fires the moment that read happens -- before
cdrom-detect has mounted any media. A script referenced as
/cdrom/sysible-ask-tools is therefore unreachable at exactly the moment it is
invoked. The `|| true` that keeps an optional prompt from failing an install
then swallows the miss, so nothing anywhere reports it: no question, no error,
and an installed machine that quietly took the defaults.

These run the real hook and read the real files, because every one of those
three pieces was individually plausible on inspection.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "live-build/config/hooks/normal/9400-sysible-installer-branding.hook.binary"
BUILD = ROOT / "live-build/build.sh"
PRESEED = ROOT / "live-build/config/includes.binary/preseed.cfg"
ASK = ROOT / "live-build/config/includes.binary/sysible-ask-tools"
ASK_HOOK = ROOT / "live-build/config/includes.binary/sysible-ask-hook"
TEMPLATES = ROOT / "live-build/config/includes.binary/sysible-tools.templates"


def _code(p):
    return "\n".join(
        l for l in p.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#")
    )


# ---- 1. the build must hand the hook the files it injects -----------------
@pytest.mark.parametrize("var", ["SYSIBLE_ASK_TOOLS", "SYSIBLE_ASK_TEMPLATES"])
def test_the_build_exports_what_the_hook_injects(var):
    code = _code(BUILD)
    assert re.search(rf"^export {var}=", code, re.M), (
        f"build.sh does not export {var}, so hook 9400 sees it unset and skips "
        f"the injection silently -- it is written to never fail a build. The "
        f"installer then has no script to run and asks nothing."
    )


# ---- 2. the hook must actually put them in the initrd ---------------------
@pytest.mark.skipif(shutil.which("cpio") is None, reason="cpio needed to build a test initrd")
def test_the_hook_puts_the_question_script_in_the_initrd(tmp_path):
    """RUN it. Every earlier version of this check read the source instead."""
    iso = tmp_path / "iso" / "install"
    iso.mkdir(parents=True)
    src = tmp_path / "src"
    (src / "sbin").mkdir(parents=True)
    (src / "sbin" / "debian-installer").write_text("#!/bin/sh\n")
    subprocess.run(
        f"cd {src} && find . | cpio -o -H newc --quiet | gzip -9 > {iso}/initrd.gz",
        shell=True, check=True,
    )

    preseed = tmp_path / "p.cfg"; preseed.write_text("d-i x\n")
    ask = tmp_path / "sysible-ask-tools"; ask.write_text("#!/bin/sh\nexit 0\n")
    tpl = tmp_path / "sysible-tools.templates"; tpl.write_text("Template: sysible/apps\n")

    r = subprocess.run(
        ["sh", str(HOOK)], cwd=tmp_path / "iso", capture_output=True, text=True,
        env={**os.environ, "SYSIBLE_PRESEED": str(preseed),
             "SYSIBLE_ASK_TOOLS": str(ask), "SYSIBLE_ASK_TEMPLATES": str(tpl)},
    )
    assert r.returncode == 0, r.stderr

    out = tmp_path / "out"; out.mkdir()
    subprocess.run(
        f"cd {out} && gzip -dc {iso}/initrd.gz | cpio -idm --quiet", shell=True, check=True
    )
    assert (out / "preseed.cfg").is_file(), "no preseed reached the initrd\n" + r.stdout[-600:]
    script = out / "sysible-ask-tools"
    assert script.is_file(), (
        "the question script is NOT in the initrd. preseed/early_command runs "
        "before any media is mounted, so a copy that exists only on the ISO "
        "root cannot be opened when it is called -- the prompt never appears "
        "and `|| true` hides it.\nhook said:\n" + r.stdout[-600:]
    )
    assert os.access(script, os.X_OK), "the question script is not executable"
    assert (out / "sysible-tools.templates").is_file(), (
        "the templates are NOT in the initrd, so debconf-loadtemplate loads "
        "nothing and db_input has no question to show -- which looks exactly "
        "like never being asked"
    )


# ---- 3. the ask must NOT run from early_command any more ------------------
def test_early_command_no_longer_asks():
    """preseed/early_command is S33 of d-i's STARTUP chain. The frontend is not
    chosen until S60 of the NEXT chain and X is not started for it until S62, so
    at S33 the only frontend that exists is cdebconf's compiled-in default --
    /etc/cdebconf.conf, `driver "newt"`. A question asked there is drawn in
    stock-blue newt EVERY time, on every boot entry, BIOS or UEFI, whatever
    vga= or gfxpayload say. Confirmed by booting the released v1.0.10 ISO.

    So early_command must not be where this is asked. If it comes back here,
    the question silently stops being part of the graphical install again."""
    line = re.search(r"^d-i preseed/early_command string (.+)$", _code(PRESEED), re.M)
    cmd = line.group(1) if line else ""
    assert "sysible-ask-tools" not in cmd, (
        "the optional-software question is being asked from preseed/early_command "
        "again. That runs before any frontend exists, so it can only ever be drawn "
        "in newt. It belongs in /lib/debian-installer.d/S66sysible-ask.\n  " + cmd
    )


def test_the_ask_runs_after_the_frontend_and_after_x():
    """/sbin/debian-installer sources /lib/debian-installer.d/S[0-9][0-9]* in
    order. S60frontend chooses the frontend; S62Xorg starts X for gtk; S70menu
    opens the main menu. Ours has to land strictly between X starting and the
    menu, or it is drawn by a frontend that is not up yet -- or not at all."""
    import re as _re
    m = _re.search(r'/lib/debian-installer\.d/(S(\d\d)[A-Za-z0-9_-]+)', _code(HOOK))
    assert m, "hook 9400 no longer installs anything into /lib/debian-installer.d/"
    name, num = m.group(1), int(m.group(2))
    assert 62 < num < 70, (
        f"{name} runs at S{num:02d}. S60frontend picks the frontend and S62Xorg "
        f"starts X for it; S70menu opens the main menu. Outside (62, 70) the "
        f"question is either drawn before its frontend exists or after the menu."
    )


def test_the_ask_hook_cannot_fail_an_install():
    """/sbin/debian-installer runs `set -e` and SOURCES each script. The asker
    ends in `exit 0`, so sourcing it would exit the installer itself, and any
    non-zero would abort the install outright. It must be RUN as a subprocess,
    with the failure swallowed."""
    code = _code(ASK_HOOK)
    assert re.search(r'\bsh\s+"\$_?f"\s*\|\|\s*true', code), (
        "the hook does not run the asker as `sh ... || true`; a debconf hiccup "
        "would abort the install")
    assert not re.search(r'^\s*\.\s+["\$/]', code, re.M), (
        "the hook SOURCES the asker; its `exit 0` would exit the installer")
    assert code.strip().splitlines()[-1].strip() == "true", (
        "the hook does not end in `true`, so its last command's status leaks "
        "into the `set -e` caller")


# ---- 4. the script must look there first too ------------------------------
def test_the_script_loads_its_templates_from_the_initrd_root_first():
    code = _code(ASK)
    m = re.search(r"for T in ([^;]+); do", code)
    assert m, "the script no longer searches a list of template paths"
    paths = m.group(1).split()
    assert paths[0] == "/sysible-tools.templates", (
        f"the first template path tried is {paths[0]!r}, not the initrd root. "
        f"At early_command time that is the only one that exists."
    )


# ---- 5. and it must ask, not quietly accept a default ---------------------
@pytest.mark.parametrize("question", ["sysible/tools", "sysible/apps"])
def test_the_question_is_asked_even_if_debconf_thinks_it_was_seen(question):
    """A seen question displays nothing and db_get returns the default.

    From the outside that is identical to never being asked: no prompt, and an
    installed machine that behaves as though the operator chose the default.
    """
    code = _code(ASK)
    fset = code.find(f"db_fset {question} seen false")
    inp = code.find(f"db_input critical {question}")
    assert fset != -1, (
        f"nothing resets the seen flag for {question}, so db_input can return 30, "
        f"display nothing, and let db_get hand back the template default"
    )
    assert inp != -1, f"{question} is never put to the operator"
    assert fset < inp, f"the seen flag for {question} is reset after the question, too late"


def test_both_questions_are_still_checklists():
    """Multi-select, so picks are not mutually exclusive."""
    body = TEMPLATES.read_text(encoding="utf-8")
    for q in ("sysible/tools", "sysible/apps"):
        block = re.search(rf"Template: {re.escape(q)}\n(.*?)(?=\nTemplate:|\Z)", body, re.S)
        assert block, f"{q} is gone from the templates"
        assert re.search(r"^Type: multiselect", block.group(1), re.M), (
            f"{q} is no longer a checklist"
        )


# ---------------------------------------------------------------------------
# A question that was never put to anyone has no answer.
#
# db_input returns 30 when debconf SKIPS a question -- below the priority
# threshold, already seen, or a noninteractive frontend. Nothing is displayed,
# and db_get then returns the TEMPLATE DEFAULT. Recording that default installs
# software the operator was never offered.
#
# That is what shipped: "didn't prompt me or ask if I wanted to install slop,
# terraform, nothing!" -- on a machine that then started bringing the whole
# platform up by itself, because `slop` is the default and nobody chose it.
# ---------------------------------------------------------------------------
CONFMODULE = """db_fset() {{ return 0; }}
db_input() {{ return {rc}; }}
db_go()    {{ return 0; }}
db_get()   {{ RET="{answer}"; return 0; }}
"""


def _run_ask(tmp_path, *, rc, answer):
    """Run the real script against a stub debconf; return (apps, tools, log)."""
    sb = tmp_path
    (sb / "usr/share/debconf").mkdir(parents=True)
    (sb / "usr/share/debconf/confmodule").write_text(CONFMODULE.format(rc=rc, answer=answer))
    binp = sb / "bin"; binp.mkdir()
    lt = binp / "debconf-loadtemplate"
    lt.write_text("#!/bin/sh\nexit 0\n"); lt.chmod(0o755)
    shutil.copy(TEMPLATES, sb / "sysible-tools.templates")

    src = ASK.read_text()
    src = (src.replace("/usr/share/debconf/confmodule", str(sb / "usr/share/debconf/confmodule"))
              .replace("ASKLOG=/tmp/sysible-ask.log", f"ASKLOG={sb}/ask.log")
              .replace("/tmp/sysible-", f"{sb}/sysible-")
              .replace(" /sysible-tools.templates ", f" {sb}/sysible-tools.templates "))
    run = sb / "run.sh"; run.write_text(src)
    p = subprocess.run(["sh", str(run)], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{binp}:{os.environ['PATH']}"})
    assert p.returncode == 0, f"the script must never fail an install: {p.stderr}"

    def _read(n):
        f = sb / f"sysible-{n}.wanted"
        return f.read_text().strip() if f.is_file() else ""
    log = (sb / "ask.log").read_text() if (sb / "ask.log").is_file() else ""
    return _read("apps"), _read("tools"), log


def test_a_question_that_was_never_shown_records_nothing(tmp_path):
    apps, tools, log = _run_ask(
        tmp_path, rc=30, answer="slop (one gateway in front of all three)")
    assert apps == "", (
        "the template default was recorded for a question debconf never "
        "displayed, so the first boot installs software the operator was never "
        "offered — exactly what was reported\n\n" + log
    )
    assert tools == ""
    assert "NOT shown" in log, "nothing recorded WHY the question did not appear\n\n" + log


def test_an_answered_question_is_recorded(tmp_path):
    apps, _, log = _run_ask(
        tmp_path, rc=0, answer="controller (fleet console), slep (infra automation)")
    assert apps == "controller slep", (
        "a real answer was lost or mangled — this is the path that must keep "
        "working\n\n" + log
    )


def test_slop_collapses_the_other_picks(tmp_path):
    """slop already runs all three; installing them again would collide."""
    apps, _, _ = _run_ask(
        tmp_path, rc=0,
        answer="slop (one gateway in front of all three), connect (browser terminal)")
    assert apps == "slop"


def test_the_script_leaves_a_log_that_says_what_happened(tmp_path):
    _, _, log = _run_ask(tmp_path, rc=30, answer="slop (one gateway in front of all three)")
    for expected in ("sysible-ask-tools:", "templates:", "apps:"):
        assert expected in log, (
            f"the breadcrumb has no {expected!r} line. Every call in this script "
            f"is deliberately non-fatal, so without the log a failure leaves no "
            f"trace at all — which is what made this take two days\n\n" + log
        )
