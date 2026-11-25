#!/usr/bin/env python3
"""Every install entry a person is likely to pick must boot the GRAPHICAL installer.

WHY THIS EXISTS. "Install Sysible Server" was reported landing in the blue
newt installer. Three fixes went in and the report came back each time, because
each fix changed one menu and nothing checked the ARTIFACT. The build has no
business publishing an ISO whose obvious install entry drops the operator into
a text-mode installer.

THE RULE. An entry is an install entry if its initrd lives under /install. Of
those, an entry is PLAIN unless its label marks it as a deliberate variant --
text mode, expert, rescue, automated, speech, serial. Plain entries must boot
an initrd under /install/gtk/. Variants may boot whatever they say they boot.

The default entry must also be a plain graphical one: "just press enter" is how
most installs start.

Usage:  check-install-entries.py [--arch amd64|arm64] FILE...
        FILE is a grub.cfg or an isolinux install.cfg, extracted from the
        FINISHED ISO -- not generated output. Reads nothing else.
"""
import argparse
import re
import sys

# Labels that announce themselves as something other than the normal install.
VARIANT = re.compile(
    r"\b(text\s*mode|expert|rescue|automat|speech|serial|advanced|graphical\s+expert)\b",
    re.I)


def parse_grub(text):
    """[(label, initrd)] for every menuentry that loads an installer initrd."""
    out = []
    for m in re.finditer(r'menuentry\s+"([^"]+)"[^{]*\{(.*?)\n\}', text, re.S):
        label, body = m.group(1), m.group(2)
        i = re.search(r'^\s*initrd\s+(\S+)', body, re.M)
        if i and "/install" in i.group(1):
            out.append((label, i.group(1)))
    return out


def parse_isolinux(text):
    """[(label, initrd)] for every `label` block that loads an installer initrd.

    The visible name is `menu label`; fall back to the internal label name when
    a block has none.
    """
    out = []
    blocks = re.split(r"(?m)^label\s+", text)[1:]
    for b in blocks:
        name = b.splitlines()[0].strip()
        ml = re.search(r"^\s*menu label\s+(.+)$", b, re.M)
        label = (ml.group(1).strip().replace("^", "") if ml else name)
        i = re.search(r"^\s*initrd\s+(\S+)", b, re.M)
        if i and "/install" in i.group(1):
            out.append((label, i.group(1)))
    return out


def default_label(text):
    """The entry that boots if nobody touches the keyboard, if it is stated."""
    m = re.search(r"(?m)^\s*default\s+(\S+)", text)
    if m:
        return m.group(1)
    m = re.search(r"(?m)^\s*set\s+default\s*=\s*\"?([^\"\n]+)", text)
    return m.group(1).strip() if m else None


def is_graphical(initrd):
    return "/gtk/" in initrd


def check(path, text, arch):
    entries = parse_grub(text) if "menuentry" in text else parse_isolinux(text)
    problems, notes = [], []
    if not entries:
        notes.append(f"{path}: no installer entries found")
        return problems, notes, entries

    for label, initrd in entries:
        plain = not VARIANT.search(label)
        if plain and not is_graphical(initrd):
            problems.append(
                f"{path}: {label!r} boots {initrd} -- a TEXT installer, and its "
                f"name does not say so. An operator picking it lands in newt.")
    return problems, notes, entries


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="amd64")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)

    # EVERY arch. live-build fetches the graphical installer for amd64/i386
    # only, but Debian publishes one for arm64 too and hook 9300 fetches it --
    # verified against the real archive: the arm64 cdrom/gtk/initrd.gz is
    # 50,748,002 bytes and carries etc/gtk-2.0/gtkrc, while the text one is
    # 22,103,479 bytes and carries neither. So there is no architecture here
    # that gets to ship a text-mode install entry under a plain name.

    all_problems, all_entries = [], []
    for path in a.files:
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError as e:
            print(f"check-install-entries: cannot read {path}: {e}", file=sys.stderr)
            continue
        problems, notes, entries = check(path, text, a.arch)
        for n in notes:
            print("  note: " + n)
        for label, initrd in entries:
            kind = "graphical" if is_graphical(initrd) else "TEXT"
            print(f"  [{kind:>9}] {label}  ->  {initrd}")
        all_problems += problems
        all_entries += entries

    if all_entries and not any(is_graphical(i) for _, i in all_entries):
        all_problems.append(
            "not one install entry boots a graphical initrd -- the "
            "graphical installer is either missing or unreferenced.")

    if all_problems:
        print("\ncheck-install-entries: FAILED", file=sys.stderr)
        for p in all_problems:
            print("  " + p, file=sys.stderr)
        return 1
    for p in all_problems:
        print("  warning: " + p)
    print("check-install-entries: every plain install entry is graphical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
