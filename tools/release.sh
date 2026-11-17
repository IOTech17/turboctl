#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Publish a signed release, which installs from install.sh then pick up with "turboctl update".
#
#   tools/release.sh VERSION      e.g. tools/release.sh 1.1.0
#
# Needs: a clean main branch where turboctl says VERSION and CHANGELOG.md has a
# "## VERSION" section, gh logged in, and the private key matching data/allowed_signers
# (RELEASE_KEY, default ~/.config/turboctl-release/release_key). The key never leaves
# this machine: keep a backup, without it no machine will accept a new release.
set -eu
cd "$(dirname "$0")/.."

version=${1:?usage: tools/release.sh VERSION}
key=${RELEASE_KEY:-$HOME/.config/turboctl-release/release_key}
name=turboctl-$version
die() { echo "release.sh: $*" >&2; exit 1; }

[ "$(git branch --show-current)" = main ] || die "not on main"
[ -z "$(git status --porcelain)" ] || die "uncommitted changes"
grep -q "^__version__ = \"$version\"$" turboctl || die "turboctl does not say $version"
grep -q "^## $version$" CHANGELOG.md || die "no \"## $version\" section in CHANGELOG.md"
git rev-parse -q --verify "refs/tags/v$version" >/dev/null && die "tag v$version exists"
[ -r "$key" ] || die "no release key at $key"
make check

out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
git tag -a "v$version" -m "turboctl $version"
git archive --format=tar.gz --prefix="$name/" -o "$out/$name.tar.gz" "v$version"
ssh-keygen -Y sign -q -f "$key" -n turboctl-release "$out/$name.tar.gz"
# The machines check with the public key in the release itself: check the same way.
ssh-keygen -Y verify -f data/allowed_signers -I turboctl-release -n turboctl-release \
    -s "$out/$name.tar.gz.sig" < "$out/$name.tar.gz" >/dev/null || die "signature does not match data/allowed_signers"
# Release notes: the CHANGELOG section of this version.
awk -v head="## $version" '$0 == head {on = 1; next} /^## / {on = 0} on' CHANGELOG.md > "$out/notes.md"

git push origin main "v$version"
gh release create "v$version" "$out/$name.tar.gz" "$out/$name.tar.gz.sig" \
    --title "turboctl $version" --notes-file "$out/notes.md"
echo "turboctl $version published; machines installed with install.sh update within a day."
