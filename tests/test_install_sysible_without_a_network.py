"""install-sysible must work on a host that already holds the source.

WHAT THIS FILE USED TO BE, and why that matters when reading it. It asserted
that the ISO shipped the platform's FINISHED container images, built in CI, so
that a first install never had to pull or build anything -- and, before that,
that it also shipped a git checkout of the source, so a fully airgapped install
was possible.

Both are gone now, deliberately:

  * The checkout carried actions/checkout's Authorization header, because that
    action's cleanup runs AFTER live-build has squashed the tree. v1.0.10
    shipped a live GitHub token in every ISO, and what operators actually met
    was not a security warning but
        Username for 'https://github.com':
    on every `sysiblectl update` -- against a PUBLIC repository, because git
    never falls back to anonymous once an Authorization header is configured.
  * The images were removed on instruction: "The isos should not have the
    container images in them anymore ... install-sysible should install from
    github not the iso". The ISO's job is the DEPENDENCIES -- Docker, compose,
    and everything else the platform needs to run -- so that an operator never
    installs a container runtime by hand. The platform itself is fetched.

What the ISO now carries, and must keep carrying, is asserted in
test_the_iso_ships_dependencies_not_the_platform.py. This file keeps the half
that is still true and still worth pinning: install-sysible's own behaviour
when the source is ALREADY on disk.

That path is not dead code. An operator can put a checkout in place themselves,
and install-sysible must then use it rather than refuse at an unconditional
network gate -- which is exactly what it used to do:

    say "== checking the internet connection =="
    _online || { ... "Nothing has been installed." ; exit 1; }

On a host with no route out, the first-boot service ran the script, the script
exited 1 with "Nothing has been installed", the service retried three times and
wrote /etc/sysible/apps-failed -- while the source sat on the disk, unread.

These tests run the REAL script against a simulated host, because a grep for
the fix would pass on the broken version too: the gate it must not run
unconditionally is still in the file, for the host that does need it.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _code(p):
    """File contents with comment lines removed."""
    return "\n".join(l for l in p.read_text().splitlines()
                      if not l.lstrip().startswith("#"))


# --------------------------------------------------------------------------
# The installer itself.
#
# Everything above shipped, and ticking "slop" in the installer STILL left a
# host with nothing running. The ISO side was all correct; `install-sysible`
# refused before it looked at any of it:
#
#     say "== checking the internet connection =="
#     _online || { ... "Nothing has been installed." ; exit 1; }
#
# An unconditional gate, so on a host with no route out the first-boot service
# ran the script, the script exited 1 with "Nothing has been installed", the
# service retried three times and wrote /etc/sysible/apps-failed -- while the
# images and the source sat on the disk, unread. And past that gate, the
# per-product loop would still `git clone` all three apps that the shipped SLOP
# checkout already vendors.
#
# These run the real script against a simulated host, because a grep for the
# fix would have passed on the broken version too: the gate it has to NOT run
# is still in the file, for the host that does need it.
INSTALLER = ROOT / "packages/sysible-cli/install-sysible"

_STUB_OFFLINE = {
    "curl": '#!/bin/sh\necho "curl: (6) Could not resolve host" >&2\nexit 6\n',
    "git": (
        "#!/bin/sh\n"
        'for a in "$@"; do case "$a" in clone|ls-remote)\n'
        '  echo "fatal: unable to access" >&2; exit 128 ;; esac; done\n'
        'case " $* " in *" pull "*) echo "fatal: unable to access" >&2; exit 1 ;; esac\n'
        "exit 0\n"
    ),
}
_STUB_ONLINE = {
    "curl": "#!/bin/sh\nexit 0\n",
    "git": (
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  if [ "$a" = clone ]; then\n'
        '    d=$(eval echo "\\${$#}"); mkdir -p "$d/.git" "$d/deploy"\n'
        "    printf 'services: {}\\n' > \"$d/deploy/docker-compose.yml\"\n"
        "    printf '#!/bin/sh\\nexit 0\\n' > \"$d/deploy/sysiblectl\"\n"
        '    chmod +x "$d/deploy/sysiblectl"; echo "CLONED $d"; exit 0\n'
        "  fi\n"
        "done\n"
        "exit 0\n"
    ),
}
_STUB_COMMON = {
    "sysiblectl": (
        "#!/bin/sh\n"
        'echo "SYSIBLECTL product=$1 verb=${2:-}'
        ' dir=${SYSIBLE_CONTROLLER_DIR:-}${SYSIBLE_SLEP_DIR:-}'
        '${SYSIBLE_CONNECT_DIR:-}${SYSIBLE_SLOP_DIR:-}"\nexit 0\n'
    ),
    "docker": "#!/bin/sh\nexit 0\n",
    "whiptail": "#!/bin/sh\nexit 0\n",
}


def _host(tmp_path, *, network, ships_platform, also_cloned=(), ships_images=None):
    """A fake machine: stub binaries on PATH and the on-disk state under tmp."""
    import os
    import stat

    bins = tmp_path / "bin"
    bins.mkdir()
    for name, body in {
        **(_STUB_ONLINE if network else _STUB_OFFLINE),
        **_STUB_COMMON,
    }.items():
        f = bins / name
        f.write_text(body)
        f.chmod(f.stat().st_mode | stat.S_IEXEC)

    src = tmp_path / "src"
    imgs = tmp_path / "app-images"
    marker = tmp_path / "images-loaded"
    src.mkdir()

    if ships_platform:
        slop = src / "sysible-linux-operations-platform"
        (slop / ".git").mkdir(parents=True)
        (slop / "docker-compose.yml").write_text("services: {}\n")
        for app in ("controller", "slep", "connect"):
            d = slop / "apps" / app / "deploy"
            d.mkdir(parents=True)
            (d / "docker-compose.yml").write_text("services: {}\n")
        ctl = slop / "apps/controller/deploy/sysiblectl"
        ctl.write_text("#!/bin/sh\nexit 0\n")
        ctl.chmod(ctl.stat().st_mode | stat.S_IEXEC)
        # Independently settable: "source but no images" is a real state (a host
        # that cloned, or an ISO that shipped one half) and it must NOT be
        # mistaken for a complete airgapped install.
        if ships_images if ships_images is not None else True:
            imgs.mkdir()
            (imgs / "sysible-images.tar").write_bytes(b"\0" * 4096)

    for repo in also_cloned:
        d = src / repo
        (d / ".git").mkdir(parents=True)
        (d / "docker-compose.yml").write_text("services: {}\n")

    # The three absolute paths are rewritten, nothing else: the logic under test
    # is byte-for-byte the shipped logic. Each substitution is ASSERTED, so a
    # rename upstream fails this loudly instead of quietly testing nothing.
    script = INSTALLER.read_text()
    for const, value in (
        ("SRC_DIR=/opt/sysible-src", f"SRC_DIR={src}"),
        ("PREBUILT_IMAGES_DIR=/usr/share/sysible/app-images", f"PREBUILT_IMAGES_DIR={imgs}"),
        (
            "PLATFORM_IMAGES_MARKER=/var/lib/sysible/platform-images-loaded",
            f"PLATFORM_IMAGES_MARKER={marker}",
        ),
    ):
        assert script.count(const) == 1, (
            f"install-sysible no longer defines {const!r} exactly once, so this "
            f"test would run against the real /opt and /usr/share. Fix the test."
        )
        script = script.replace(const, value, 1)

    run = tmp_path / "install-sysible"
    run.write_text(script)

    env = dict(os.environ, PATH=f"{bins}:/usr/bin:/bin")
    return run, env, src


def _install(tmp_path, *args, network, ships_platform, also_cloned=(), ships_images=None):
    import subprocess

    run, env, src = _host(
        tmp_path,
        network=network,
        ships_platform=ships_platform,
        also_cloned=also_cloned,
        ships_images=ships_images,
    )
    p = subprocess.run(
        ["sh", str(run), "-y", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return p.stdout + p.stderr, src


# -- the bug: an airgapped host that ships everything must install -----------


def test_an_airgapped_host_that_ships_the_platform_does_not_check_the_network(tmp_path):
    out, _ = _install(tmp_path, "slop", network=False, ships_platform=True)
    assert "Nothing has been installed" not in out, (
        "install-sysible aborted on a host that already holds the images and the "
        "source. This is the whole airgap requirement, and the path the installer "
        "menu takes on first boot.\n\n" + out
    )
    assert "nothing to download" in out


@pytest.mark.parametrize("product", ["controller", "slep", "connect", "slop"])
def test_every_app_is_started_on_an_airgapped_host(tmp_path, product):
    out, _ = _install(tmp_path, "slop", network=False, ships_platform=True)
    assert f"SYSIBLECTL product={product}" in out, (
        f"{product} never got started on an airgapped host.\n\n" + out
    )


def test_nothing_is_cloned_when_the_source_is_already_vendored(tmp_path):
    out, _ = _install(tmp_path, "slop", network=False, ships_platform=True)
    assert "(clone)" not in out, "a product was skipped because a clone failed\n\n" + out
    for app in ("controller", "slep", "connect"):
        assert f"using the {app} source vendored in the platform checkout" in out


def test_the_apps_resolve_to_the_vendored_source_not_an_empty_directory(tmp_path):
    out, src = _install(tmp_path, "slop", network=False, ships_platform=True)
    vendored = src / "sysible-linux-operations-platform/apps"
    for app in ("controller", "slep", "connect"):
        assert f"dir={vendored / app}" in out, (
            f"{app} was handed a path that is not the vendored checkout.\n\n" + out
        )


def test_a_failed_refresh_does_not_look_like_a_broken_install(tmp_path):
    """An unreachable remote is not an error when the code is already here."""
    out, _ = _install(tmp_path, "slop", network=False, ships_platform=True)
    assert "could not reach the remote" in out
    assert not re.search(r"^fatal:", out, re.M), (
        "git's raw 'fatal: unable to access' reached the operator, which reads as "
        "a failed install on a host that is working exactly as designed.\n\n" + out
    )


# -- and the gate must STILL fire for the host that really is just offline ---


def test_a_host_with_nothing_local_still_gets_the_offline_message(tmp_path):
    out, _ = _install(tmp_path, "slop", network=False, ships_platform=False)
    assert "checking the internet connection" in out
    assert "Nothing has been installed" in out, (
        "the connectivity gate was removed rather than made conditional: a host "
        "that genuinely needs the network now fails later and less clearly.\n\n" + out
    )


def test_an_online_host_still_clones(tmp_path):
    out, src = _install(tmp_path, "controller", network=True, ships_platform=False)
    assert "  online." in out
    assert f"CLONED {src / 'sysible-controller'}" in out, (
        "the normal online install stopped cloning.\n\n" + out
    )


def test_a_real_checkout_is_preferred_over_the_vendored_copy(tmp_path):
    """A host that cloned SLEP keeps using that clone, not SLOP's vendored one."""
    out, src = _install(
        tmp_path,
        "slep",
        network=True,
        ships_platform=True,
        also_cloned=("sysible-linux-engineering-platform",),
    )
    assert f"dir={src / 'sysible-linux-engineering-platform'}" in out, (
        "a standalone checkout was ignored in favour of the vendored copy, so "
        "`sysiblectl slep update` would stop tracking the repo the operator "
        "cloned.\n\n" + out
    )


