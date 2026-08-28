# Sysible Server — Build Roadmap

A Debian-stable–based engineering **server**. We inherit everything we can
from Debian and maintain only Sysible-specific packages + an opinionated toolkit.

## Model

Two things ship Sysible, everything else is Debian or an upstream repo:

1. **A tiny apt repo** (`sysible-stable` / `sysible-dev`) holding only `sysible-*`.
2. **Metapackages** that pull the toolkit — the real "product" is `sysible-server`.

The ISO is just live-build preseeding `sysible-server` on a Debian base, installed
via the text-mode Debian Installer — headless, no GNOME and no Calamares.
Do the metapackage + repo first; the ISO is the last step, not the first.

## Phases

- [ ] **P1 — Repo + metapackage**
  - [x] `sysible-meta` source → `sysible-server` (this scaffold)
  - [ ] `sysible-archive-keyring` + `sysible-release` (our repo config + third-party repo configs/keys)
  - [ ] aptly repo, `sysible-dev` and `sysible-stable` suites, publish script
- [ ] **P2 — Sysible packages**
  - [ ] `sysible-cli` (ships `sysible verify`)
  - [ ] `sysible-controller`, `sysible-agent` (already built elsewhere — repackage for the repo)
  - [ ] `sysible-artwork` (the finalized wallpapers) + `sysible-branding` (GRUB theme, os-release, Sora font)
- [ ] **P3 — Verify framework**
  - [ ] `sysible verify [--network|--containers|--virtualization|--security|--json]`
  - [ ] CI: install `sysible-server` on fresh Debian, run `sysible verify`, gate on it
- [ ] **P4 — ISO**
  - [ ] live-build config: text-mode Debian Installer + `sysible-server` + branding (no GUI)
  - [ ] CI builds nightly `dev` ISO + tagged `stable` ISO; boot-test in a VM via Sysible Controller

## Non-goals

Custom kernel · fork of Debian · replacing systemd · mirroring Debian packages ·
any GUI/desktop stack (that is the separate Sysible Workstation product, in the
Sysible-Linux repo).

## Known package traps (tracked so the metapackage ships the *right* thing)

- `terraform` / `packer` — not in Debian (HashiCorp BSL); from `apt.releases.hashicorp.com` via `sysible-release`.
- `kubectl` / `helm` — from `pkgs.k8s.io` / `baltocdn`.
- `docker-compose` — Debian's is dead v1; use `docker-compose-plugin` (v2) from Docker's repo.
- `awscli` — Debian is v1; AWS v2 is a bundled installer.
- `eza` — only Debian 13+; `bat`→`batcat`, `fd-find`→`fdfind` (symlink them).
- `yq` — Debian's is the Python one; the Go `mikefarah/yq` is what people expect.
</content>
