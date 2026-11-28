"""The cloud and infrastructure tools must actually ship, not nearly ship.

"I want all the cloud and infrastructure tools to actually ship with the iso"
and "Also does kubectl ship installed on these isos? Helm too?"

Three separate mechanisms decide whether a tool reaches a built ISO, and they
had drifted apart:

  1. `debian/control` names it. build.sh then expands Depends, Recommends AND
     Suggests into ONE live-build package list, which apt installs as a hard
     set -- so on the ISO the field a package sits in changes nothing. What
     does change things is build.sh's VEND list, which is the only thing that
     keeps a non-Debian package (helm, sops, eza, gcloud) out of a list apt
     would otherwise fail to resolve.

     This is why `azure-cli, google-cloud-cli` sitting in **Suggests** was a
     real defect rather than a cosmetic one: Suggests is still flattened into
     the ISO's list, so every ISO had them -- while a machine that installed
     sysible-server from repo.sysible.com got neither, because apt does not
     install Suggests. One product name, two different toolsets.

  2. The vendor hook installs the non-Debian ones, or fails the build.

  3. 9500-sysible-verify asserts the program is on PATH in the finished image.
     This is the only one of the three that survives somebody editing the
     control file, and it is the reason an ISO can no longer be published
     while advertising a tool it does not carry.

The test that matters most here is the LAST one in this file: it runs build.sh's
own awk generator against the real control file, so it fails if VEND or the
control file changes in a way that would drop a promised package -- rather than
asserting that a name appears somewhere in a file.
"""
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTROL = ROOT / "packages/sysible-meta/debian/control"
VERIFY = ROOT / "live-build/config/hooks/normal/9500-sysible-verify.hook.chroot"
BUILD = ROOT / "live-build/build.sh"

# The cloud/virtualization capability. Every one of these rested on something
# that nothing checked: az and gcloud on the vendor hook alone, age and gh on
# an unasserted list entry, virsh and qemu-img on a Recommends of a Recommends.
CLOUD = ["az", "gcloud", "virsh", "qemu-img", "age", "gh"]

# Newly promised in the metapackage, and the ones most likely to be quietly
# dropped again because they look like conveniences rather than dependencies.
# yq is the headline: the image shipped jq and not yq, while everything an
# operator edits on it -- compose files, Kubernetes manifests, playbooks, CI
# workflows -- is YAML.
HEADLINE = ["yq", "socat", "git-lfs", "shellcheck", "rclone", "wg"]


def _code(path):
    """Shell source with comment lines removed.

    Same reason as test_the_promised_tools_are_guaranteed.py: the comment
    block that EXPLAINS this loop names every tool in it, so a plain substring
    search over the file passes whether or not the loop checks anything.
    """
    return "\n".join(l for l in path.read_text().splitlines()
                     if not l.lstrip().startswith("#"))


def _verified_tools():
    """The tool names 9500-sysible-verify actually loops over."""
    code = _code(VERIFY)
    m = re.search(r"for _t in\s+(.*?);\s*do", code, re.S)
    assert m, "the verify hook no longer has a `for _t in ...; do` tool loop"
    return set(m.group(1).replace("\\", " ").split())


def _field(name):
    """The package names in one control field, comments stripped."""
    text = CONTROL.read_text()
    m = re.search(rf"^{name}:(.*?)^(?=[A-Z][A-Za-z-]*:)", text, re.S | re.M)
    assert m, f"no {name}: field in {CONTROL}"
    out = []
    for line in m.group(1).splitlines():
        if line.lstrip().startswith("#"):
            continue
        for part in line.split(","):
            part = part.strip()
            if re.fullmatch(r"[a-z0-9][a-z0-9.+-]+", part):
                out.append(part)
    return out


@pytest.mark.parametrize("tool", CLOUD)
def test_the_verify_hook_asserts_the_cloud_tool(tool):
    """An ISO cannot be published while missing one of these.

    The summary comment under this loop has claimed for some time that
    libvirt/QEMU is "installed above and checked by name". It was not checked
    by anything at all -- the loop went straight from `nft jq` to `sops eza
    pwsh`. A comment asserting a guarantee that does not exist is worse than
    no comment: it is what somebody reads before deciding not to add the check.
    """
    assert tool in _verified_tools(), (
        f"{tool} is not in the verify loop, so an ISO built while its install "
        f"silently failed would still be published as carrying it"
    )


