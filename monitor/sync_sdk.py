#!/usr/bin/env python3
"""把最新快照同步进 go-twitter-api 的 Web GraphQL 绑定（转发到该仓库的 tools/websync/sync_sdk.py）。

需要环境变量 GO_TWITTER_API_REPO 指向 go-twitter-api 的本地 checkout。
"""
import os, subprocess, sys

ROOT = os.environ.get("XWEB_OPS_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
repo = os.environ.get("GO_TWITTER_API_REPO")
if not repo:
    sys.exit("set GO_TWITTER_API_REPO to the go-twitter-api checkout")
args = sys.argv[1:]
if "--snapshot" not in args:
    args += ["--snapshot", os.path.join(ROOT, "data", "snapshots", "latest.json")]
if "--endpoints" not in args:
    args += ["--endpoints", os.path.join(ROOT, "sdk", "sdk_endpoints.json")]
sys.exit(subprocess.call([sys.executable, os.path.join(repo, "tools", "websync", "sync_sdk.py"), "--repo", repo, *args]))
