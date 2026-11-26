#!/usr/bin/env python3
"""Make the isolinux (BIOS) installer entries match the GRUB (UEFI) ones.

The GRUB menu was changed so the plain "Install Sysible Server" entry boots the
GRAPHICAL Debian Installer, with the newt one demoted to "(text mode)". That
change was applied to grub.cfg ONLY. isolinux was left carrying Debian's stock
entries, where plain "Install" is the newt installer -- so a BIOS boot still
lands in the blue 1990s dialogs, which is exactly what was reported from a real
install.

Debian's CD layout ships ONE installer kernel at install/vmlinuz and only the
GTK INITRD under install/gtk/. Stock install.cfg nevertheless points its
graphical entry at /install/gtk/vmlinuz, which does not exist -- the same trap
already fixed for GRUB. Both are handled here.

Reads install.cfg on stdin, writes the rewritten file on stdout.
"""
import re
import sys

s = sys.stdin.read()
orig = s

# 1. The gtk kernel path does not exist on a Debian CD; share the one kernel.
s = re.sub(r'(/install[^/\s]*)/gtk/vmlinuz', r'\1/vmlinuz', s)

# 2. Relabel -- BY BLOCK, and only the blocks that need it.
#
# This used to be two global regexes over the whole file:
#
#     menu label ^Graphical install  ->  Install Sysible Server
#     menu label ^Install            ->  Install Sysible Server (text mode)
#
# and the second one did real damage, visible for the first time in ISO #95's
# log. The file this build receives nests FOUR entries under "Advanced install
# options" twice over -- once under "Graphical installer" and once under "Text
# installer" -- and both submenus label their first entry "^Install". So the
# GRAPHICAL one was renamed "Install Sysible Server (text mode)", and the menu
# ended up with two different entries under that identical name, one of them
# booting the graphical installer. Debian's own labels were better than what we
# replaced them with.
#
# Two shapes, told apart by whether the top-level `installstart` block exists:
#
#   * the shape this build gets. Relabel ONLY the two top-level entries, which
#     are the ones an operator sees first. The Advanced tree is already
#     self-describing -- "Graphical installer > Install", "Text installer >
#     Install" -- and is left exactly as Debian wrote it.
#   * the netinst shape, which has a flat install/installgui pair and no
#     submenus. There, naming them is the whole point.
def _relabel(text, block, label):
    """Rewrite the `menu label` of the `label <block>` stanza, if it is there."""
    pat = re.compile(
        r"(^label\s+" + re.escape(block) + r"\b.*?^\s*menu label\s+)[^\n]*",
        re.M | re.S)
    return pat.sub(lambda m: m.group(1) + label, text, count=1)


# Which shape is this? The build receives the submenu one; a netinst CD is flat.
if re.search(r"^label\s+installstart\b", s, re.M):
    s = _relabel(s, "installstart", "Install Sysible Server")
    s = _relabel(s, "installstartspeech", "Install Sysible Server (speech synthesis)")
else:
    s = _relabel(s, "installgui", "Install Sysible Server")
    s = _relabel(s, "install", "Install Sysible Server (text mode)")

relabelled = s != orig

# 3. Make the GRAPHICAL entry the default, so "just press enter" gets the dark
#    installer rather than newt.
if re.search(r'^label\s+installgui\b', s, re.M):
    if re.search(r'^default\s+', s, re.M):
        s = re.sub(r'^default\s+.*$', 'default installgui', s, count=1, flags=re.M)
    else:
        s = 'default installgui\n' + s

# Already ours is not a no-op, it is nothing left to do -- build.sh can run
# this over an extracted file more than once, and the guards check that doing
# so changes nothing.
already_ours = "Install Sysible Server" in orig

if not relabelled and not already_ours:
    # Not a warning. A silent no-op here is how the BIOS menu shipped carrying
    # Debian's own wording while this script reported success, and the only
    # reason it was ever noticed is that the build log happened to print the
    # file. If the shape changes again, say so.
    print("ERROR: install.cfg carried no label this rewrite recognises, so the "
          "BIOS menu would ship with Debian's own wording. Its labels are:",
          file=sys.stderr)
    for line in orig.splitlines():
        if "menu label" in line:
            print("    " + line.strip(), file=sys.stderr)
    sys.exit(1)

sys.stdout.write(s)
if s == orig:
    print("WARN: install.cfg unchanged by the rewrite", file=sys.stderr)
