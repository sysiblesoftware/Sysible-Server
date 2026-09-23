"""The branding guard, run for real against a throwaway /etc.

What the GRUB menu says is one line on disk — GRUB_DISTRIBUTOR, in a drop-in that
belongs to us. That ownership is the whole problem: no package upgrade ever
restores it, so when this repo was briefly rebranded to "Sysible Workstation"
(b0715be) and rebranded back a day later (8a2f18e), the machines installed in
between kept booting a menu naming the wrong product — and nothing on them would
ever have corrected it. Fixing the source only fixes machines installed from a
later image.

So these tests do not read the script; they run it, as root, against a sandboxed
/etc bind-mounted over the real one inside a mount namespace. What the guard
writes to the drop-in IS the boot menu's text, and whether update-grub ran is the
difference between a corrected file and a corrected menu.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "live-build" / "config" / "includes.chroot" / "usr" / "lib" / "sysible" / "branding-guard"

WANT = 'GRUB_DISTRIBUTOR="Sysible Server"'
DROPIN = "default/grub.d/20_sysible-theme.cfg"

# The guard rewrites /usr/lib/os-release and /etc/motd too. Those are not what
# these tests are about, so the sandbox starts already correct and they no-op —
# a test that trips over an unrelated section proves nothing about this one.
OS_RELEASE = 'PRETTY_NAME="Sysible Server"\nNAME="Sysible Server"\nID=sysible\n'
MOTD = "\nSysible Server — engineering & automation platform\n"


# As root, ask for a mount namespace and nothing else. The extra --map-root-user
# a non-root run needs creates an UNPRIVILEGED user namespace, and Ubuntu 24.04
# confines those with AppArmor: the namespace is created, then the first exec
# inside it is denied (126, "Permission denied") — which is what broke this job
# on the runner even though it was already running as root.
UNSHARE = ["unshare", "--mount"] if os.geteuid() == 0 else ["unshare", "--map-root-user", "--mount"]


def _have_namespaces() -> bool:
    if not shutil.which("unshare"):
        return False
    # Probe with a real exec, not `true` as a builtin: creating the namespace and
    # being allowed to run something in it are two different permissions.
    r = subprocess.run(
        UNSHARE + ["/bin/sh", "-c", "exec /bin/true"], capture_output=True, timeout=30
    )
    return r.returncode == 0


# A skip is the right answer on a machine that cannot bind-mount, and the wrong
# one in CI: a guard that silently stops being exercised is no guard. CI sets
# SYSIBLE_REQUIRE_NS=1, which turns the skip into a failure.
if not _have_namespaces():
    if os.environ.get("SYSIBLE_REQUIRE_NS") == "1":
        raise RuntimeError(
            "SYSIBLE_REQUIRE_NS=1 but unshare/user namespaces are unavailable — "
            "the branding-guard tests would have been skipped silently"
        )
    pytestmark = pytest.mark.skip(
        reason="needs unshare + user namespaces to bind-mount a throwaway /etc"
    )


class Sandbox:
    """A fake /etc the real guard is pointed at, plus a log of what it ran."""

    def __init__(self, root: Path):
        self.root = root
        self.etc = root / "etc"
        (self.etc / "default" / "grub.d").mkdir(parents=True)
        (self.etc / "grub.d").mkdir(parents=True)
        (self.etc / "motd").write_text(MOTD)
        # Already patched, so section 2 no-ops and only 2b can move anything.
        (self.etc / "grub.d" / "10_linux").write_text('echo "${GRUB_DISTRIBUTOR}"\n')
        (root / "os-release").write_text(OS_RELEASE)
        self.log = root / "update-grub.log"
        self.log.write_text("")
        bin_ = root / "bin"
        bin_.mkdir()
        (bin_ / "update-grub").write_text(
            '#!/bin/sh\nprintf "update-grub\\n" >> "$FAKE_LOG"\n'
        )
        (bin_ / "update-grub").chmod(0o755)
        self.bin = bin_

    def write(self, rel: str, text: str) -> Path:
        p = self.etc / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def read(self, rel: str) -> str:
        return (self.etc / rel).read_text()

    def exists(self, rel: str) -> bool:
        return (self.etc / rel).exists()

    def run(self) -> subprocess.CompletedProcess:
        """Run the REAL guard with this sandbox mounted over /etc."""
        script = (
            f"mount --bind {self.etc} /etc && "
            f"mount --bind {self.root / 'os-release'} /usr/lib/os-release && "
            f"exec {GUARD}"
        )
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["FAKE_LOG"] = str(self.log)
        return subprocess.run(
            UNSHARE + ["sh", "-c", script],
            capture_output=True, text=True, env=env, timeout=120,
        )

    @property
    def regenerated(self) -> bool:
        return "update-grub" in self.log.read_text()


@pytest.fixture()
def sandbox(tmp_path):
    return Sandbox(tmp_path)


def test_wrong_product_in_the_menu_is_corrected(sandbox):
    """The exact state of a machine installed from an image built mid-rebrand."""
    sandbox.write(DROPIN, 'GRUB_THEME="/boot/grub/themes/sysible/theme.txt"\n'
                          'GRUB_DISTRIBUTOR="Sysible Workstation"\n')

    r = sandbox.run()

    assert r.returncode == 0, r.stderr
    assert WANT in sandbox.read(DROPIN)
    assert "Workstation" not in sandbox.read(DROPIN)
    # ...and the rest of the drop-in is left alone: it carries the theme and the
    # gfxmode, and this guard has no business rewriting those.
    assert "GRUB_THEME=" in sandbox.read(DROPIN)
    # A corrected file is not a corrected menu until grub.cfg is regenerated.
    assert sandbox.regenerated


def test_correct_product_changes_nothing(sandbox):
    """Runs on every boot and after every apt transaction — it must be cheap."""
    sandbox.write(DROPIN, f'GRUB_THEME="/boot/grub/themes/sysible/theme.txt"\n{WANT}\n')
    before = sandbox.read(DROPIN)

    r = sandbox.run()

    assert r.returncode == 0, r.stderr
    assert sandbox.read(DROPIN) == before
    assert not sandbox.regenerated, "update-grub ran with nothing to do"


def test_missing_dropin_is_restored(sandbox):
    """An older image had no drop-in at all: the menu would say 'Debian'."""
    assert not sandbox.exists(DROPIN)

    r = sandbox.run()

    assert r.returncode == 0, r.stderr
    assert WANT in sandbox.read(DROPIN)
    assert sandbox.regenerated


def test_a_later_dropin_naming_another_sysible_product_is_corrected(sandbox):
    """grub-mkconfig sources the drop-ins in order, so the LAST one wins.

    Ours sorts at 20; anything later would override it and put the wrong product
    back on the menu with our own file looking perfectly correct.
    """
    sandbox.write(DROPIN, f"{WANT}\n")
    sandbox.write("default/grub.d/99-late.cfg",
                  'GRUB_DISTRIBUTOR="Sysible Workstation"\n')

    r = sandbox.run()

    assert r.returncode == 0, r.stderr
    assert WANT in sandbox.read("default/grub.d/99-late.cfg")
    assert sandbox.regenerated


def test_a_distributor_that_is_not_ours_is_left_alone(sandbox):
    """Branding drift is ours to fix; another vendor's entry is not."""
    sandbox.write(DROPIN, f"{WANT}\n")
    sandbox.write("default/grub.d/99-vendor.cfg", 'GRUB_DISTRIBUTOR="Proxmox VE"\n')

    r = sandbox.run()

    assert r.returncode == 0, r.stderr
    assert sandbox.read("default/grub.d/99-vendor.cfg") == 'GRUB_DISTRIBUTOR="Proxmox VE"\n'
    assert not sandbox.regenerated


