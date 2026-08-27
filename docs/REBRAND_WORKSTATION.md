# Rebrand: Sysible Server / Sysible Linux → **Sysible Workstation**

Tracks the rebrand from the distro's former display names ("Sysible Server",
"Sysible Linux") to **Sysible Workstation**. Split into what's **done**, what needs
**sign-off** (cosmetics), and the **coordinated** slug/repo renames that must be
verified in an ISO build.

## 1. Done (this branch: `rebrand/sysible-workstation`)

**Display brand strings** — all 75 occurrences of "Sysible Server" / "Sysible
Linux" replaced with "Sysible Workstation", and contradictory taglines reworded
("…engineering & automation server" → "…platform"). This is text only; no image
or ISO was rebuilt. Notable files:

- OS identity: `9000-sysible-system.hook.chroot` (`PRETTY_NAME`/`NAME`, `/etc/issue`,
  `/etc/issue.net`, motd, GRUB title logic) and the `branding-guard` that enforces
  `PRETTY_NAME` — both now target "Sysible Workstation" consistently.
- GRUB theme text, installer-branding hook, apt/ssh/tmux/profile.d headers.
- Docs, READMEs, `THIRD-PARTY-LICENSES.md`, package descriptions.
- Wallpaper generator banner (`SYSIBLE WORKSTATION`) + a bug fix: its hardcoded
  `ROOT = /home/user/sysible-linux` now derives from the file location.

## 2. Needs sign-off — cosmetics (then batched into ONE ISO)

Per the working agreement, boot/desktop cosmetics are locked with **mockups first**,
signed off, then regenerated and batched into a **single** ISO build — never one
build per tweak. Pending after sign-off:

- **Wallpapers** — regenerate the shipped 8K set (dark + light, all styles) with the
  new banner: `python3 branding/wallpapers/render_wallpapers.py` →
  `packages/sysible-artwork/backgrounds/`. (Mockups already rendered at preview res
  for review.)
- **Lock screen** — `branding/lockscreen/render-lock.py`.
- **GRUB / boot splash** — theme text is updated; render/verify the splash at the
  real **1024×768** boot resolution.
- **Installer branding** — `9400-sysible-installer-branding.hook.binary`.

Only after these are signed off: regenerate assets, commit, and run **one**
`iso.yml` build to bake them in.

## 3. Coordinated slug rename `sysible-server` → `sysible-workstation`

The **slug** is build-critical (package name, artifact name, install paths), so
change all of these in ONE commit and verify with an ISO build — do NOT partially
rename:

| File | Reference | New value |
|---|---|---|
| `packages/sysible-meta/debian/control` | `Package: sysible-server` | `sysible-workstation` |
| `packages/sysible-meta/debian/changelog` | metapackage name in the entry | `sysible-workstation` |
| `.github/workflows/iso.yml` | artifact `name: sysible-server-${arch}-iso` | `sysible-workstation-${arch}-iso` |
| `usr/share/doc/sysible-server/` | doc install dir (tracks the package name) | `usr/share/doc/sysible-workstation/` |
| `live-build/build.sh` | comment/dep resolution referencing the metapackage | `sysible-workstation` |
| `live-build/config/includes.binary/preseed.cfg` | default hostname fallback (commented) | `sysible-workstation` |

After renaming: `git mv` the doc dir, update any `Depends:`/`Recommends:` that name
the metapackage, and run one ISO build to confirm live-build still resolves the
package set and the artifact uploads under the new name.

## 4. GitHub repo rename `sysible-server` → `sysible-workstation`

A GitHub-side operation (I can't do it from here). Steps:

1. **Rename the repo** on GitHub (Settings → Rename). GitHub keeps redirects from
   the old name, but update explicit references so nothing depends on the redirect.
2. **Update git remotes** in every clone:
   `git remote set-url origin https://github.com/sysiblesoftware/sysible-workstation`.
3. **Update cross-repo references** to the old name/URL:
   - This repo: the EE-style image-label `image.source` and any README badges/links.
   - **Controller** (`Sysible-Controller`, `sysible-controller-ee`) and **SLEP**
     (`sysible-linux-engineering-platform`) docs/guides that mention "Sysible
     Server" as the ISO — reword to "Sysible Workstation".
   - Your working-agreement/CLAUDE.md notes that reference "Sysible Linux ISO" /
     `sysible-server`.
   - Any CI that checks out or dispatches this repo by name.
4. Consider whether the **SLEP repo** (`sysible-linux-engineering-platform`) should
   also drop "linux" for naming consistency — separate decision, not required by
   this rebrand.

## 5. Verify checklist (post-ISO, after slug + cosmetics land)

- `cat /etc/os-release` → `PRETTY_NAME="Sysible Workstation"`.
- `/etc/issue`, `/etc/motd`, GRUB menu title, installer banner all read
  "Sysible Workstation".
- `branding-guard` passes (doesn't try to "correct" the new name).
- Desktop wallpaper + lock screen show the new wordmark.
- ISO artifact uploads as `sysible-workstation-<arch>-iso`.
