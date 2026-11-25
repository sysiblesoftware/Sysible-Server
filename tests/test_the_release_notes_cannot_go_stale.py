"""The release page a user lands on must describe the release they are getting.

The body in iso.yml is hard-coded, and it opened with a literal

    ### New in 1.0.5

followed by 1.0.5's bullets. Nothing derives that from the tag being published,
so cutting 1.0.6 would have produced a release page headed "New in 1.0.5",
describing changes a user already had, and saying nothing about the one that
matters — that the installer is no longer the text-mode one.

Exactly the shape of the website's own "1.0.3 Ignition": a version written by
hand into a file that is not rewritten when a release is cut.

The heading now comes from the tag. These guards keep it that way, and keep the
things a user needs in order to USE the download present.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ISO_YML = ROOT / ".github/workflows/iso.yml"


def _body():
    """The release body block from the publish step."""
    s = ISO_YML.read_text(encoding="utf-8")
    m = re.search(r"\n          body: \|\n(.*?)\n          fail_on_unmatched_files:", s, re.S)
    assert m, "could not find the release body in iso.yml"
    return m.group(1)


def test_the_heading_is_not_a_hard_coded_version():
    body = _body()
    m = re.search(r"###\s*New in\s*(.+)", body)
    assert m, "the release body has no 'New in' heading"
    heading = m.group(1).strip()
    assert not re.fullmatch(r"v?\d+\.\d+(\.\d+)?", heading), (
        f"the release heading is the literal version {heading!r}. It is not "
        f"rewritten when a tag is cut, so the next release would be published "
        f"under the previous release's number. Derive it from the tag.")
    assert "${{" in heading and "tag" in heading, (
        f"the heading should come from the tag being published, got {heading!r}")


def test_no_version_number_is_written_into_the_notes_by_hand():
    """Any literal x.y.z in the body is a claim that goes stale silently."""
    body = _body()
    bad = []
    for n, line in enumerate(body.splitlines(), 1):
        if "${{" in line:
            continue
        for m in re.finditer(r"(?<![\w.-])\d+\.\d+\.\d+(?![\w.-])", line):
            # BUSL-1.1 and the like are licence versions, not product versions.
            if re.search(r"(BUSL|GPL|LGPL|AGPL|MPL|Apache)[- ]?$", line[:m.start()]):
                continue
            bad.append(f"  line {n}: {line.strip()[:100]}")
    assert not bad, (
        "these write a version into the release body by hand:\n" + "\n".join(bad))


@pytest.mark.parametrize("needed", [
    "SHA256SUMS",            # how to verify
    "sysible.com/security",  # where the key fingerprint lives
    "REASSEMBLE",            # how to put the parts together
    "cat sysible-server-",   # how to join the parts
])
def test_the_notes_tell_a_user_how_to_use_the_download(needed):
    """The ISO ships split across several files. Without these a release is a
    pile of .part files with no instructions."""
    assert needed in _body(), (
        f"the release notes no longer mention {needed!r}, which a user needs in "
        f"order to verify or reassemble the download")


def test_both_authenticity_checks_are_given():
    """There are TWO things to verify -- the parts before joining them, and the
    whole ISO after -- and each has its own signed manifest.

    A plain `"gpg --verify" in body` check passed while one of them was
    deleted, because the other was still there. Name them separately.
    """
    body = _body()
    for what, needle in (
            ("the downloaded parts", "gpg --verify SHA256SUMS.<arch>.parts.gpg SHA256SUMS.<arch>.parts"),
            ("the reassembled ISO", "gpg --verify SHA256SUMS.<arch>.gpg SHA256SUMS.<arch>")):
        assert needle in body, (
            f"the notes no longer say how to check the authenticity of {what}")
    for what, needle in (
            ("the downloaded parts", "sha256sum -c SHA256SUMS.<arch>.parts"),
            ("the reassembled ISO", "sha256sum -c SHA256SUMS.<arch>")):
        assert needle in body, (
            f"the notes no longer say how to checksum {what}")


def test_the_publish_step_refuses_to_ship_missing_files():
    """fail_on_unmatched_files keeps a release from being published with some of
    its parts or checksums silently absent."""
    s = ISO_YML.read_text(encoding="utf-8")
    assert re.search(r"fail_on_unmatched_files:\s*true", s), (
        "a release could publish with assets missing and nobody would be told")
