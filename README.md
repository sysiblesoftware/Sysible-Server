<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/sysible-logo-dark.png">
    <img alt="Sysible Server" src=".github/sysible-logo-light.png" width="340">
  </picture>
</p>

<p align="center"><strong>Sysible Server</strong> — the headless engineering platform</p>

# Sysible Server

A Debian-stable–based **headless server base**. Install it and the server
toolchain is already there — containers, Kubernetes, infrastructure-as-code,
cloud CLIs, the diagnostics set — with no desktop and no GUI applications.

Kernel, systemd, OpenSSH, Python and package maintenance are Debian's. This
repository maintains only the Sysible-specific packages, the installer image,
and an opinionated toolset on top.

## Install

Download an ISO from [Releases](https://github.com/sysiblesoftware/Sysible-Server/releases).
It is larger than GitHub's 2 GB per-file limit, so each build ships as numbered
`*.part` files — `REASSEMBLE.<arch>.md` in the release has the exact commands,
and [sysible.com/security](https://sysible.com/security) has the signing-key
fingerprint to verify them against.

The boot menu's **Install Sysible Server** entry runs the graphical Debian
Installer; **(text mode)** is the same installer with the newt frontend, kept
as the fallback for when the graphical one will not start.

During installation you are asked which Sysible software to set up. It is a
checklist, not an either/or:

```
[ ] slop (all three behind one gateway)
[ ] controller (standalone)
[ ] slep (standalone)
[ ] connect (standalone)
```

`slop` runs Controller, SLEP and Connect behind a single gateway. The three
standalone options run them individually. Ticking `slop` supersedes the others
because the gateway runs those same containers under those same names, and
Docker names are unique per host. Whatever you tick is installed on the first
boot that has a working network.

You can change the selection at any time afterwards:

```sh
sudo install-sysible            # pick from a checklist
sudo install-sysible slop       # or name what you want
sudo sysible-tools              # the optional third-party tools
```

## Layout

```
packages/
  sysible-meta/       # the `sysible-server` metapackage — this IS the distro
  sysible-cli/        # `sysible`, `install-sysible`, `sysiblectl`
  sysible-release/    # apt configuration + archive keyring
  sysible-branding/   # os-release, GRUB theme, Sora font
  sysible-artwork/    # wallpapers and branding assets
branding/             # the ONE source mark + the generator for every derived asset
live-build/           # the ISO: Debian Installer, preseed, boot menus
scripts/              # build, publish and repair helpers (see scripts/README.md)
tests/                # the guards; run with `pytest`
docs/                 # third-party licences
```

## What is in the image

The `sysible-server` metapackage groups its dependencies by purpose — system
administration, networking, archives, troubleshooting, the modern CLI set,
language/dev base, automation and IaC, and containers. Read
`packages/sysible-meta/debian/control` for the authoritative list; it is
commented and is the thing that actually defines the distribution.

Hardening in the image includes `fail2ban`, `auditd`, AppArmor, a password
quality floor via `libpam-pwquality`, and `unattended-upgrades`. The system
boots to a console; reach it over SSH.

## Updates

Installed machines track the Sysible apt repository, so changes arrive without
reinstalling:

```sh
sudo apt update && sudo apt upgrade
```

Published package versions carry a `+ci<timestamp>.r<run-id>.g<commit>` suffix.
That suffix is load-bearing rather than decorative: the pool is served behind a
CDN with `immutable` caching, so every build must land on a URL that has never
been cached before. A bare, unsuffixed version in `apt policy` output means
something published without stamping — see `scripts/publish-repo.sh`.

## Build it yourself

```sh
cd packages/sysible-meta        # or any other package
dpkg-buildpackage -us -uc -b
```

```sh
./scripts/build-all.sh          # every package, into dist/
cd live-build && sudo ./build.sh                     # the ISO (root, ~30 min)
cd live-build && sudo SYSIBLE_ARCH=arm64 ./build.sh  # arm64 instead
```

`scripts/README.md` covers the signing key and the apt repository. Branding
assets are all generated from one source mark — never hand-edit a derived PNG:

```sh
python3 branding/render-branding.py       # regenerate every logo asset
sh scripts/verify-branding.sh             # fail fast if any has drifted
```

## Links

- [sysible.com/server](https://sysible.com/server) — product page
- [sysible.com/security](https://sysible.com/security) — release signing key
- [RELEASE.md](RELEASE.md) — how updates ship over apt
- [roadmap.md](roadmap.md) — the phased plan
