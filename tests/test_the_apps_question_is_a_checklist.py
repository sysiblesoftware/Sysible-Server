"""Choosing Sysible software must be a checklist, not all-or-nothing.

Reported as: "The sysible server menu to choose the software didnt' allow me to
choose 1 or 2 options by themselves. It was all or nothing and the menu looks
bad", and then "There should be checkboxes for sysible software and it should
not have all or none".

sysible/apps was `Type: select` -- a single-choice radio list. You could pick
exactly one of slop / all / controller / slep / connect / none, so the only way
to get TWO apps was to take every app. The tools question immediately above it
in the same file is a multiselect and renders as checkboxes, which is what this
one should always have been.

Three layers had to change together, and the two behind the template were
already broken for a list before anyone could reach them:

  * ask-tools normalised the answer with `tr -d ' '` and NO `tr ',' ' '` --
    the tools branch has both. A multiselect answers "a, b, c", so this would
    have written "controller,slep": one unknown product.
  * install-selected-apps read it with `tr -d ' \\n'`, which glues
    "controller slep" into "controllerslep", and then called
    install-sysible "$sel" QUOTED, handing it one argument with a space in it.

So the template alone would not have fixed anything. These run the real scripts
rather than reading them, because that is what the last round of this bug
taught: every existing test asserted the script's text and none of them noticed
the file could not even be opened.
"""
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "live-build/config/includes.binary/sysible-tools.templates"
ASK = ROOT / "live-build/config/includes.binary/sysible-ask-tools"
FIRSTBOOT = ROOT / "live-build/config/includes.chroot/usr/lib/sysible/install-selected-apps"
SH = shutil.which("dash") or shutil.which("sh")


