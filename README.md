# Sysible Server

A stripped-down, **headless** Debian-based server base — no GUI — with the
tooling an engineer needs to run server software already baked in on first boot.
The server sibling of [Sysible Workstation](https://github.com/sysiblesoftware/Sysible-Linux).

## What's in it

Boots to a console (no desktop, no display manager). Preinstalled:

- **Containers & orchestration** — Docker CE + compose/buildx, `podman`/`buildah`/`skopeo`, `kubectl`, Helm, `k9s`
- **Infrastructure as code / automation** — OpenTofu, Ansible + ansible-lint, SOPS
- **Networking & diagnostics** — `iproute2`, `nftables`, `tcpdump`, `nmap`, `mtr`, `iperf3`, `socat`, `dnsutils`, `ethtool`
- **Observability & troubleshooting** — `htop`/`btop`, `iotop`, `sysstat`, `ncdu`, `smartmontools`, `lsof`, `strace`
- **Modern CLI** — `jq`, `ripgrep`, `fd`, `bat`, `fzf`, `tmux`
- **Languages / base** — Python 3 + pip/venv/pipx, `build-essential`
- **Security & hardening** — `fail2ban`, `auditd`, AppArmor, `libpam-pwquality`, unattended security upgrades, a sysctl hardening profile, and a hardened SSH drop-in

Debian-native packages come from
[`live-build/config/package-lists/sysible-server.list.chroot`](live-build/config/package-lists/sysible-server.list.chroot).
The non-Debian vendor tools (Docker CE, kubectl, Helm, OpenTofu, k9s, SOPS) are
installed by
[`8000-sysible-server-vendor-tools.hook.chroot`](live-build/config/hooks/normal/8000-sysible-server-vendor-tools.hook.chroot),
which wires up the official vendor apt repos / fetches signed release binaries —
so this repo is self-contained and needs nothing from the Workstation repo.

## SSH

Unlike the Workstation image (SSH **off** by default), a server is reachable
over SSH by design, so `ssh` is **enabled**. The shipped drop-in
([`10-sysible.conf`](live-build/config/includes.chroot/etc/ssh/sshd_config.d/10-sysible.conf))
disables root login and tightens the login surface. Password auth is left **on**
so a freshly-installed box is reachable before keys are provisioned — once your
`authorized_keys` are in place, set `PasswordAuthentication no` in that drop-in.

## Build

Build on a Debian host or in a `debian:bookworm` container with network access:

```sh
cd live-build
sudo ./build.sh            # amd64 by default
SYSIBLE_ARCH=arm64 sudo ./build.sh   # arm64
```

The finished `*.iso` lands in `live-build/`. Or build in CI: run the **ISO**
GitHub Actions workflow (`.github/workflows/iso.yml`), choosing the architecture
and, optionally, publishing a GitHub Release. To release both arches to one tag,
dispatch the workflow twice (amd64 and arm64) with `release=true` and the same
`tag`.

> Releases are signed if a `SYSIBLE_GPG_PRIVATE_KEY` repository secret is set;
> without it, checksums still ship but unsigned.

## Relationship to Sysible Workstation

| | Sysible Workstation | Sysible Server |
|---|---|---|
| Target | Engineer's desktop/laptop/VM | Headless server |
| Desktop | GNOME + Calamares installer | none (console) |
| SSH | off by default | on (hardened) |
| Extras | VSCodium, LibreOffice, SysTerm, Ollama, GUI apps | server tooling only |

Same Debian base, same hardening philosophy, same vendor tooling for containers
and IaC — minus everything graphical.