def test_dropin_without_a_distributor_line_gains_one(sandbox):
    sandbox.write(DROPIN, 'GRUB_GFXMODE="1024x768,auto"\n')

    r = sandbox.run()

    assert r.returncode == 0, r.stderr
    assert WANT in sandbox.read(DROPIN)
    assert 'GRUB_GFXMODE="1024x768,auto"' in sandbox.read(DROPIN)
    assert sandbox.regenerated


def test_ten_linux_suffix_and_the_product_name_share_one_regeneration(sandbox):
    """Both sections can fire on the same run; grub.cfg is rebuilt once."""
    sandbox.write("grub.d/10_linux", 'echo "${GRUB_DISTRIBUTOR} GNU/Linux"\n')
    sandbox.write(DROPIN, 'GRUB_DISTRIBUTOR="Sysible Workstation"\n')

    r = sandbox.run()

    assert r.returncode == 0, r.stderr
    assert "GNU/Linux" not in sandbox.read("grub.d/10_linux")
    assert WANT in sandbox.read(DROPIN)
    assert sandbox.log.read_text().count("update-grub") == 1


def test_no_grub_on_the_box_is_not_an_error(sandbox):
    """The guard also runs where grub is absent; it must not fail the boot."""
    shutil.rmtree(sandbox.etc / "default" / "grub.d")
    (sandbox.bin / "update-grub").unlink()

    r = sandbox.run()

    assert r.returncode == 0, r.stderr