@pytest.mark.parametrize("tool", HEADLINE)
def test_the_verify_hook_asserts_the_headline_tool(tool):
    assert tool in _verified_tools(), (
        f"{tool} is promised by the metapackage but nothing asserts it landed"
    )


def test_the_cloud_clis_are_not_in_suggests():
    """Suggests is the one field apt does NOT install.

    So this was the only field that could make an ISO and an apt-installed
    machine disagree -- and it did, because the ISO's list is built from all
    three fields while `apt install sysible-server` honours only two.
    """
    suggests = _field("Suggests")
    for pkg in ("azure-cli", "google-cloud-cli"):
        assert pkg not in suggests, (
            f"{pkg} is back in Suggests — the vendor hook installs it on every "
            f"ISO, so a machine installed from repo.sysible.com would get a "
            f"different toolset under the same product name"
        )


def test_the_cloud_clis_are_recommended():
    recommends = _field("Recommends")
    for pkg in ("azure-cli", "google-cloud-cli"):
        assert pkg in recommends, f"{pkg} is no longer recommended at all"


def test_virsh_has_a_package_that_provides_it():
    """libvirt-clients, named outright.

    virsh used to arrive only as a Recommends of libvirt-daemon-system (and on
    the Workstation, of virt-manager), so the single command that drives a
    hypervisor was two levels of "probably" deep -- while SLEP's hypervisor
    feature assumes it is there.
    """
    named = _field("Depends") + _field("Recommends")
    assert "libvirt-clients" in named, (
        "libvirt-clients is not named in the metapackage, so virsh is back to "
        "arriving only as somebody else's Recommends"
    )


def test_ltrace_is_not_promised_because_it_would_break_arm64():
    """A regression guard with a reason, so it is not "cleaned up" later.

    ltrace is in bookworm on amd64 and NOT on arm64. Because build.sh flattens
    every field into one hard package list, adding it in ANY field -- Depends,
    Recommends or Suggests -- makes the arm64 ISO build fail outright on "no
    installation candidate", the same way grub-efi-ia32 once did. It was on the
    shortlist of debugging tools to add for exactly that reason and left off.
    """
    named = _field("Depends") + _field("Recommends") + _field("Suggests")
    assert "ltrace" not in named, (
        "ltrace is amd64-only in bookworm; every field here is flattened into "
        "the ISO's hard package list, so this breaks the arm64 build"
    )


def _awk_program():
    """build.sh's real toolkit generator, lifted out of build.sh."""
    text = BUILD.read_text()
    m = re.search(r"\nawk '\n(.*?)\n' \"\$ROOT/packages/sysible-meta/debian/control\"",
                  text, re.S)
    assert m, "could not find build.sh's awk toolkit generator — did it move?"
    return m.group(1)


def test_the_real_generator_puts_the_new_tools_in_the_toolkit_list():
    """Run build.sh's own awk over the real control file.

    This is the check that actually holds: it exercises the generator and its
    VEND list rather than asserting a name appears in a file, so it fails if
    somebody adds a package to VEND (which silently removes it from the ISO's
    list and hands its install to a hook that may not do it) or edits it out of
    debian/control.
    """
    prog = _awk_program()
    r = subprocess.run(["awk", prog, str(CONTROL)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"the generator failed: {r.stderr}"
    produced = set(r.stdout.split())

    # The Debian-packaged half of what the metapackage now promises. The
    # non-Debian half (helm, sops, gcloud, ...) is deliberately NOT here: VEND
    # keeps it out of this list on purpose, and the vendor hook installs it.
    for pkg in ["yq", "yamllint", "shellcheck", "shfmt", "socat", "git-lfs",
                "rclone", "restic", "wireguard-tools", "dmidecode", "lshw",
                "pciutils", "usbutils", "nvme-cli", "ipmitool", "fio",
                "bpftrace", "tshark", "conntrack", "libvirt-clients",
                "python3-boto3", "python3-kubernetes", "direnv", "pre-commit"]:
        assert pkg in produced, (
            f"{pkg} is promised but build.sh's generator does not put it in the "
            f"ISO's package list — check whether it was added to VEND"
        )

    # ...and the vendor-installed ones must still be EXCLUDED, or apt would try
    # to resolve a package that is not in Debian and fail the build.
    for pkg in ["helm", "sops", "eza", "google-cloud-cli", "kubectl", "k9s",
                "opentofu", "azure-cli"]:
        assert pkg not in produced, (
            f"{pkg} reached the generated list; it is not in bookworm, so apt "
            f"would fail the ISO build with 'no installation candidate'"
        )
