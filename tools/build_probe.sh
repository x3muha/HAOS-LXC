#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Build the restricted probe from a pinned official, signed HAOS release.
# Run on a disposable Linux build worker, not on the PVE host.
set -eu
umask 077
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run as a normal user on a disposable build worker.' >&2
    exit 1
fi
if [ "$#" -ne 1 ]; then
    echo "Usage: sh tools/build_probe.sh NEW_OUTPUT_DIRECTORY" >&2
    exit 2
fi
for name in curl cosign sha256sum xz awk; do
    command -v "$name" >/dev/null || { echo "Missing tool: $name" >&2; exit 1; }
done
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$1
version=18.4
asset=haos_generic-x86-64-$version.img.xz
base=https://github.com/home-assistant/operating-system/releases/download/$version
identity=https://github.com/home-assistant/operating-system/.github/workflows/build.yaml@refs/tags/$version
mkdir -p "$(dirname -- "$out")"
mkdir "$out"
out=$(CDPATH= cd -- "$out" && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
cd "$work"
for file in SHA256SUMS SHA256SUMS.sigstore.json "$asset"; do
    curl --fail --silent --show-error --location --retry 3 --proto '=https' --proto-redir '=https' --output "$file" "$base/$file"
done
# Verify publisher identity and tag, not just a checksum from the download.
# Any mismatch fails closed. Do not weaken the expected identity on failure.
cosign verify-blob SHA256SUMS \
    --bundle SHA256SUMS.sigstore.json \
    --certificate-identity "$identity" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com
awk -v f="$asset" '$2 == f || $2 == "*" f {print}' SHA256SUMS > selected.sha256
[ "$(wc -l < selected.sha256)" -eq 1 ] || { echo 'Expected exactly one signed asset digest' >&2; exit 1; }
sha256sum --check --strict selected.sha256
xz -d "$asset"
raw=$asset
raw="$(basename "$raw" .xz)"
raw_hash=$(sha256sum "$raw" | cut -d ' ' -f 1)
/usr/bin/python3 "$script_dir/extract_rootfs.py" "$raw" --sha256 "$raw_hash" --output "$out/slot-a"
/usr/bin/python3 "$script_dir/audit_rootfs.py" "$out/slot-a/rootfs.tar.gz" > "$out/audit.json"
rootfs_hash=$(sha256sum "$out/slot-a/rootfs.tar.gz" | cut -d ' ' -f 1)
/usr/bin/python3 "$script_dir/prepare_probe.py" "$out/slot-a/rootfs.tar.gz" --sha256 "$rootfs_hash" --output "$out/probe"
cp selected.sha256 "$out/upstream-image.sha256"
cp SHA256SUMS.sigstore.json "$out/upstream-signature.json"
cp SHA256SUMS "$out/upstream-SHA256SUMS"
printf '%s\n' "$identity" > "$out/upstream-identity.txt"
printf 'Local experimental template: %s/probe/haos-lxc-probe.tar.gz\n' "$out"