def _stanza(name):
    text = TEMPLATES.read_text()
    start = text.index(f"Template: {name}\n")
    nxt = text.find("\nTemplate: ", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def _field(name, field):
    for line in _stanza(name).splitlines():
        if line.startswith(f"{field}:"):
            return line.split(":", 1)[1].strip()
    return None


def _ids(name="sysible/apps"):
    """The ids the rest of the system uses.

    They live in Choices-C now. Choices carries what the OPERATOR reads -- full
    product names ("Sysible Linux Operations Platform (SLOP)") -- and db_get
    returns the C value, so the two can differ freely. Before Choices-C the id
    was the first word of the label, which only worked while every label began
    with its own id; "Sysible Linux Operations Platform (SLOP)" does not, and
    that parse silently produced "Sysible"."""
    c = _field(name, "Choices-C")
    if c is not None:
        return [x.strip() for x in c.split(",") if x.strip()]
    return [x.strip().split()[0] for x in (_field(name, "Choices") or "").split(",") if x.strip()]


def _labels(name="sysible/apps"):
    return [x.strip() for x in (_field(name, "Choices") or "").split(",") if x.strip()]


# --- the question --------------------------------------------------------

def test_the_apps_question_is_a_checklist():
    """The whole report. `select` is one-of; `multiselect` is checkboxes."""
    assert _field("sysible/apps", "Type") == "multiselect", (
        "sysible/apps is still a single-choice list, so two apps cannot be "
        "picked without picking them all")


def test_it_matches_the_tools_question_beside_it():
    """They sit in one file and are answered one after the other. One being a
    checklist and the other not is the inconsistency that was reported."""
    assert _field("sysible/tools", "Type") == _field("sysible/apps", "Type")


def test_all_and_none_are_gone():
    """A checklist expresses both already: tick everything, or tick nothing.
    Leaving them in gives two ways to say the same thing, and "all" next to
    real checkboxes is exactly the all-or-nothing framing being removed."""
    ids = _ids()
    assert "all" not in ids, ids
    assert "none" not in ids, ids
    assert {"slop", "controller", "slep", "connect"} == set(ids), ids


def test_no_choice_hides_a_comma():
    """Commas separate choices. One inside a label silently splits it in two."""
    for c in _field("sysible/apps", "Choices").split(","):
        assert "(" not in c or ")" in c, f"a comma split this label: {c!r}"


def test_the_default_is_one_of_the_choices():
    """A Default that matches nothing pre-selects nothing, silently."""
    ids = _ids()
    for d in (x.strip() for x in (_field("sysible/apps", "Default") or "").split(",") if x.strip()):
        assert d in ids, (
            f"Default {d!r} is not among {ids}. With Choices-C the Default must be "
            f"a C VALUE, not a label -- a Default that matches no id pre-selects "
            f"nothing, silently.")


def test_the_description_does_not_rely_on_alignment():
    """It used to draw a table with hand-aligned columns. debconf re-flows the
    extended description, so that collapsed into a blob -- "the menu looks
    bad". Paragraphs separated by ' .' survive; column alignment does not."""
    body = _stanza("sysible/apps").split("Description:", 1)[1]
    for line in body.splitlines():
        if line.startswith(" ") and line.strip() and line.strip() != ".":
            assert not line.startswith("   "), (
                f"this line is hand-indented and will be re-flowed: {line!r}")


# --- the answer, parsed by the real script -------------------------------

@pytest.fixture()
def ask(tmp_path):
    """Run the REAL sysible-ask-tools with debconf stubbed out."""
    stub = tmp_path / "confmodule"
    out = tmp_path / "apps.wanted"
    tools_out = tmp_path / "tools.wanted"

    def run(answer):
        stub.write_text(
            "db_input() { :; }\ndb_go() { :; }\n"
            "debconf_loadtemplate() { :; }\n"
            'db_get() { case "$1" in sysible/apps) RET="$ANSWER" ;; *) RET="" ;; esac; }\n')
        src = ASK.read_text()
        src = src.replace("/usr/share/debconf/confmodule", str(stub))
        src = src.replace("/tmp/sysible-apps.wanted", str(out))
        src = src.replace("/tmp/sysible-tools.wanted", str(tools_out))
        script = tmp_path / "ask"
        script.write_text(src)
        os.chmod(script, 0o755)
        if out.exists():
            out.unlink()
        r = subprocess.run([SH, str(script)], capture_output=True, text=True,
                           timeout=60, env={**os.environ, "ANSWER": answer})
        assert r.returncode == 0, f"the script must never fail an install: {r.stderr}"
        return out.read_text().strip() if out.exists() else ""

    return run


@pytest.mark.parametrize("answer,expected", [
    ("controller, slep", "controller slep"),
    ("controller, slep, connect", "controller slep connect"),
    ("connect", "connect"),
    ("slop", "slop"),
    ("", ""),
    # Leading/trailing space is normal in a multiselect answer.
    ("  controller ,  connect ", "controller connect"),
    # A LABEL leaking through -- Choices-C not honoured, or someone edits the
    # template and forgets it -- must be DROPPED, not forwarded. Forwarding it
    # hands install-sysible "Sysible" and it dies on an unknown product in a log
    # nobody reads. Empty-and-logged is the safe failure.
    ("Sysible Linux Operations Platform (SLOP) - one front door for all three", ""),
    ("slop, Sysible Connect - terminal in the browser", "slop"),
])
def test_a_multiselect_answer_becomes_a_product_list(ask, answer, expected):
    """db_get returns the Choices-C value, so what arrives here is the bare id."""
    assert ask(answer) == expected


def test_slop_supersedes_the_individual_apps(ask):
    """slop IS all three behind the gateway. Installing it alongside them would
    stand a second standalone copy of each next to the ones it fronts."""
    assert ask("slop, controller") == "slop"


# --- the first boot, running the real script ------------------------------

@pytest.fixture()
def firstboot(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv = tmp_path / "argv"
    (bin_dir / "install-sysible").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$#" >> "$ARGV"\nfor a in "$@"; do printf "[%s]" "$a" >> "$ARGV"; done\n'
        'printf "\\n" >> "$ARGV"\nexit "${STUB_RC:-0}"\n')
    os.chmod(bin_dir / "install-sysible", 0o755)

    def run(wanted):
        want = tmp_path / "apps.wanted"
        want.write_text(wanted + "\n")
        src = FIRSTBOOT.read_text()
        src = src.replace("WANT=/etc/sysible/apps.wanted", f"WANT={want}")
        src = src.replace("TRIES=/var/lib/sysible/apps-firstboot.tries", f"TRIES={tmp_path}/tries")
        src = src.replace("LOG=/var/log/sysible-apps-firstboot.log", f"LOG={tmp_path}/log")
        src = src.replace("/etc/sysible/apps-failed", f"{tmp_path}/failed")
        script = tmp_path / "fb"
        script.write_text(src)
        os.chmod(script, 0o755)
        if argv.exists():
            argv.unlink()
        subprocess.run([SH, str(script)], capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
                            "ARGV": str(argv)})
        return argv.read_text().strip() if argv.exists() else ""

    return run


def _products(argv):
    """The bracketed arguments the stub recorded, minus the -y flag."""
    import re
    return [a for a in re.findall(r"\[([^\]]*)\]", argv) if a != "-y"]


def test_two_apps_reach_install_sysible_as_two_arguments(firstboot):
    """`install-sysible "$sel"` passed ONE argument containing a space, which
    is not a product. This is the bug that would have survived the template
    change and still looked like the checklist not working."""
    got = firstboot("controller slep")
    assert _products(got) == ["controller", "slep"], got


def test_one_app_still_reaches_it_as_one(firstboot):
    got = firstboot("slop")
    assert _products(got) == ["slop"], got


def test_three_apps_all_arrive(firstboot):
    got = firstboot("controller slep connect")
    assert _products(got) == ["controller", "slep", "connect"], got


