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

cookie、`secrets/`、`cache/`、`.env*` 均在 `.gitignore` 中，切勿提交。
