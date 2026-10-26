#!/bin/sh
# Install the WHYLINE git hooks into the repository of the current directory.
set -e
src="$(cd "$(dirname "$0")" && pwd)/hooks/pre-commit"
dest="$(git rev-parse --git-path hooks)/pre-commit"
mkdir -p "$(dirname "$dest")"
cp "$src" "$dest"
chmod +x "$dest"
echo "installed pre-commit hook -> $dest"