# -- the state EVERY ISO install is now in: images, no source ---------------
#
# This pair is here because the ISO stopped shipping a source checkout. Before
# that, images-and-source was the normal case and images-without-source was
# unusual; now it is what every single host built from an ISO looks like on
# first boot, and it had no test at all. The unusual case is the one that was
# covered.


def test_an_online_host_with_the_images_but_no_source_installs(tmp_path):
    """The ordinary first boot. It has to CLONE (the source is not here any
    more) and it must not pull or build images (they are)."""
    out, src = _install(tmp_path, "slop", network=True,
                        ships_platform=False, ships_images=True)
    assert "Nothing has been installed" not in out, (
        "the ordinary first boot of an ISO-installed host did not install.\n\n" + out)
    assert "nothing to download" not in out, (
        "it decided it already had the platform, but the ISO no longer ships "
        "the source — it has to clone.\n\n" + out)
    assert (src / "sysible-linux-operations-platform").exists(), (
        "nothing was cloned into %s\n\n%s" % (src, out))


def test_an_offline_host_with_only_the_images_says_so_rather_than_half_installing(tmp_path):
    """The other half, and the cost of dropping the checkout, asserted rather
    than left to be discovered.

    An ISO-installed host that cannot reach github.com can no longer install:
    the images are here, the source is not, and the source is not optional.
    The failure has to be the clear "no internet connection" BEFORE anything is
    touched — not a clone that fails halfway and leaves a half-built stack.
    """
    out, _ = _install(tmp_path, "slop", network=False,
                      ships_platform=False, ships_images=True)
    assert "checking the internet connection" in out, (
        "the network check was skipped on a host that has the images but NOT "
        "the source — the clone will fail later, after the menu is gone.\n\n" + out)
    assert "Nothing has been installed" in out, (
        "it got past the gate and started installing anyway.\n\n" + out)


