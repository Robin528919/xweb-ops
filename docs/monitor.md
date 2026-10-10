# monitor — x.com 网页端接口变化监控

不登录、只用公开资源（x.com HTML + abs.twimg.com 上的 JS），抓取 **x.com 网页客户端** 的 GraphQL / REST 接口清单，存快照并与上一版做 diff。不管 Android、不管官方 API。

## 运行

```bash
python3 monitor/monitor.py run            # 抓取 → 快照 → 与上一版 diff → 打印结果
python3 monitor/monitor.py run --status-exit   # 同上，但有变化时退出码 10
python3 monitor/monitor.py sdk            # 当前网页 vs SDK（go-twitter-api）逐 op 对比
python3 monitor/monitor.py sdk --all      # 含全部 Android op
python3 monitor/monitor.py list [关键字]   # 列出最新快照里的 op
python3 monitor/monitor.py diff [A.json B.json] [--json]
```
依赖：Python 3 + `requests`（已装）。

### 输出约定（给定时任务用）
* `run` 的 **第一行** 是 `NO_CHANGE` / `CHANGED` / `BASELINE` / `FETCH_ERROR: ...`。
* 退出码：0 = 正常（不论有无变化）；**2 = 抓取/解析失败**（x.com 被拦、JS 拉不下来、解析出的 op 数异常骤降）；加 `--status-exit` 时 CHANGED 返回 10。
* 机器可读结果：`diffs/latest_diff.json`（`status`、`changed` 字段）。有变化时另存 `diffs/diff-<时间>.json/.md`。
* 只有 JS 文件 hash 变了、接口没变 → `NO_CHANGE`（这次的快照会被丢弃，只保留上一版）。

## 当前（2026-10）x.com 网页端的结构 —— 与旧版不同
X 已把网页端从 webpack 的 `responsive-web/client-web/main.*.js` 迁到 **Vite + Relay 的 `x-web`**：
* 入口：`https://abs.twimg.com/x-web/x-web/entry-client-logged-out-<hash>.js`，模块是 ES module，脚本沿 `import`/`__vite__mapDeps` 递归抓取（约 2100 个文件、35 MB；语言包跳过）。
* GraphQL 定义不再是 `{queryId, operationName, operationType, metadata:{featureSwitches, fieldToggles}}`，而是 Relay 持久化查询：`params:{id, name, operationKind, providedVariables}`。脚本同时识别：
  * Relay 制品（`source: relay`）：queryId=id、operationType=operationKind、`featureSwitches` = providedVariables 里的特性开关（`__relay_internal__pv__xclientsfeatures…relayprovider` 去掉前后缀）、`variables` = 变量名、`fieldsHash/fieldCount` = 返回字段集、`trackedFields`；
  * 少量 `{id, name}` 形式的 stored operation（`source: stored`，类型按名字猜）；
  * 旧 webpack 格式（`source: legacy-webpack`，带 featureSwitches/fieldToggles）——若 X 回滚会自动识别（未经实测）。
* **网页端已不再发送 `features` / `fieldToggles` 参数**；对应信息改为 Relay provided variables + 运行时 feature switch。
* 顺带提取：REST 路径（`/1.1/…`、`/2/…`、`/i/media/…` 等）、HTML 内 `__INITIAL_DATA__` 的未登录 feature switch、`feature-switch-overrides` 模块里的内置开关列表与默认值、x-client-transaction-id 签名脚本（`sign.o-*.js`）。

## 文件
* `monitor.py` —— 唯一入口。
* `snapshots/snapshot-YYYYmmdd-HHMMSS.json`、`snapshots/latest.json` —— 快照。`js_files`（URL/hash/大小）与 `api`（graphql/rest/tracked_fields/feature switches）分开存。`probes` 记录 SDK 用到的 op 名/queryId/feature 名/REST 路径在网页 JS 里出现在哪些模块。
* `diffs/` —— diff 结果。
* `cache/js/` —— JS 缓存（文件名带 hash，不可变；10 天未用自动清理）。
* `sdk_endpoints.json` —— 从 `github.com/Robin528919/go-twitter-api`（commit 9d142e2）提取的 SDK 端点：web 8 个 GraphQL op（queryId/features/fieldToggles/变量/网页等价 op 提示）+ 7 个 REST、Android 374 个 GraphQL op + 15 个 REST。由 `sdk/build_sdk_endpoints.py` 生成（Android 表在 `sdk/android_1213_graphql.txt`）；SDK 更新后改这两个文件再跑一次生成脚本。每次 `run` 都会拿它对比，并在 diff 里标 `⚠SDK相关`、列出 SDK 状态变化。

## diff 内容与排序
新增/删除 op、queryId 变化、operationType 变化、featureSwitches(provided 开关)/fieldToggles/变量增删、返回字段集变化、疑似改名（同 queryId 换名）、REST 增删、`can_dm` / `follow_request_sent` / `profile_interstitial_type` 的出现情况变化。排序：SDK 相关 → 关注/关系 → 帖子/推文/时间线 → 私信 → 账号设置 → 用户资料 → 其他（其他类最多列 25 条）。feature switch 默认值/签名脚本变化只作为附加信息，不单独触发 CHANGED。

## 局限
* 只能看到 **未登录可达** 的 JS 模块图。目前它已包含登录后的大部分页面（首页时间线、发帖、关注、点赞、设置等），但 **私信（/i/chat，XChat）的代码不在这个模块图里**，网页端 DM 接口目前无法从公开资源监控。
* Relay 的 queryId 是查询文本的哈希：返回字段一变 queryId 就变，所以 queryId 变化频率会比旧版高。
* timeline 类 op 的返回字段部分放在共享的 normalization 模块里（`timeline_normalization.graphql.js` 等），`trackedFields` 的 op 列表只覆盖内联字段；字段是否还在 JS 中用 `tracked_fields.*.raw_count/modules` 判断。
* “网页 JS 中没有某个 SDK queryId” 只说明网页不再用它，**不等于服务端已拒绝**（旧 persisted query 可能仍可用）；需要真机请求确认。

### 登录态客户端检测（每次 `run` 1 个请求）

`run` 会用 cookie 文件（`$XWEB_COOKIE_FILE` / `$TWITTER_WEB_COOKIE_FILE` / 仅环境变量，未设置则跳过）请求一次 `https://x.com/home`，
按**实际加载的入口脚本**判断登录态页面是旧 webpack 客户端（`responsive-web/client-web` + `ondemand.s`）还是 x-web（`x-web/` 入口 / `sign.o-*.js`），
结果存 `logged_in_client.json`，也写进 `diffs/latest_diff.json` 的 `logged_in_client`。cookie 值不打印、不落盘。

* 与上次相比客户端变了：在 `NO_CHANGE` / `CHANGED` **之前**额外输出第一行 `LOGGED_IN_CLIENT_CHANGED: old->xweb`（`--status-exit` 时退出码 10）。
* 没变：最后一行 `LOGGED_IN_CLIENT: old|xweb|unknown`，第一行仍是原来的 `NO_CHANGE` / `CHANGED` / `BASELINE`。
* cookie 缺失 / 过期 / 请求失败：最后一行 `LOGGED_IN_CHECK_SKIPPED: <原因>`，不影响本次 run 的结果与退出码。
* `--no-login-check` 关闭检测。
