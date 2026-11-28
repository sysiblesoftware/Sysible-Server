"""Every tool fetched via api.github.com needs a pinned fallback.

Workstation ISO run #86 died nine minutes in:

    == GitHub-release binaries ==
    k9s ok (sha256 verified)
    eza ok
    curl: (22) The requested URL returned error: 403
    ERROR: no published sops release for linux.amd64.
    E: config/hooks/normal/8000-sysible-vendor-tools.hook.chroot failed

api.github.com allows 60 unauthenticated requests an hour PER IP, and GitHub
Actions runners share addresses — so a 403 there is routine, not exceptional.
The same 403 appears twice more in that log, against helm and against opentofu,
and neither stopped the build: each pins a known-good version and falls back to
it. powershell does too. sops was the only one of the four that did not.

So the bug was never sops being unavailable. sops was fine; the API in front of
it was rate-limited, and one of four call sites had no answer for that. The
pattern existed and one place did not follow it — which is the same shape as
almost everything else this QA sweep turned up.

This test is the guard that makes the pattern enforceable rather than
remembered. It reads the hook, finds every api.github.com fetch, and requires
each to have a fallback on the very next lines. A fifth tool added later fails
here until it has one.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / "live-build/config/hooks/normal/8000-sysible-vendor-tools.hook.chroot"


def _api_fetches():
    """[(lineno, varname, following_lines)] for each api.github.com fetch."""
    lines = HOOK.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(lines):
        if "api.github.com/repos/" not in line:
            continue
        m = re.match(r"\s*([A-Za-z_][A-Za-z_0-9]*)=\$\(", line)
        if not m:
            continue                       # not a capture — nothing to fall back to
        out.append((i + 1, m.group(1), lines[i:i + 30]))
    return out


def test_the_hook_still_fetches_through_that_api():
    """Guards the rest: if nothing matches, the test below proves nothing."""
    fetches = _api_fetches()
    assert len(fetches) >= 4, (
        "only %d api.github.com fetches found — the scan has stopped working, "
        "not the hook stopped using the API" % len(fetches))
    names = {v for _, v, _ in fetches}
    assert {"helm_ver", "tofu_ver", "sops_url", "pwsh_ver"} <= names, names


@pytest.mark.parametrize("which", ["helm_ver", "tofu_ver", "sops_url", "pwsh_ver"])
def test_every_api_fetch_has_a_pinned_fallback(which):
    """A 403 must pick a known-good version, not kill the build."""
    for _, var, following in _api_fetches():
        if var != which:
            continue
        blob = "\n".join(following)
        pattern = r'\[\s*-n\s+"\$%s"\s*\]\s*\|\|\s*%s=' % (re.escape(var), re.escape(var))
        assert re.search(pattern, blob), (
            "%s has no pinned fallback. api.github.com is rate-limited per IP "
            "and Actions runners share addresses, so this WILL return 403 and "
            "the build will fail on a tool that was perfectly available.\n\n"
            "Its three siblings do:\n"
            '    [ -n "$helm_ver" ] || helm_ver=v3.16.3\n'
            "Block was:\n%s" % (var, blob[:600]))
        return
    pytest.fail("no api.github.com fetch captures %s" % which)


def test_the_sops_fallback_points_at_a_real_asset():
    """The fallback is only worth having if the URL is right. The amd64 asset
    name is upstream's own, from their install instructions; the ${ARCH}
    substitution is what makes it work for the architecture being built."""
    src = HOOK.read_text(encoding="utf-8")
    m = re.search(r'sops_url="(https://github\.com/getsops/sops/releases/download/[^"]+)"', src)
    assert m, "no pinned sops URL found"
    url = m.group(1)
    assert "/releases/download/v" in url, url
    assert url.endswith("linux.${ARCH}"), (
        "the fallback hardcodes an architecture instead of following ${ARCH}: %s" % url)
    tag = re.search(r"/download/(v[0-9.]+)/", url).group(1)
    assert "sops-%s.linux" % tag in url, (
        "the tag and the asset name disagree, so the URL is a 404: %s" % url)


def test_the_api_is_still_tried_first():
    """The pin is a fallback, not a replacement: pinning outright would quietly
    freeze these tools at whatever version somebody last edited in."""
    src = HOOK.read_text(encoding="utf-8")
    # Scoped to the SOPS block. The first version indexed the whole file for
    # "releases/download/v", which finds opentofu's download URL a few dozen
    # lines earlier — so it compared two unrelated positions and failed on
    # correct code.
    api_at = src.index("api.github.com/repos/getsops/sops")
    pin_at = src.index("getsops/sops/releases/download/v")
    assert api_at < pin_at, "the pinned URL is used before the API is consulted"


def test_the_comment_does_not_still_call_them_best_effort():
    """k9s, eza and sops are REQUIRED — a build failure when missing. A comment
    saying the opposite is what somebody reads before deciding a red build is
    harmless."""
    src = HOOK.read_text(encoding="utf-8")
    # The whole file, not a window anchored on "# GitHub-release binaries".
    # There are TWO such comments — one at the top of the hook describing the
    # file, and the one above these three tools — and the first version
    # anchored on the top one, so its 700-character window never reached the
    # text it was checking. It passed against a hook that still said the
    # opposite. A window has to be anchored on something unique or not used.
    assert "stay best-effort" not in src, (
        "a comment still calls these best-effort, which has not been true since "
        "they were made required:\n%s"
        % src[max(0, src.index("stay best-effort") - 300):][:600])
