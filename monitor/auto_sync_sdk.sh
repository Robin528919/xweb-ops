#!/usr/bin/env bash
# 把 xweb-ops.json 同步进 go-twitter-api，并维护「唯一一个」自动同步 PR（从不合并）。
#
# 用法：
#   GO_TWITTER_API_REPO=/path/to/go-twitter-api monitor/auto_sync_sdk.sh [--dry-run]
# 环境变量：
#   GO_TWITTER_API_REPO  必填：go-twitter-api 本地 checkout（只用来取 remote；工作在独立 worktree 里，不动它的工作区）
#   XWEB_OPS_MANIFEST    清单（本地路径或 URL），默认 <本仓库>/xweb-ops.json
#   AUTO_SYNC_BRANCH     PR 分支，默认 auto/web-sync（每次从最新默认分支重建后 force-with-lease 推送）
#   AUTO_SYNC_WORKTREE   worktree 目录，默认 $TMPDIR/go-twitter-api-autosync
#   AUTO_SYNC_BASE       基线分支（默认 origin 的默认分支；测试用）
#   DRY_RUN=1 或 --dry-run：同步 + 检查 + 本地提交，但不推送、不开 PR
# 输出 / 退出码：
#   0  NO_DIFF（与默认分支一致；如有已开的自动同步 PR 也打印其 URL）/ PR_URL: <url> / DRY_RUN: ...
#   2  sync_sdk.py 报错（清单缺 op、provided variable 不合法等）
#   3  环境问题（缺 GO_TWITTER_API_REPO、gh 未登录、sync_sdk.py 不支持 --manifest 等）
#   4  检查失败（gofmt / build / vet / test），不推送
set -euo pipefail

DRY_RUN=${DRY_RUN:-0}
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1
die() { local code=$1; shift; echo "AUTO_SYNC_FAILED: $*" >&2; echo "AUTO_SYNC_FAILED: $*"; exit "$code"; }

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=${GO_TWITTER_API_REPO:-}
[[ -n "$REPO" && -d "$REPO/.git" ]] || die 3 "GO_TWITTER_API_REPO 未设置或不是 git checkout"
MANIFEST=${XWEB_OPS_MANIFEST:-$ROOT/xweb-ops.json}
BRANCH=${AUTO_SYNC_BRANCH:-auto/web-sync}
LABEL=auto/web-sync
WT=${AUTO_SYNC_WORKTREE:-${TMPDIR:-/tmp}/go-twitter-api-autosync}
command -v go >/dev/null || die 3 "PATH 里没有 go"
if [[ "$DRY_RUN" != 1 ]]; then gh auth status >/dev/null 2>&1 || die 3 "gh 未登录"; fi

git -C "$REPO" fetch -q origin || die 3 "git fetch 失败"
DEFAULT=$(git -C "$REPO" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
[[ -n "$DEFAULT" ]] || DEFAULT=master
# AUTO_SYNC_BASE：测试用，覆盖基线分支（默认 = 仓库默认分支）。
DEFAULT=${AUTO_SYNC_BASE:-$DEFAULT}

cleanup() { git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup
git -C "$REPO" worktree add -q -f -B "$BRANCH" "$WT" "origin/$DEFAULT" || die 3 "创建 worktree 失败"
cd "$WT"
grep -q -- "--manifest" tools/websync/sync_sdk.py || die 3 "origin/$DEFAULT 的 sync_sdk.py 还不支持 --manifest"

SNAP=$(python3 - "$MANIFEST" <<'PY'
import json, sys, urllib.request, re
src = sys.argv[1]
d = json.load(urllib.request.urlopen(src, timeout=30)) if re.match(r"https?://", src) else json.load(open(src))
print(d.get("snapshot", "unknown"))
PY
) || die 3 "读不到清单 $MANIFEST"

existing_pr() { gh pr list --state open --head "$BRANCH" --json url -q '.[0].url' 2>/dev/null || true; }

set +e
python3 tools/websync/sync_sdk.py --manifest "$MANIFEST" --check > /tmp/auto_sync_check.$$ 2>&1
rc=$?
set -e
cat /tmp/auto_sync_check.$$; rm -f /tmp/auto_sync_check.$$
case $rc in
  0)
    echo "NO_DIFF: origin/$DEFAULT 已与清单 $SNAP 一致"
    if [[ "$DRY_RUN" != 1 ]]; then url=$(existing_pr); [[ -n "$url" ]] && echo "OPEN_PR: $url（与默认分支已无差异，可人工关闭）"; fi
    exit 0 ;;
  1) ;;
  *) die 2 "sync_sdk.py --check 退出码 $rc" ;;
esac

python3 tools/websync/sync_sdk.py --manifest "$MANIFEST" || die 2 "sync_sdk.py 写入失败"
[[ -z "$(gofmt -l .)" ]] || die 4 "gofmt: $(gofmt -l . | tr '\n' ' ')"
go build ./... || die 4 "go build 失败"
go vet ./... || die 4 "go vet 失败"
go test -race -count=1 ./... >/tmp/auto_sync_test.$$ 2>&1 || { tail -40 /tmp/auto_sync_test.$$; rm -f /tmp/auto_sync_test.$$; die 4 "go test 失败"; }
rm -f /tmp/auto_sync_test.$$

git add -A
git -c user.name="${GIT_AUTHOR_NAME:-xweb-ops auto-sync}" -c user.email="${GIT_AUTHOR_EMAIL:-auto-sync@users.noreply.github.com}" \
  commit -q -m "chore(web): sync x-web GraphQL bindings to xweb-ops snapshot $SNAP" || die 3 "git commit 失败"
echo "COMMIT: $(git log --oneline -1)"
git --no-pager diff --stat "origin/$DEFAULT"...HEAD

if [[ "$DRY_RUN" == 1 ]]; then
  echo "DRY_RUN: 检查通过；会推送 $BRANCH 并开 / 更新 PR（未推送）"
  exit 0
fi

git push -q --force-with-lease origin "HEAD:refs/heads/$BRANCH" || die 3 "git push 失败"
gh label create "$LABEL" --color 0E8A16 --description "xweb-ops 自动同步" >/dev/null 2>&1 || true
BODY="自动同步：把 \`internal/clientprofile/web_chrome144.go\` 的 XOps 生成区同步到 [xweb-ops](https://github.com/Robin528919/xweb-ops) 清单快照 \`$SNAP\`。

由 \`monitor/auto_sync_sdk.sh\` 生成：基于最新 \`$DEFAULT\`，gofmt / build / vet / \`go test -race ./...\` 已通过。
新 queryId 在真机验收前标为「置信度=未验证」；auto 模式下若失效会按 HTTP 404 回退旧 op。**请人工审查后合并，脚本从不合并。**"
url=$(existing_pr)
if [[ -n "$url" ]]; then
  num=${url##*/}
  nwo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
  gh api -X PATCH "repos/$nwo/pulls/$num" -f title="chore(web): sync x-web GraphQL bindings ($SNAP)" -f body="$BODY" >/dev/null
else
  url=$(gh pr create --base "$DEFAULT" --head "$BRANCH" --title "chore(web): sync x-web GraphQL bindings ($SNAP)" --body "$BODY" --label "$LABEL" 2>/dev/null \
        || gh pr create --base "$DEFAULT" --head "$BRANCH" --title "chore(web): sync x-web GraphQL bindings ($SNAP)" --body "$BODY")
fi
echo "PR_URL: $url"