def test_source_without_the_images_is_not_treated_as_airgap_ready(tmp_path):
    """Half a shipment is not a shipment.

    The source alone gets compose as far as reading its file and then straight
    to a registry for images this host does not have. Skipping the gate there
    trades one clear "no internet connection" for a wall of pull failures from
    inside a build, which is strictly worse than what it replaced.
    """
    out, _ = _install(
        tmp_path, "slop", network=False, ships_platform=True, ships_images=False
    )
    assert "checking the internet connection" in out, (
        "the network check was skipped on a host that has the source but NOT the "
        "images, so the install will fail later, inside compose, pulling images "
        "it cannot reach.\n\n" + out
    )
    assert "Nothing has been installed" in out


# --------------------------------------------------------------------------
# The first-boot unit that runs the installer.
#
# Sysible Server's unit has ordered after the image loader since the loader was
# added. Sysible Workstation uses a different mechanism entirely -- marker files
# and sysible-platform-installer.service -- and never got the same ordering, so
# the two editions raced differently on the first boot: Workstation could run
# the install before the images were in Docker's store, and compose would then
# go to a registry for images the machine was already carrying.
#
# Parameterised over whichever unit this repo ships so neither edition can be
# fixed alone again.
_APPS_UNITS = [
    p
    for p in (
        ROOT / "live-build/config/includes.chroot/usr/lib/systemd/system/sysible-apps-firstboot.service",
        ROOT / "packages/sysible-platform-apps/debian/sysible-platform-installer.service",
    )
    if p.exists()
]


