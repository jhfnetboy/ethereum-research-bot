#!/usr/bin/env bash
# Build, commit and push to GitHub, then deploy that same commit to Cloudflare Pages.
# Deploy only runs after the push succeeds.
#
# The source of truth is the directory this script lives in (the store copy).
# Building directly on the store mount can stall, so every run first mirrors the
# published sources (.gitignore, site/ without dist/docs/workers, reports/) one way
# into a local build directory, then builds, scans, commits, pushes and deploys
# from there. Nothing is ever written back to the source directory.
#
# Usage (from anywhere):
#   bash site/publish.sh "日报 2026-11-12"        # mirror + build + commit + push + deploy
#   bash site/publish.sh --no-deploy "message"    # mirror + build + commit + push only
#
# Env:
#   GIT_DIR                 git directory (default: /home/box/git/ethereum-research-bot.git,
#                           kept outside the store because the mount does not allow .git)
#   BUILD_ROOT              local build directory (default: /home/box/build/ethereum-research-bot);
#                           wiped and refilled from the source on every run
#   COPY_TIMEOUT            seconds allowed for the mirror copy (default: 300)
#   CLOUDFLARE_API_TOKEN    needed for deploy; read from the environment only, never stored
#   PAGES_PROJECT           default: ethereum-research-bot
#   PAGES_BRANCH            default: main
set -euo pipefail

SITE_DIR_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_ROOT="$(dirname "$SITE_DIR_SRC")"
BUILD_ROOT="${BUILD_ROOT:-/home/box/build/ethereum-research-bot}"
COPY_TIMEOUT="${COPY_TIMEOUT:-300}"
export GIT_DIR="${GIT_DIR:-/home/box/git/ethereum-research-bot.git}"
PAGES_PROJECT="${PAGES_PROJECT:-ethereum-research-bot}"
PAGES_BRANCH="${PAGES_BRANCH:-main}"

DEPLOY=1
if [[ "${1:-}" == "--no-deploy" ]]; then DEPLOY=0; shift; fi
MSG="${1:-update $(TZ=Asia/Bangkok date +%F)}"

if [[ ! -d "$GIT_DIR" ]]; then
  echo "git dir not found: $GIT_DIR" >&2; exit 1
fi
case "$BUILD_ROOT" in
  ""|"/"|"$SRC_ROOT"|"$SRC_ROOT"/*) echo "BUILD_ROOT must be a separate local directory: $BUILD_ROOT" >&2; exit 1 ;;
esac

echo "==> mirror $SRC_ROOT -> $BUILD_ROOT"
rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT"
timeout "$COPY_TIMEOUT" tar -C "$SRC_ROOT" \
    --exclude='site/dist' --exclude='site/docs' --exclude='site/workers' \
    --exclude='__pycache__' --exclude='.wrangler' --exclude='node_modules' \
    -cf - .gitignore site reports \
  | tar -C "$BUILD_ROOT" -xf -
export GIT_WORK_TREE="$BUILD_ROOT"
SITE_DIR="$BUILD_ROOT/site"

echo "==> build in $SITE_DIR"
( cd "$SITE_DIR" && python3 build.py )

echo "==> secret scan of staged content"
cd "$BUILD_ROOT"
git add -A
if git diff --cached --name-only | grep -E '(^|/)\.env|\.pem$|\.key$|site/docs/|site/workers/|site/dist/' ; then
  echo "refusing: sensitive or excluded path staged" >&2; git reset -q; exit 1
fi
if git diff --cached -U0 -- ':(top)' ':(top,exclude)site/publish.sh' | grep -E '^\+' | grep -Eiq \
   'CLOUDFLARE_API_TOKEN=|account_id|ghp_[A-Za-z0-9]{20,}|github_pat_|xox[bap]-|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|[0-9a-f]{32}\.workers'; then
  echo "refusing: possible secret in staged diff" >&2; git reset -q; exit 1
fi

if git diff --cached --quiet; then
  echo "==> nothing new to commit"
else
  git commit -q -m "$MSG"
fi
SHA="$(git rev-parse HEAD)"

# The mirror was copied from the source in this run, so HEAD equals the source's
# published files. A clean status here confirms nothing was left unstaged.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "work tree not clean after commit; aborting before push" >&2; git status --short >&2; exit 1
fi

echo "==> push $SHA"
git push origin "HEAD:main"
REMOTE_SHA="$(git ls-remote origin refs/heads/main | cut -f1)"
if [[ "$REMOTE_SHA" != "$SHA" ]]; then
  echo "push check failed: remote main is $REMOTE_SHA, local is $SHA" >&2; exit 1
fi

if [[ "$DEPLOY" == "1" ]]; then
  if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
    echo "CLOUDFLARE_API_TOKEN not set; pushed but not deployed" >&2; exit 1
  fi
  echo "==> deploy $SHA to Pages project $PAGES_PROJECT"
  ( cd "$SITE_DIR" && npx --yes wrangler pages deploy dist \
      --project-name "$PAGES_PROJECT" --branch "$PAGES_BRANCH" \
      --commit-hash "$SHA" --commit-message "$(git log -1 --format=%s "$SHA")" --commit-dirty=false )
fi
echo "==> done: $SHA"
