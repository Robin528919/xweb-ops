# xweb-ops

x.com web client (x-web, Relay persisted queries) GraphQL bindings, extracted from the public web JS bundle.

`xweb-ops.json` (schema 1):

| field | meaning |
| --- | --- |
| `schema` | format version (`1`) |
| `snapshot` | web build id the bindings were taken from |
| `generated_at` | generation time, RFC 3339 |
| `ops.<operationName>.query_id` | persisted query id |
| `ops.<operationName>.type` | `query` or `mutation` |
| `ops.<operationName>.variables` | variable names declared by the web client |
| `ops.<operationName>.provided_variables` | Relay provided variable values (`__relay_internal__pv__*`) |

Only publicly visible data is published here. Commit only when content changes.

## 仓库内容

```
monitor/monitor.py      网页端接口监控（不登录抓 x.com 公开 JS → 快照 → diff；可选登录态客户端检测）
monitor/sync_sdk.py     把最新快照同步进 go-twitter-api（转发到该仓库 tools/websync/sync_sdk.py）
data/snapshots/         接口快照（latest.json + 历史）
data/diffs/             每次变化的 diff（.json / .md）与 latest_diff.json
data/logged_in_client.json  登录态页面最近一次检测结果（old / xweb）
sdk/                    SDK 端点基线（sdk_endpoints.json 及其生成脚本）
txid/                   x-web sign.o（x-client-transaction-id）研究与离线复现工具
docs/                   监控说明、基线报告、SDK 对比基线
xweb-ops.json           对外清单（schema 1，见上），由 `monitor.py run` 重新生成；内容不变时不改写
```

## 运行

```bash
pip install requests
python3 monitor/monitor.py run                 # 第一行 NO_CHANGE / CHANGED / BASELINE / FETCH_ERROR: ...
python3 monitor/monitor.py run --status-exit   # 有变化（或登录态客户端变化）时退出码 10
```

环境变量（都可选）：

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `XWEB_OPS_DIR` | 状态目录（data/、sdk/、xweb-ops.json 所在） | 仓库根目录 |
| `XWEB_OPS_CACHE` | JS 缓存目录（约 300 MB，不入库） | `<仓库>/cache` |
| `XWEB_COOKIE_FILE` | 登录态检测用的 cookie 文件（一行 `auth_token=…; ct0=…`）。**只从环境变量读取**，值不会打印或落盘 | 未设置 → `LOGGED_IN_CHECK_SKIPPED` |
| `GO_TWITTER_API_REPO` | `monitor/sync_sdk.py` 用的 go-twitter-api checkout | 必填（仅 sync_sdk） |

输出约定详见 [docs/monitor.md](docs/monitor.md)。清单内容变化时 `run` 额外输出一行 `MANIFEST_UPDATED: xweb-ops.json`。
遇到未在 `PROVIDERS` 登记的 Relay provided variable 时，先按网页 JS 里的 provider 声明自动从 feature switch 取值（输出 `MANIFEST_WARNING: ... auto-resolved ...`，提示补登记）；仍解析不了的只跳过受影响的 op、沿用清单里上一条记录（`MANIFEST_WARNING: ... skipped ...`），其余 op 照常生成。

cookie、`secrets/`、`cache/`、`.env*` 均在 `.gitignore` 中，切勿提交。

## 同步到 go-twitter-api

```bash
GO_TWITTER_API_REPO=/path/to/go-twitter-api python3 monitor/sync_sdk.py --check   # 用本仓库 xweb-ops.json 检查
GO_TWITTER_API_REPO=/path/to/go-twitter-api monitor/auto_sync_sdk.sh [--dry-run]  # 定时自动同步
```

`monitor/auto_sync_sdk.sh`：在 go-twitter-api 最新默认分支的独立 worktree 里运行 `tools/websync/sync_sdk.py --manifest xweb-ops.json`；
无差异输出 `NO_DIFF`；有差异则 gofmt / build / vet / `go test -race ./...`，通过后强推 `auto/web-sync` 分支并新开或更新**唯一**一个
自动同步 PR（标签 `auto/web-sync`），输出 `PR_URL: …`。从不合并。退出码：0 正常，2 清单 / 同步错误，3 环境问题，4 检查失败（不推送）。
`--dry-run` 只做到本地提交。需要 go、gh（已登录）、python3。
