#!/usr/bin/env python3
"""Generate a Sysible-palette folder icon set that matches the Files app icon.

GNOME shows each folder by icon name — a generic `folder` plus specialised
`folder-documents`, `folder-download`, `folder-music`, … — so recolouring one
isn't enough. This writes the whole set (same folder shape + gradients as
org.gnome.Nautilus.svg, with a white glyph per type) into the Adwaita theme's
scalable/places directory, so every folder in Files and on the desktop reads as
one Sysible family instead of the stock blue Adwaita folders.
"""
import os

OUT = "live-build/config/includes.chroot/usr/share/icons/Adwaita/scalable/places"

# Folder body — identical geometry/gradients to the Files app icon so the whole
# set reads as one family. Front panel spans ~x64..472, y196..404 (centre 256,300).
HEAD = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
 <defs>
  <linearGradient id="back" x1="0" y1="0" x2="1" y2="1">
   <stop offset="0" stop-color="#43a047"/><stop offset="1" stop-color="#2f4fc0"/></linearGradient>
  <linearGradient id="front" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="#7aa2ff"/><stop offset="1" stop-color="#4f6ff0"/></linearGradient>
 </defs>
 <!-- Folder body scaled narrower (slimmer) + a touch taller about its centre;
      glyphs are drawn afterwards at full size so they stay crisp. -->
 <g transform="translate(256,300) scale(0.72,1.06) translate(-256,-300)">
  <path d="M92 108 h116 a24 24 0 0 1 17 7 l34 34 h161 a28 28 0 0 1 28 28 v58 H64 V136 a28 28 0 0 1 28-28 z" fill="url(#back)"/>
  <path d="M64 196 h384 a24 24 0 0 1 24 24 v156 a28 28 0 0 1 -28 28 H68 a28 28 0 0 1 -28-28 V220 a24 24 0 0 1 24-24 z" fill="url(#front)"/>
 </g>
'''
FOOT = "</svg>\n"

W = "#eaf1ff"          # glyph white (slightly cool)
SW = 'stroke="%s" stroke-width="15" fill="none" stroke-linecap="round" stroke-linejoin="round"' % W

# Each glyph is drawn on the front panel, centred near (256, 302).
GLYPHS = {
    "folder": "",
    "folder-documents":
        '<rect x="214" y="246" width="84" height="108" rx="10" fill="%s"/>'
        '<path d="M232 276 h48 M232 300 h48 M232 324 h32" stroke="#4f6ff0" stroke-width="10" stroke-linecap="round"/>' % W,
    "folder-download":
        '<path d="M256 244 v70 M228 288 l28 28 28-28 M222 352 h68" %s/>' % SW,
    "folder-music":
        '<path d="M238 250 v88 M238 250 l60 -14 v88" %s/>'
        '<circle cx="226" cy="342" r="16" fill="%s"/><circle cx="286" cy="328" r="16" fill="%s"/>' % (SW, W, W),
    "folder-pictures":
        '<rect x="210" y="252" width="92" height="96" rx="10" %s/>'
        '<circle cx="236" cy="282" r="10" fill="%s"/>'
        '<path d="M214 340 l30 -34 22 22 20 -16 16 16" %s/>' % (SW, W, SW),
    "folder-videos":
        '<rect x="208" y="256" width="96" height="88" rx="12" %s/>'
        '<path d="M244 282 l28 18 -28 18 z" fill="%s"/>' % (SW, W),
    "folder-publicshare":
        '<circle cx="230" cy="270" r="16" fill="%s"/><circle cx="300" cy="266" r="14" fill="%s"/>'
        '<circle cx="292" cy="342" r="18" fill="%s"/>'
        '<path d="M230 270 L300 266 M230 270 L292 342 M300 266 L292 342" stroke="%s" stroke-width="9" fill="none"/>'
        % (W, W, W, W),
    "folder-templates":
        '<path d="M222 258 h68 a8 8 0 0 1 8 8 v72 a8 8 0 0 1 -8 8 h-68 a8 8 0 0 1 -8 -8 v-72 a8 8 0 0 1 8 -8 z" %s/>'
        '<path d="M214 292 h84 M256 258 v88" stroke="%s" stroke-width="9" fill="none"/>' % (SW, W),
    "user-home":
        '<path d="M256 246 l52 46 M256 246 l-52 46 M220 280 v70 h72 v-70" %s/>' % SW,
    "user-desktop":
        '<rect x="210" y="250" width="92" height="66" rx="10" %s/>'
        '<path d="M256 316 v22 M234 350 h44" %s/>' % (SW, SW),
}

# Aliases so name variants also pick up the Sysible look.
ALIASES = {
    "folder-open": "folder",
    "folder-visiting": "folder",
    "folder-drag-accept": "folder",
    "folder-remote": "folder",
    "inode-directory": "folder",
    "folder-download-open": "folder-download",
    "folder-documents-open": "folder-documents",
    "folder-music-open": "folder-music",
    "folder-pictures-open": "folder-pictures",
    "folder-videos-open": "folder-videos",
    "folder-publicshare-open": "folder-publicshare",
    "folder-templates-open": "folder-templates",
    "user-desktop-open": "user-desktop",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, glyph in GLYPHS.items():
        open(os.path.join(OUT, name + ".svg"), "w").write(HEAD + glyph + "\n" + FOOT)
    for alias, target in ALIASES.items():
        open(os.path.join(OUT, alias + ".svg"), "w").write(
            HEAD + GLYPHS[target] + "\n" + FOOT)
    print("wrote %d folder icons to %s" % (len(GLYPHS) + len(ALIASES), OUT))


if __name__ == "__main__":
    main()
