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

# 2. Relabel. Order matters: match the graphical label FIRST, otherwise the
#    plain-install pattern also matches "Graphical install" and both entries end
#    up with the same name.
s = re.sub(r'(menu label\s+)\^?Graphical install.*',
           r'\1Install Sysible Server', s)
s = re.sub(r'(menu label\s+)\^?Install\b(?!\s+Sysible).*',
           r'\1Install Sysible Server (text mode)', s)

# 3. Make the GRAPHICAL entry the default, so "just press enter" gets the dark
#    installer rather than newt.
if re.search(r'^label\s+installgui\b', s, re.M):
    if re.search(r'^default\s+', s, re.M):
        s = re.sub(r'^default\s+.*$', 'default installgui', s, count=1, flags=re.M)
    else:
        s = 'default installgui\n' + s

sys.stdout.write(s)
if s == orig:
    print("WARN: install.cfg unchanged by the rewrite", file=sys.stderr)
