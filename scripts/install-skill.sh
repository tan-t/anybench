#!/usr/bin/env bash
# anybench-harvest スキルを Claude Code にインストールする。
#
#   ./scripts/install-skill.sh --global        # ~/.claude/skills/ (全リポジトリで利用可)
#   ./scripts/install-skill.sh /path/to/repo   # <repo>/.claude/skills/ (そのリポジトリのみ)
#
# インストール後は Claude Code 上で /anybench-harvest [commit] で呼び出せる。
set -euo pipefail

SRC="$(cd "$(dirname "$0")/../skills/anybench-harvest" && pwd)"

case "${1:-}" in
  --global)
    DEST="$HOME/.claude/skills/anybench-harvest"
    ;;
  "")
    echo "usage: $0 --global | <repo-path>" >&2
    exit 1
    ;;
  *)
    if [ ! -d "$1" ]; then
      echo "error: directory not found: $1" >&2
      exit 1
    fi
    DEST="$(cd "$1" && pwd)/.claude/skills/anybench-harvest"
    ;;
esac

mkdir -p "$DEST"
cp -r "$SRC/." "$DEST/"
echo "installed: $DEST"
echo "usage: open Claude Code and run  /anybench-harvest [commit]"
