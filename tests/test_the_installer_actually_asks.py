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


# ---- 3. the preseed must look there first ---------------------------------
def test_the_early_command_tries_the_initrd_root_first():
    line = re.search(r"^d-i preseed/early_command string (.+)$", _code(PRESEED), re.M)
    assert line, "the preseed no longer runs anything at early_command"
    cmd = line.group(1)
    assert "/sysible-ask-tools" in cmd, "early_command does not reference the script at all"
    first = cmd.index("/sysible-ask-tools")
    cdrom = cmd.find("/cdrom/sysible-ask-tools")
    assert cdrom == -1 or first < cdrom, (
        f"early_command reaches for /cdrom before the initrd root. Nothing is "
        f"mounted at /cdrom when this fires, so the prompt is skipped silently:\n  {cmd}"
    )


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
