"""The ISO ships the DEPENDENCIES. install-sysible fetches the platform.

"The isos should not have the container images in them anymore. We talked about
that. install-sysible should install from github not the iso"
"You were only supposed to keep docker compose and all slop dependencies on the
isos so the user wasn't installing it themselves"

Those are two requirements, not one, and the second is the one at risk. It is
easy to take the platform payload out and quietly take the dependencies with
it -- at which case the operator is back to being told to go and install Docker
by hand, which is the bug the payload was added to avoid in the first place. So
this file asserts BOTH halves, and the second half is deliberately the larger:

  OUT: the container-image archive, the image-loading unit, and any source
       checkout. A built ISO must contain none of them.
  IN:  a container runtime, the compose plugin, and the rest of the toolchain,
       all still guaranteed by the metapackage and still asserted on PATH in
       the finished image.

HISTORY WORTH KEEPING. The previous version of this ISO shipped the finished
images (built in CI) and, before that, a git checkout of the source too. The
checkout is why v1.0.10 shipped a live GitHub token: actions/checkout writes an
Authorization header into .git/config and its cleanup runs AFTER live-build has
already squashed the tree. Operators met it as
    Username for 'https://github.com':
on every `sysiblectl update`, against a PUBLIC repository, because git never
falls back to anonymous once that header is configured.

The tests here are written to fail for the right reason. An earlier check for
the checkout was `"opt/sysible-src" in text`, which kept passing after the
checkout was removed -- because the step that now REFUSES a checkout names that
path too, and a substring match cannot tell "ships it" from "forbids it". The
replacement below resolves each step and exempts only the guard by identity.
"""
import pathlib
import subprocess
import tempfile

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/iso.yml"
CONTROL = ROOT / "packages/sysible-meta/debian/control"
VERIFY = ROOT / "live-build/config/hooks/normal/9500-sysible-verify.hook.chroot"
FIRSTBOOT = ROOT / "live-build/config/hooks/normal/9600-sysible-firstboot.hook.chroot"
CHROOT = ROOT / "live-build/config/includes.chroot"
INSTALLER = ROOT / "packages/sysible-cli/install-sysible"

WORKFLOW = yaml.safe_load(WF.read_text())
JOBS = WORKFLOW["jobs"]

GUARD = "Confirm the ISO carries no platform payload"
PAYLOAD = ("app-images", "sysible-src", "sysible-images.tar")


def _code(p):
    return "\n".join(l for l in p.read_text().splitlines()
                     if not l.lstrip().startswith("#"))


def _logical_lines(p):
    """Comment-stripped shell, with backslash continuations joined.

    Both of the dependency checks below were written as substring searches
    first, and BOTH passed against a mutation that removed the thing they
    claimed to check:

      * `"docker-ce" in depends` passed with docker-ce deleted from the field,
        because the long comment ABOVE the field explains why docker-ce is a
        hard dependency -- so the name was still in the text.
      * `"command -v docker" in v` passed with the runtime guard replaced by
        `true`, because the hook names the same command again a few lines later
        when it works out which runtime it found.

    Joining continuations is what makes the guard checkable as one unit: the
    real check spans three physical lines ending in `\\`, so the condition and
    the `fail` that enforces it only appear together once they are joined.
    """
    out, buf = [], ""
    for line in _code(p).splitlines():
        buf += line.rstrip()
        if buf.endswith("\\"):
            buf = buf[:-1] + " "
            continue
        if buf.strip():
            out.append(" ".join(buf.split()))
        buf = ""
    if buf.strip():
        out.append(" ".join(buf.split()))
    return out


def _depends():
    """The package names in the metapackage's Depends field, comments stripped."""
    import re
    text = CONTROL.read_text()
    m = re.search(r"^Depends:(.*?)^Recommends:", text, re.S | re.M)
    assert m, "no Depends: field in the metapackage control"
    names = []
    for line in m.group(1).splitlines():
        if line.lstrip().startswith("#"):
            continue
        for part in line.split(","):
            part = part.strip()
            if re.fullmatch(r"[a-z0-9][a-z0-9.+-]+", part):
                names.append(part)
    return names


def _guard_step():
    steps = [s for s in JOBS["iso"]["steps"] if s.get("name") == GUARD]
    assert len(steps) == 1, (
        f"expected exactly one {GUARD!r} step, found {len(steps)} — the guard "
        f"that keeps the payload out of the ISO is the thing under test here"
    )
    return steps[0]


# ---- OUT: no platform payload ---------------------------------------------
def test_nothing_builds_platform_images_for_the_iso():
    assert "app-images" not in JOBS, (
        "the app-images job is back — the ISO would carry the platform's "
        "container images again, which is what was removed"
    )


def test_the_iso_job_does_not_wait_on_an_image_build():
    assert not JOBS["iso"].get("needs"), (
        f"the iso job now needs {JOBS['iso'].get('needs')!r}; it should stand "
        f"alone, because there is no payload for it to wait for"
    )


def test_no_step_downloads_an_image_artifact():
    users = [s.get("name", "(unnamed)") for s in JOBS["iso"]["steps"]
             if "download-artifact" in str(s.get("uses", ""))]
    assert not users, f"these steps pull an artifact into the ISO again: {users}"


