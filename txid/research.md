# x-web 的 x-client-transaction-id（sign.o）研究 — 2026-10-10

## 结论
**x-web 的 `sign.o-*.js` 与旧 webpack 的 `ondemand.s.*a.js` 是同一个算法**，只是被 obfuscator 重新混淆、换了加载方式。
离线执行 sign.o（node 20 + jsdom，固定 `Date.now` / 随机字节，Web Animations 按规范插值）得到的 txid，与 SDK
现有 `txid.go`（`newTxGen` + `idWith`）用同一页面输入算出的结果**逐字节相同**（2 个页面变体 × 2 个请求，4/4 一致）。

## 加载链
`x.com` 页面 → `<script type=module src=…/x-web/x-web/entry-client-*.js>` → 静态 import
`./assets/client-transaction-id-plugin-<hash>.js` → 首次需要时动态 `import("./sign.o-<hash>.js")`，
`(await mod.default())(path, METHOD)` 返回 txid（异常时返回 `btoa("e:"+err)`）。
plugin 只给 `api|jf|grok|mobile.(twitter|x).com`（不含 caps）的请求加头；`jf.x.com` 固定签 `("jf","PATCH")`。
入参 path 是 URL 的 pathname（去掉 query）。

## 输入（运行时实际访问）
- `document.querySelectorAll("[name^=tw]")` → `twitter-site-verification` meta 的 `content`（base64 → 48 字节 key）。
- `document.querySelectorAll(".r-govh28")` → 4 个 loading-x-anim SVG（顺序同 `loading-x-anim-0..3`），取被选帧里 path 的 `d`。
- `document.createElement("div")` + `el.animate({color:[c0,c1], transform:["rotate(0deg)","rotate(Xdeg)"], easing:"cubic-bezier(…)"}, 4096)`，
  `pause()`，`currentTime = t`，再 `getComputedStyle(el).color / .transform`。
- `crypto.subtle.digest("SHA-256", …)`、`Date.now()`、随机字节。访问了 `RTCPeerConnection`（返回 undefined 也不影响结果）。

## 算法（与 ondemand.s 相同）
1. key = base64decode(verification)；帧 = frames[key[5] % 4]；行 = key[row] % 16；动画时刻 = round(Π key[i] % 16 / 10) * 10。
2. animationKey = 颜色 hex + transform 矩阵各值的 hex（同 txid.go 的 `animate`）。
3. t = (now_ms - 1682924400000) / 1000；hash = sha256(`METHOD!path!t` + `obfiowerehiring` + animationKey)[:16]。
4. 明文 = key ‖ t(4 字节小端) ‖ hash ‖ 0x03；txid = base64(rnd ‖ 明文 XOR rnd)，去掉 `=`。

关键词 `obfiowerehiring`、纪元 1682924400、额外字节 3 都没变（digest 钩子直接看到明文输入）。

## 唯一变化：下标随版本轮换，但仍可正则提取
差分实验（逐字节改 key，看 animate 参数是否变）确认 sign.o-Oxxhj9hP 的 row=28、时刻下标 = [0,14,41]；
混淆代码里仍有字面量 `(e[28],16)(e[0],16)(e[14],16)(e[41],16)`，旧正则 `\(\w\[(\d{1,2})\],\s*16\)` 直接可用。
缓存里的 7 个 sign.o 版本下标各不相同（如 [4,32,23,45]、[7,14,1,6]、[34,0,41,9]），所以必须每次从当前 sign.o 读。

## 真机
- 登录态页面（/home、/messages）目前仍是旧客户端（入口 `responsive-web/client-web/main.*.js`，有 ondemand.s）；只有登出页是 x-web。
- 用「登录页 key/帧 + 当前 sign.o 下标」生成的 txid 读 `UserByScreenName`：200。
- **对照组**：故意用错的 animationKey，同一接口也 200 —— 这个读接口目前不严格校验 txid，所以真机通过不能证明算法正确；
  正确性的证据是上面的离线逐字节一致。没做写请求。

## 原型
分支 `feat/txid-signo`（基于 PR #22 分支）：`web.Options.TxSource` / `TWITTER_WEB_TXID_SOURCE` = `auto`（默认：页面有 ondemand.s 用它，否则走 x-web 入口 → plugin → sign.o）| `ondemand` | `signo`。
算法代码不变，只加了脚本发现；单测用离线执行 sign.o 得到的向量。

## 复现
`txid/tools/`：`run.mjs`（jsdom 执行器，`NOW` / `RND` / `TXMETHOD` / `TXPATH` 环境变量）、`sens.py`（下标差分）、`cases.json`、`mini.html`。
需要 `npm i jsdom@24`（在 `txid/tools/` 下执行，`node_modules/` 已 gitignore）；`run.mjs` 里的 jsdom 导入路径按需调整，sign.o 文件需自行下载为 `sign.mjs`。
`run.mjs` 默认读、`sens.py` 固定读的 `loggedout.html`，以及 `cases.json` 引用的 `case1.html`，是保存下来的 x.com 页面 HTML，不入库，需自行保存到 `txid/tools/`；两个脚本都在 `txid/tools/` 下执行。