def test_it_does_not_wait_for_a_terminal_that_is_not_there(firstboot):
    """A first boot has nobody watching it."""
    assert "-y" in firstboot("controller"), "install-sysible may stop for input"


def test_every_choice_names_a_product_install_sysible_accepts():
    """The parser takes each choice's FIRST WORD as the product id, so a label
    may gain explanatory text freely -- but the word itself has to be real.
    `install-sysible slopp` exits with usage into a log nobody reads."""
    accepted = None
    cli = ROOT / "packages" / "sysible-cli" / "install-sysible"
    if cli.is_file():
        import re
        m = re.search(r'^PRODUCTS_ALL="([^"]+)"', cli.read_text(), re.M)
        if m:
            accepted = set(m.group(1).split())
    if accepted is None:
        pytest.skip("could not read PRODUCTS_ALL from install-sysible")
    ids = set(_ids())
    assert ids <= accepted, (
        f"the installer offers products install-sysible rejects: "
        f"{sorted(ids - accepted)}; it accepts {sorted(accepted)}")


def test_the_installer_offers_what_the_post_install_menu_offers():
    """install-sysible's own whiptail --checklist offers controller, slep,
    connect and slop as four independent ticks. The installer asked the same
    question as a one-of list. Two menus for one decision disagreeing is how
    this was reported; they match now, and must stay matched."""
    cli = ROOT / "packages" / "sysible-cli" / "install-sysible"
    if not cli.is_file():
        pytest.skip("install-sysible not in this repo")
    text = cli.read_text()
    assert "--checklist" in text, "the post-install menu is no longer a checklist"
    ids = set(_ids())
    assert ids == {"controller", "slep", "connect", "slop"}, ids


# --- it is a page a customer reads ---------------------------------------
# "These ISOs are for users and they depend on them being professional."
# The description once explained itself in terms of its own history -- what had
# been "reported", which of two menus "was wrong" -- which is a note to whoever
# was fixing it, printed full-screen to someone installing a server.
_DEV_SPEAK = (
    "reported", "was wrong", "used to be", "disagreed", "all or nothing",
    "bug", "regression", "todo", "fixme", "workaround", "as before",
)


def _descriptions():
    """Every extended description in the file the installer shows."""
    out = {}
    for stanza in TEMPLATES.read_text().split("Template: "):
        if not stanza.strip():
            continue
        name = stanza.splitlines()[0].strip()
        if "Description:" in stanza:
            out[name] = stanza.split("Description:", 1)[1]
    assert "sysible/apps" in out and "sysible/tools" in out, out.keys()
    return out


@pytest.mark.parametrize("word", _DEV_SPEAK)
def test_no_installer_page_explains_its_own_history(word):
    for name, body in _descriptions().items():
        assert word not in body.lower(), (
            f"{name} tells the operator about this project's development "
            f"({word!r}). Describe what the choice does, not why it changed.")


def test_the_installer_pages_are_plain_ascii():
    """The same file is rendered by the graphical frontend and by newt in a
    console whose font is not guaranteed to carry anything else."""
    raw = TEMPLATES.read_bytes()
    bad = [(i, b) for i, b in enumerate(raw) if b > 0x7E or (b < 0x20 and b != 0x0A)]
    assert not bad, f"non-ASCII in a page the installer prints: {bad[:5]}"


# --- the labels the operator actually reads -------------------------------

def test_the_listing_names_the_products_in_full():
    """Reported: the list said "slop" and "slep". Those are internal ids, not
    product names -- nobody outside this repo knows what "slep" is. Choices-C
    keeps the ids for the machine, so the visible list can say what the
    software IS without changing a single thing downstream."""
    labels = " | ".join(_labels())
    for want in ("Sysible Linux Operations Platform (SLOP)",
                 "Sysible Linux Engineering Platform (SLEP)",
                 "Sysible Controller",
                 "Sysible Connect"):
        assert want in labels, f"the install listing never says {want!r}:\n  {labels}"


def test_every_id_has_exactly_one_label():
    """Choices-C and Choices are matched up by POSITION. One more entry in
    either, or a stray comma inside a label, silently shifts every label onto
    the wrong id -- the operator ticks the Controller and gets Connect."""
    ids, labels = _ids(), _labels()
    assert len(ids) == len(labels), (
        f"{len(ids)} ids but {len(labels)} labels; they are paired by position, "
        f"so every one after the mismatch is attached to the wrong product.\n"
        f"  ids   : {ids}\n  labels: {labels}")


def test_no_label_hides_a_comma():
    """Commas separate entries. One inside a label splits it in two, which is
    how the counts above drift apart in the first place."""
    for lab in _labels():
        assert "(" not in lab or ")" in lab, f"a comma split this label: {lab!r}"