@pytest.mark.parametrize("token", PAYLOAD)
def test_only_the_guard_mentions_the_payload(token):
    """Resolved per step and exempted by identity, not by substring.

    This is the check whose earlier version passed for the wrong reason, so it
    is worth being precise: every step is flattened to text, and any step other
    than the guard that names a payload path is a step putting it back.
    """
    offenders = []
    for s in JOBS["iso"]["steps"]:
        if s.get("name") == GUARD:
            continue
        if token in " ".join(str(v) for v in s.values()):
            offenders.append(s.get("name", "(unnamed)"))
    assert not offenders, (
        f"{token!r} is named by these steps, which no longer have any reason "
        f"to touch it: {offenders}"
    )


def test_no_step_checks_a_repository_out_into_the_image():
    """The actual mechanism behind the shipped token, asserted directly."""
    bad = [s.get("name", "(unnamed)") for s in JOBS["iso"]["steps"]
           if "actions/checkout" in str(s.get("uses", ""))
           and "includes.chroot" in str(s.get("with", {}).get("path", ""))]
    assert not bad, f"these steps check a repository out INTO the image: {bad}"


@pytest.mark.parametrize("gone", [
    "usr/lib/sysible/load-platform-images",
    "usr/lib/systemd/system/sysible-platform-images.service",
])
def test_the_image_loading_machinery_is_gone(gone):
    assert not (CHROOT / gone).exists(), (
        f"{gone} is back in the image; it exists only to load an image archive "
        f"the ISO no longer carries, so at boot it would fail or mislead"
    )


def test_first_boot_does_not_enable_an_image_loader():
    assert "sysible-platform-images" not in _code(FIRSTBOOT), (
        "first boot still enables the image-loading unit, which no longer "
        "exists — systemctl enable would fail on every install"
    )


def test_the_apps_unit_does_not_order_after_the_image_loader():
    unit = CHROOT / "usr/lib/systemd/system/sysible-apps-firstboot.service"
    if not unit.exists():
        pytest.skip("this edition ships no apps first-boot unit")
    text = unit.read_text()
    assert "sysible-platform-images" not in text, (
        "the apps unit is ordered after a unit that no longer exists, so "
        "systemd would never reach it and nothing would be installed"
    )


def test_the_guard_fails_when_a_payload_appears():
    """Behavioural: run the real step against real trees.

    A guard is only worth having if it stops the build, so this executes it
    rather than reading it -- once on a clean tree, then once per payload path.
    """
    body = _guard_step()["run"]

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        script = root / "step.sh"
        script.write_text(body)

        r = subprocess.run(["sh", str(script)], cwd=root,
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (
            f"the guard failed on a CLEAN tree, so it would fail every build:\n"
            f"{r.stdout}{r.stderr}"
        )

    for path in ("live-build/config/includes.chroot/usr/share/sysible/app-images",
                 "live-build/config/includes.chroot/opt/sysible-src"):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / path).mkdir(parents=True)
            (root / path / "payload").write_text("x")
            script = root / "step.sh"
            script.write_text(body)

            r = subprocess.run(["sh", str(script)], cwd=root,
                               capture_output=True, text=True, timeout=60)
            assert r.returncode != 0, (
                f"{path} was present and the guard still exited 0 — the build "
                f"would ship it"
            )


def test_the_chroot_verify_refuses_a_payload_in_the_squashfs():
    """The in-chroot hook is the last gate before the tree is squashed."""
    v = _code(VERIFY)
    for path in ("/usr/share/sysible/app-images", "/opt/sysible-src"):
        assert path in v, f"the hook no longer looks at {path}"
    assert "! -e" in v and "fail " in v, (
        "the hook names the paths but cannot stop the build"
    )


# ---- IN: the dependencies, which are the whole point ----------------------
def test_the_verify_hook_still_requires_a_container_runtime():
    """The counterweight. Removing the payload must not remove the runtime.

    This is the failure that started the whole thread: a machine reached an
    operator who was then told by the installer to go and fetch Docker
    themselves. The payload is gone; this must not go with it.
    """
    lines = _logical_lines(VERIFY)

    guards = [l for l in lines
              if "command -v docker" in l and "command -v podman" in l
              and "fail " in l]
    assert guards, (
        "no single check both looks for a container runtime AND fails the "
        "build when neither docker nor podman is there — so an ISO could ship "
        "without a runtime and install-sysible would have nothing to run"
    )

    compose = [l for l in lines if "docker-compose-plugin" in l and "fail " in l]
    assert compose, (
        "nothing fails the build when the compose plugin is absent — every "
        "Sysible product is brought up with `docker compose`"
    )


@pytest.mark.parametrize("pkg", ["docker-ce", "docker-compose-plugin",
                                 "containerd.io", "podman", "openssl", "git"])
def test_the_runtime_is_still_a_hard_dependency(pkg):
    assert pkg in _depends(), (
        f"{pkg} is no longer a hard dependency of the metapackage; an install "
        f"without it cannot run the software it was installed to run"
    )


def test_the_installer_fetches_the_platform_from_github():
    """"install-sysible should install from github not the iso"."""
    code = _code(INSTALLER)
    assert "github.com/sysiblesoftware" in code, (
        "install-sysible no longer names a GitHub source, so with the payload "
        "gone there is nothing left for it to install from"
    )
    assert "clone" in code, "install-sysible no longer clones anything"
