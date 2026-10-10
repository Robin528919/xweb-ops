#!/usr/bin/env python3
"""用本仓库的 xweb-ops.json 同步 go-twitter-api 的 Web GraphQL 绑定（转发到该仓库的 tools/websync/sync_sdk.py）。

需要环境变量 GO_TWITTER_API_REPO 指向 go-twitter-api 的本地 checkout。其余参数原样转发（如 --check）。
"""
import os, subprocess, sys

ROOT = os.environ.get("XWEB_OPS_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
repo = os.environ.get("GO_TWITTER_API_REPO")
if not repo:
    sys.exit("set GO_TWITTER_API_REPO to the go-twitter-api checkout")
script = os.path.join(repo, "tools", "websync", "sync_sdk.py")
args = sys.argv[1:]
if "--manifest" not in open(script).read():
    sys.exit(f"{script} 还不支持 --manifest（需要 go-twitter-api 合入读清单的 sync_sdk.py）")
if "--manifest" not in args:
    args += ["--manifest", os.environ.get("XWEB_OPS_MANIFEST") or os.path.join(ROOT, "xweb-ops.json")]
sys.exit(subprocess.call([sys.executable, script, "--repo", repo, *args]))
