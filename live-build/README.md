# Sysible Workstation — ISO (live-build)

Builds a bootable headless server ISO with the Sysible toolkit preinstalled and
the standard text-mode Debian Installer for install-to-disk.

## Build

On a Debian host (matching the target release), with the Sysible packages
available (published to the Sysible repo, or dropped into `config/packages.chroot/`):

```
sudo apt install live-build
./build.sh
```

`build.sh` wires the Sysible + upstream vendor repos (and their keys) into the
build chroot, then runs live-build. Output: `live-image-amd64.hybrid.iso`.

## What it produces

- A headless server system — no GNOME, no desktop apps.
- The full non-GUI engineering/DevOps toolkit (SSH, containers, Kubernetes,
  cloud CLIs, IaC, etc.).
- Sysible hardening (key-only sshd, sysctl, pwquality) and the green Sysible
  GRUB/isolinux boot-menu branding.
- os-release branded `ID=sysible` / `ID_LIKE=debian`.
- The standard text-mode Debian Installer for install-to-disk.

## Notes

- Until the Sysible repo is live, drop the locally-built `sysible-*.deb` into
  `config/packages.chroot/` and live-build will include them.
- When rebasing to a newer Debian release, bump `CODENAME` in `build.sh` and the
  distribution in `auto/config`, plus the Kubernetes minor version.
- The ISO cannot be boot-tested from `dpkg`/CI without KVM; use Sysible Controller
  + provision-lab-vms to boot it in a VM and run `sysible verify` as the gate.