def test_this_repo_ships_a_first_boot_apps_unit():
    assert _APPS_UNITS, (
        "no first-boot unit runs the apps the operator ticked in the installer, "
        "so ticking one does nothing at all"
    )


@pytest.mark.parametrize("unit", _APPS_UNITS, ids=lambda p: p.name)
def test_the_apps_unit_does_not_require_the_network(unit):
    """Wants= is an optimisation; Requires= would block the airgapped install."""
    text = _code(unit)
    assert "Requires=network-online.target" not in text, (
        f"{unit.name} REQUIRES the network, so a host whose source is already "
        f"on disk -- and which needs no network to install it -- would never "
        f"run the install at all"
    )
    assert "Wants=network-online.target" in text, (
        f"{unit.name} should still WANT the network, so a host that does need to "
        f"clone and build waits for it rather than failing and retrying"
    )


def test_an_offline_install_does_not_report_problems_it_cannot_avoid(tmp_path):
    """A machine that did exactly the right thing must not say it failed.

    The optional software -- HashiCorp's tools, the AWS CLI, Obsidian where the
    edition offers it -- is downloaded from the vendors at install time. That is
    the whole reason the ISO cannot carry it, licensing included. So an airgapped
    host can never have it, and counting that as a failure ended a flawless
    offline install on

        Finished WITH PROBLEMS -- these did not come up: optional-software

    which is how a working machine gets read as a broken one, and is the
    complaint this whole path exists to answer.
    """
    out, _ = _install(tmp_path, "slop", network=False, ships_platform=True)
    assert "WITH PROBLEMS" not in out, (
        "an offline install still finished WITH PROBLEMS:\n\n" + out
    )
    assert "optional-software" not in out, (
        "the optional software was still counted as a failed component\n\n" + out
    )
    assert "it was SKIPPED. Nothing is wrong." in out, (
        "nothing told the operator why the optional software is absent, so its "
        "absence looks like a fault\n\n" + out
    )
