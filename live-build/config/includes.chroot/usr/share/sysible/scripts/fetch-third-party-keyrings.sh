#!/bin/sh
# Fetch the third-party APT signing key + source that sysible-tools needs.
#
# HashiCorp's products (Terraform, Vault, Consul, Nomad, Packer, Boundary) are
# BUSL-1.1, so only the apt *source definition* — never the binaries — is set up
# here, and only when the operator opts in via `sysible-tools`. That keeps the
# base image's apt clean (no repo whose key is absent) until the user chooses to
# install a licensed tool and accepts its licence.
#
# sysible-tools calls this when /usr/share/keyrings/hashicorp.gpg is missing.
# Safe to re-run; needs network (installing the tool needs it anyway).
set -eu

KEYRING=/usr/share/keyrings/hashicorp.gpg
SOURCES=/etc/apt/sources.list.d/hashicorp.sources
# The apt.releases.hashicorp.com pools are keyed by the DEBIAN base codename,
# not the Sysible marketing codename.
CODENAME=bookworm

if [ ! -s "$KEYRING" ]; then
  echo "== fetching HashiCorp signing key =="
  tmp="$(mktemp)"
  curl -fsSL --connect-timeout 20 --max-time 120 https://apt.releases.hashicorp.com/gpg -o "$tmp"
  gpg --dearmor < "$tmp" > "$KEYRING"
  rm -f "$tmp"
  chmod 0644 "$KEYRING"
  echo "   wrote $KEYRING"
fi

if [ ! -s "$SOURCES" ]; then
  cat > "$SOURCES" <<SRC
Types: deb
URIs: https://apt.releases.hashicorp.com
Suites: $CODENAME
Components: main
Architectures: amd64 arm64
Signed-By: $KEYRING
SRC
  echo "   wrote $SOURCES"
fi
