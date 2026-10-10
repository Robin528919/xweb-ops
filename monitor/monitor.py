#!/usr/bin/env python3
"""x.com WEB client API change monitor (logged-out, public resources only).

Usage:
  python3 monitor.py run            # fetch -> snapshot -> diff vs previous -> print summary / NO_CHANGE
  python3 monitor.py fetch          # fetch + snapshot only
  python3 monitor.py diff [A B]     # diff two snapshots (default: previous vs latest)
  python3 monitor.py sdk            # full SDK-vs-web comparison report for latest snapshot
  python3 monitor.py list [keyword] # list ops in latest snapshot

Output contract for `run` / `diff`:
  first stdout line is one of:  NO_CHANGE | CHANGED | BASELINE
  exit code: 0 on success (changed or not), 2 on fetch/extraction error ("FETCH_ERROR: ..." on stderr+stdout).
  `--status-exit` makes CHANGED exit 10 (NO_CHANGE/BASELINE stay 0).
  Logged-in client check (1 request to x.com/home with the cookie file; values never printed):
    if the logged-in page switched client since last run, an extra FIRST line
    `LOGGED_IN_CLIENT_CHANGED: old->xweb` precedes NO_CHANGE/CHANGED (exit 10 with --status-exit);
    otherwise a LAST line `LOGGED_IN_CLIENT: old|xweb|unknown` or `LOGGED_IN_CHECK_SKIPPED: <reason>`.
    Cookie file: $XWEB_COOKIE_FILE / $TWITTER_WEB_COOKIE_FILE (env only; unset -> skipped). `--no-login-check` disables.
  Machine-readable result: data/diffs/latest_diff.json  ({"status": ..., "changed": bool, ...})
"""
import argparse, concurrent.futures as cf, datetime as dt, glob, hashlib, json, os, re, sys, time
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    print("FETCH_ERROR: python 'requests' not installed (pip install requests)", file=sys.stderr)
    sys.exit(2)

# 仓库根目录（状态都写在这里）；可用 XWEB_OPS_DIR 覆盖。JS 缓存默认 <root>/cache（已 gitignore），可用 XWEB_OPS_CACHE 覆盖。
ROOT = os.environ.get("XWEB_OPS_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
SNAP_DIR = os.path.join(DATA_DIR, "snapshots")
DIFF_DIR = os.path.join(DATA_DIR, "diffs")
CACHE_DIR = os.path.join(os.environ.get("XWEB_OPS_CACHE") or os.path.join(ROOT, "cache"), "js")
SDK_FILE = os.path.join(ROOT, "sdk", "sdk_endpoints.json")
MANIFEST_FILE = os.path.join(ROOT, "xweb-ops.json")
TZ = dt.timezone(dt.timedelta(hours=8))  # Asia/Singapore

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
PRIMARY_SEEDS = ["https://x.com/", "https://x.com/home", "https://twitter.com/", "https://x.com/i/flow/login"]
EXTRA_SEEDS = ["https://x.com/XDevelopers"]  # profile page SSR pulls a few more entry modules (best-effort)
SCRIPT_RE = re.compile(r'https://abs\.twimg\.com/(?:x-web/x-web|responsive-web/client-web(?:-legacy)?)/[A-Za-z0-9_./~@+-]+?\.js')
MAX_FILES = 6000

TRACKED_FIELDS = ["can_dm", "follow_request_sent", "profile_interstitial_type"]
# substrings probed in raw JS each run (presence = still referenced by web JS)
EXTRA_PROBES = ["ondemand.s", "responsive-web/client-web", "x-client-transaction-id", "twitter-site-verification",
                "loading-x-anim", "/i/api/graphql", "api.x.com/graphql", "featureSwitches", "fieldToggles"]

# ---------------------------------------------------------------- categories
CAT_ORDER = ["follow", "tweet", "dm", "account", "user", "other"]
CAT_ZH = {"follow": "关注/关系", "tweet": "帖子/推文/时间线", "dm": "私信 DM/XChat",
          "account": "账号设置 AccountSettings", "user": "用户资料", "other": "其他"}

def is_dm_name(name):
    return bool(re.search(r"(^|[a-z_])(Dm|DM)([A-Z_]|$)|^dm[A-Z_]|DirectMessage|direct_message|Inbox|inbox|XChat|xchat|xChat|^[Cc]hat[A-Z]|Message(s)?(Query|Mutation|Request|Event|Page|Timeline)|[Mm]essageRequest|SendMessage|^Conversation(?!Control)[A-Z]|GetConversation(?!Control)|ConnectTab|GetConnectPage|GroupConversation|GroupInvite|GroupJoin|FrankedMessage|WelcomeMessage", name))

def op_category(name):
    n = name.lower()
    if re.search(r"follow|friendship", n):
        return "follow"
    if is_dm_name(name):
        return "dm"
    if re.search(r"tweet|post|retweet|repost|like|favorit|favourit|timeline|bookmark|quote|repl(y|ies)|compose|conversationcontrol", n):
        return "tweet"
    if re.search(r"account|setting", n):
        return "account"
    if re.search(r"user", n):
        return "user"
    return "other"

def rest_category(path):
    p = path.lower()
    if re.search(r"friendship|follow", p): return "follow"
    if re.search(r"statuses|favorites|tweet|retweet|/media/|timeline|bookmark", p): return "tweet"
    if re.search(r"/dm/|direct_messages|inbox|conversation|xchat", p): return "dm"
    if "account/" in p or "settings" in p: return "account"
    if "/users/" in p or "user" in p: return "user"
    return "other"

def op_tags(name):
    tags = []
    if name.startswith("UserTweets") or name in ("UserRepliesTimeline", "UserOriginalsTimeline"):
        tags.append("UserTweets分页")
    if re.search(r"accountsettings|account_settings|settings", name, re.I):
        tags.append("AccountSettings")
    return tags

# ---------------------------------------------------------------- http
class FetchError(Exception):
    pass

_session = None
def session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session

def http_get(url, retries=3, timeout=30, accept=None):
    last = None
    for attempt in range(retries):
        try:
            h = {"Accept": accept} if accept else None
            r = session().get(url, timeout=timeout, headers=h, allow_redirects=True)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code} for {url}"
            if r.status_code in (403, 404, 410):
                break  # not worth retrying
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e} for {url}"
        time.sleep(1.5 * (attempt + 1))
    raise FetchError(last or f"failed {url}")

# ---------------------------------------------------------------- discovery & crawl
def parse_initial_data(html):
    i = html.find("window.__INITIAL_DATA__=")
    if i < 0:
        return {}
    try:
        d, _ = json.JSONDecoder().raw_decode(html[i + len("window.__INITIAL_DATA__="):])
        return d
    except Exception:
        return {}

def discover():
    errors, seeds_used, scripts, info = [], [], [], {}
    for url in PRIMARY_SEEDS:
        try:
            r = http_get(url, accept=HEADERS["Accept"])
        except FetchError as e:
            errors.append(str(e)); continue
        found = sorted(set(SCRIPT_RE.findall(r.text)))
        if not found:
            errors.append(f"no abs.twimg.com client scripts in HTML of {url} (final {r.url}, {len(r.text)} bytes) — blocked/changed?")
            continue
        seeds_used.append(url); scripts += found
        m = re.search(r'data-app-version="([0-9a-f]+)"', r.text) or re.search(r'name="app-version" content="([^"]+)"', r.text)
        init = parse_initial_data(r.text)
        info = {"html_url": url, "final_url": r.url, "app_version": m.group(1) if m else None,
                "initial_data_app_metadata": init.get("appMetadata"),
                "feature_switches_logged_out": (init.get("featureSwitchPayload") or {}).get("features"),
                "feature_switch_settings_version": (init.get("featureSwitchPayload") or {}).get("settingsVersion"),
                "has_twitter_site_verification": "twitter-site-verification" in r.text,
                "loading_x_anim_frames": len(re.findall(r'id="loading-x-anim-\d"', r.text))}
        break
    if not scripts:
        raise FetchError("x.com HTML unavailable or contains no client JS. Tried: " + " | ".join(errors))
    for url in EXTRA_SEEDS:
        try:
            r = http_get(url, accept=HEADERS["Accept"], retries=2)
            extra = sorted(set(SCRIPT_RE.findall(r.text)))
            if extra:
                scripts += extra; seeds_used.append(url)
        except FetchError as e:
            errors.append(f"(non-fatal) {e}")
    info["seeds_used"] = seeds_used
    info["seed_errors"] = errors
    return sorted(set(scripts)), info

REL_IMPORT_RE = re.compile(r'["\'`](\.{1,2}/[A-Za-z0-9_./~@+-]+?\.js)["\'`]')
LOCALE_IMPORT_RE = re.compile(r'"\.\./messages/[\w-]+\.json":\(\)=>\w+\(\(\)=>import\(`\./([\w.~-]+\.js)`\)')
LEGACY_NAME_RE = re.compile(r'(\d+):"([\w.~-]+)"')
LEGACY_HASH_RE = re.compile(r'(\d+):"([0-9a-f]{7,10})"')

def cache_path(url):
    base = os.path.basename(urlparse(url).path)
    return os.path.join(CACHE_DIR, hashlib.sha1(url.encode()).hexdigest()[:10] + "-" + base)

def fetch_js(url):
    p = cache_path(url)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        os.utime(p, None)
        with open(p, encoding="utf-8", errors="replace") as f:
            return url, f.read(), True
    r = http_get(url, accept="*/*")
    txt = r.text
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(txt)
    os.replace(tmp, p)
    return url, txt, False

def crawl(roots):
    texts, skip, failed = {}, set(), {}
    todo = list(roots)
    cached_hits = 0
    with cf.ThreadPoolExecutor(16) as ex:
        while todo:
            batch = [u for u in dict.fromkeys(todo) if u not in texts and u not in skip and u not in failed]
            todo = []
            if not batch:
                break
            if len(texts) + len(batch) > MAX_FILES:
                raise FetchError(f"module graph exploded (> {MAX_FILES} files) — aborting")
            futs = {ex.submit(fetch_js, u): u for u in batch}
            for fu in cf.as_completed(futs):
                u = futs[fu]
                try:
                    _, txt, hit = fu.result()
                except Exception as e:
                    failed[u] = str(e); continue
                cached_hits += hit
                texts[u] = txt
                for m in LOCALE_IMPORT_RE.findall(txt):
                    skip.add(urljoin(u, "./" + m))
                for rel in REL_IMPORT_RE.findall(txt):
                    if "/messages/" in rel:
                        continue
                    nu = urljoin(u, rel)
                    if nu.startswith("https://abs.twimg.com/") and nu not in texts and nu not in skip:
                        todo.append(nu)
                if "/responsive-web/client-web" in u:  # legacy webpack client fallback (best-effort)
                    names = dict(LEGACY_NAME_RE.findall(txt)); hashes = dict(LEGACY_HASH_RE.findall(txt))
                    basedir = u.rsplit("/", 1)[0] + "/"
                    for cid, h in hashes.items():
                        nm = names.get(cid)
                        if nm and not re.fullmatch(r"[0-9a-f]+", nm):
                            todo.append(f"{basedir}{nm}.{h}a.js")
    crit = [u for u in failed if u in roots]
    if crit or (failed and len(failed) > 0.05 * max(1, len(texts))):
        raise FetchError(f"failed to fetch {len(failed)} JS files (e.g. {list(failed.items())[:3]})")
    return texts, failed, cached_hits

# ---------------------------------------------------------------- extraction
Q = r'[`"\']'
RELAY_PARAMS_RE = re.compile(
    r'params:\{id:`([A-Za-z0-9_-]+)`,metadata:(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}),name:`(\w+)`,operationKind:`(\w+)`,text:null'
    r'(?:,providedVariables:\{([^{}]*)\})?\}')
RELAY_HASH_RE = re.compile(r'\s*\}\}\)\(\);\s*[\w$]+\.hash=`([0-9a-f]{32})`')
STORED_RE = re.compile(r'\{id:' + Q + r'([A-Za-z0-9_-]{20,24})' + Q + r',name:' + Q + r'(\w+)' + Q + r'\}')
LEGACY_OP_RE = re.compile(
    r'queryId:' + Q + r'([A-Za-z0-9_-]+)' + Q + r',operationName:' + Q + r'(\w+)' + Q + r',operationType:' + Q + r'(\w+)' + Q +
    r',metadata:\{featureSwitches:\[([^\]]*)\],fieldToggles:\[([^\]]*)\]')
LOCALARG_RE = re.compile(r'kind:`LocalArgument`,name:`(\w+)`')
FIELD_RE = re.compile(r'kind:`(?:Scalar|Linked)Field`,name:`(\w+)`')
PV_RE = re.compile(r'(__relay_internal__pv__\w+)\s*:')
REST_RE = re.compile(r'(?:(?<=[`"\'])|https://((?:api|upload|caps|jf|mobile|grok|ton|money)\.(?:x|twitter)\.com|x\.com|twitter\.com))'
                     r'(/(?:1\.1|2|i/api|i/jfapi|i/media|onboarding)/(?:[A-Za-z0-9_.\-/:]|\$\{[^}`]{0,120}\})+)')
FS_NAMES_RE = re.compile(r'`([a-z0-9_]+(?:\.[a-z0-9_]+){20,})`\.split\(`\.`\)')
FS_PAIR_RE = re.compile(r'(\w+):(!0|!1|-?\d+(?:\.\d+)?|`[^`]*`|"[^"]*"|null|\[[^\]]*\])')
HASH_SUFFIX_RE = re.compile(r'-[A-Za-z0-9_-]{8}\.js$')

def module_name(url):
    base = os.path.basename(urlparse(url).path)
    return HASH_SUFFIX_RE.sub(".js", base)

def pv_to_flag(pv):
    s = pv.replace("__relay_internal__pv__", "")
    return s[:-len("relayprovider")] if s.endswith("relayprovider") else s

def strlist(s):
    return sorted(set(re.findall(r'[`"\']([\w.-]+)[`"\']', s)))

def extract(texts, sdk):
    graphql, rest, tracked = {}, {}, {f: {"raw_count": 0, "selection_count": 0, "ops": set(), "modules": set()} for f in TRACKED_FIELDS}
    probes_terms = set(EXTRA_PROBES)
    rest_probe_res = {}
    if sdk:
        for side in ("web", "android"):
            for n, o in sdk.get(side, {}).get("graphql", {}).items():
                probes_terms.add(n); probes_terms.add(o["queryId"]); probes_terms.update(o.get("features", {}).keys())
                probes_terms.update(o.get("fieldToggles", {}).keys())
            for r in sdk.get(side, {}).get("rest", []):
                rest_probe_res["rest:" + r["path"]] = re.compile(re.escape(r["path"]) + r"(?![\w/.-])")
    probes = {t: set() for t in probes_terms}
    probes.update({k: set() for k in rest_probe_res})
    signer = []
    fs_defaults = None

    def add_op(name, rec, mod):
        cur = graphql.get(name)
        if cur is None:
            rec["modules"] = {mod}; graphql[name] = rec
            return
        cur["modules"].add(mod)
        if cur["source"] == "stored" and rec["source"] == "relay":
            # prefer the Relay artifact; keep the stored-operation id as an alternate
            rec["modules"] = cur["modules"]
            alts = set(cur.get("alt_queryIds", set())) | {cur["queryId"]}
            alts.discard(rec["queryId"])
            if alts: rec["alt_queryIds"] = alts
            graphql[name] = rec
            return
        if cur["queryId"] != rec["queryId"]:
            cur.setdefault("alt_queryIds", set()).add(rec["queryId"])
        elif cur.get("paramsOnly") and not rec.get("paramsOnly"):
            rec["modules"] = cur["modules"]
            if cur.get("alt_queryIds"): rec["alt_queryIds"] = cur["alt_queryIds"]
            graphql[name] = rec  # prefer the full Relay artifact over a bare params reference

    for url, t in sorted(texts.items()):
        mod = module_name(url)
        if "sign.o" in mod or "ondemand.s" in mod:
            signer.append(url)
        prev_end = 0
        for m in RELAY_PARAMS_RE.finditer(t):
            qid, meta, name, kind, pv = m.groups()
            k = t.rfind("fragment:{argumentDefinitions", prev_end, m.start())
            params_only = k < 0 or t.find("kind:`Request`", k, m.start()) < 0
            if params_only:
                block = ""
            else:
                st = t.rfind("(function(){", prev_end, k)
                if st < 0 or k - st > 200000:
                    st = k
                block = t[st:m.end()]
            hm = RELAY_HASH_RE.match(t, m.end())
            fields = sorted(set(FIELD_RE.findall(block)))
            pvs = sorted(set(PV_RE.findall(pv or "")) | set(a for a in LOCALARG_RE.findall(block) if a.startswith("__relay_internal__pv__")))
            rec = {"queryId": qid, "operationType": kind, "source": "relay",
                   "featureSwitches": sorted(set(pv_to_flag(p) for p in pvs)),
                   "fieldToggles": [],
                   "variables": sorted(set(a for a in LOCALARG_RE.findall(block) if not a.startswith("__relay_internal__pv__"))),
                   "relayHash": hm.group(1) if hm else None,
                   "fieldCount": len(fields),
                   "fieldsHash": hashlib.sha1(",".join(fields).encode()).hexdigest()[:12],
                   "trackedFields": [f for f in TRACKED_FIELDS if f in fields]}
            if meta not in ("{}",):
                rec["metadata"] = meta
            if params_only:
                rec["paramsOnly"] = True
                for k_ in ("relayHash", "fieldCount", "fieldsHash"): rec.pop(k_, None)
            add_op(name, rec, mod)
            for f in rec["trackedFields"]:
                tracked[f]["ops"].add(name)
            prev_end = m.end()
        for m in STORED_RE.finditer(t):
            qid, name = m.groups()
            if name in graphql and graphql[name]["source"] == "relay":
                if graphql[name]["queryId"] != qid:
                    graphql[name].setdefault("alt_queryIds", set()).add(qid)
                continue
            kind = "mutation" if "Mutation" in name or name.endswith("Mutate") else "query"
            add_op(name, {"queryId": qid, "operationType": kind, "operationTypeGuessed": True, "source": "stored",
                          "featureSwitches": [], "fieldToggles": [], "variables": [], "trackedFields": []}, mod)
        for m in LEGACY_OP_RE.finditer(t):
            qid, name, kind, fs, ft = m.groups()
            add_op(name, {"queryId": qid, "operationType": kind, "source": "legacy-webpack",
                          "featureSwitches": strlist(fs), "fieldToggles": strlist(ft), "variables": [], "trackedFields": []}, mod)
        for m in REST_RE.finditer(t):
            host, path = m.group(1), m.group(2)
            path = re.sub(r"\$\{[^}]*\}", "{}", path).rstrip("/:")
            if len(path) < 5 or path in ("/i/api/graphql", "/i/api", "/i/jfapi") or path.count("/") < 2 and not path.endswith(".json"):
                continue
            e = rest.setdefault(path, {"hosts": set(), "modules": set()})
            e["modules"].add(mod)
            if host: e["hosts"].add(host)
        for mm in FS_NAMES_RE.finditer(t):
            cand = {"module": mod, "known_switches": sorted(mm.group(1).split(".")), "defaults": {}}
            tk = re.search(r",[\w$]+=`([0-9a-f]{40})`", t[mm.end():mm.end() + 200])
            if tk: cand["feature_set_token"] = tk.group(1)
            i = t.find("={", mm.end(), mm.end() + 400)
            j = t.find("}", i) if i > 0 else -1
            if i > 0 and j > i:
                for k_, v_ in FS_PAIR_RE.findall(t[i + 2:j]):
                    v_ = True if v_ == "!0" else False if v_ == "!1" else v_.strip("`\"") if v_[:1] in "`\"" else v_
                    cand["defaults"][k_] = v_
            score = (len(cand["defaults"]), len(cand["known_switches"]))
            if fs_defaults is None or score > (len(fs_defaults["defaults"]), len(fs_defaults["known_switches"])):
                fs_defaults = cand
        for f in TRACKED_FIELDS:
            c = t.count(f)
            if c:
                tracked[f]["raw_count"] += c; tracked[f]["modules"].add(mod)
                tracked[f]["selection_count"] += t.count("name:`%s`" % f)
        for term in probes_terms:
            if term in t:
                probes[term].add(mod)
        for term, rx in rest_probe_res.items():
            if rx.search(t):
                probes[term].add(mod)

    def fin(o):
        if isinstance(o, set): return sorted(o)
        if isinstance(o, dict): return {k: fin(v) for k, v in o.items()}
        if isinstance(o, list): return [fin(v) for v in o]
        return o
    for n, rec in graphql.items():
        rec["category"] = op_category(n)
        tg = op_tags(n)
        if tg: rec["tags"] = tg
    for p, rec in rest.items():
        rec["category"] = rest_category(p)
    return fin(graphql), fin(rest), fin(tracked), {k: sorted(v) for k, v in probes.items()}, sorted(set(signer)), fs_defaults

# ---------------------------------------------------------------- snapshot io
def now():
    return dt.datetime.now(TZ)

def load_sdk():
    if os.path.exists(SDK_FILE):
        with open(SDK_FILE) as f:
            return json.load(f)
    return None

def list_snapshots():
    return sorted(glob.glob(os.path.join(SNAP_DIR, "snapshot-*.json")))

def load(p):
    with open(p) as f:
        return json.load(f)

def prune_cache(days=10):
    if not os.path.isdir(CACHE_DIR): return
    cut = time.time() - days * 86400
    for p in glob.glob(os.path.join(CACHE_DIR, "*")):
        try:
            if os.path.getmtime(p) < cut: os.remove(p)
        except OSError:
            pass

def do_fetch():
    t0 = time.time()
    sdk = load_sdk()
    roots, info = discover()
    texts, failed, cached_hits = crawl(roots)
    graphql, rest, tracked, probes, signer, fs_defaults = extract(texts, sdk)
    if len(graphql) < 50:
        raise FetchError(f"extraction suspect: only {len(graphql)} GraphQL operations found in {len(texts)} JS files")
    ts = now()
    js_files = {}
    for u, t in sorted(texts.items()):
        js_files[u] = {"module": module_name(u), "size": len(t), "sha256": hashlib.sha256(t.encode("utf-8", "replace")).hexdigest()[:16]}
    types = {}
    for o in graphql.values():
        types[o["operationType"]] = types.get(o["operationType"], 0) + 1
    snap = {
        "schema": 1,
        "generated_at": ts.isoformat(timespec="seconds"),
        "meta": dict(info, client_build="x-web (Vite/Relay)" if any("/x-web/" in u for u in roots) else "responsive-web (webpack)",
                     root_scripts=roots, js_file_count=len(texts), js_total_bytes=sum(len(t) for t in texts.values()),
                     js_fetch_failed=failed, cache_hits=cached_hits, txid_signer_scripts=signer,
                     elapsed_s=round(time.time() - t0, 1)),
        "counts": {"graphql_total": len(graphql), "graphql_by_type": types,
                   "graphql_by_source": {s: sum(1 for o in graphql.values() if o["source"] == s) for s in {o["source"] for o in graphql.values()}},
                   "rest_paths": len(rest), "js_files": len(texts)},
        "js_files": js_files,                 # file URLs/hashes kept separate from API data
        "api": {"graphql": graphql, "rest": rest, "tracked_fields": tracked,
                "feature_switches_logged_out": info.get("feature_switches_logged_out"),
                "feature_switch_defaults": fs_defaults},
        "probes": probes,
    }
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = os.path.join(SNAP_DIR, "snapshot-" + ts.strftime("%Y%m%d-%H%M%S") + ".json")
    with open(path, "w") as f:
        json.dump(snap, f, indent=1, ensure_ascii=False, sort_keys=False)
    with open(os.path.join(SNAP_DIR, "latest.json"), "w") as f:
        json.dump(snap, f, indent=1, ensure_ascii=False)
    prune_cache()
    return path, snap

# ---------------------------------------------------------------- SDK comparison
def norm(n):
    return re.sub(r"(query|mutation)$", "", n.lower())

def sdk_compare(snap, sdk):
    """Per SDK op status vs current web snapshot."""
    if not sdk: return None
    g = snap["api"]["graphql"]; rest = snap["api"]["rest"]; probes = snap.get("probes", {})
    by_qid = {}
    for n, o in g.items():
        by_qid.setdefault(o["queryId"], []).append(n)
        for q in o.get("alt_queryIds", []): by_qid.setdefault(q, []).append(n)
    by_norm = {norm(n): n for n in g}
    out = {"web": {}, "android": {}, "rest": [], "web_sends_features": any(o.get("source") == "legacy-webpack" for o in g.values())}
    for side in ("web", "android"):
        for n, o in sdk.get(side, {}).get("graphql", {}).items():
            q = o["queryId"]
            r = {"sdk_queryId": q, "category": op_category(n)}
            if n in g:
                r["web_name"] = n; r["web_queryId"] = g[n]["queryId"]
                r["status"] = "same" if g[n]["queryId"] == q or q in g[n].get("alt_queryIds", []) else "changed"
            elif q in by_qid:
                r["status"] = "same_queryId_renamed"; r["web_name"] = by_qid[q][0]; r["web_queryId"] = q
            elif norm(n) in by_norm:
                wn = by_norm[norm(n)]; r["web_name"] = wn; r["web_queryId"] = g[wn]["queryId"]
                r["status"] = "same" if g[wn]["queryId"] == q else "changed(name-variant)"
            else:
                r["status"] = "removed_from_web" if side == "web" else "not_in_web"
            r["queryId_in_js"] = bool(probes.get(q))
            r["name_in_js"] = bool(probes.get(n))
            hints = [h for h in o.get("web_equivalent_hint", []) if h in g]
            if hints:
                r["web_equivalents"] = {h: {"queryId": g[h]["queryId"], "type": g[h]["operationType"],
                                            "variables": g[h].get("variables", []),
                                            "providedFlags": g[h].get("featureSwitches", [])} for h in hints}
            if side == "web":
                feats = list(o.get("features", {}).keys()); tog = list(o.get("fieldToggles", {}).keys())
                r["sdk_features"] = len(feats)
                r["sdk_features_absent_from_web_js"] = [f for f in feats if not probes.get(f)]
                r["sdk_fieldToggles_absent_from_web_js"] = [f for f in tog if not probes.get(f)]
                tgt = r.get("web_name") or (hints[0] if hints else None)
                if tgt and tgt in g:
                    r["web_required_flags"] = g[tgt].get("featureSwitches", [])
                    r["web_variables"] = g[tgt].get("variables", [])
                    sv = set(o.get("variables", []))
                    if sv and r["web_variables"]:
                        r["variables_web_only"] = sorted(set(r["web_variables"]) - sv)
                        r["variables_sdk_only"] = sorted(sv - set(r["web_variables"]))
            out[side][n] = r
    for side in ("web", "android"):
        for rr in sdk.get(side, {}).get("rest", []):
            p = rr["path"]
            tmpl = [k for k in rest if "{" in k and re.fullmatch(re.escape(k).replace(r"\{\}", r"[^/]+"), p)]
            present = p in rest or bool(tmpl) or bool(probes.get("rest:" + p))
            out["rest"].append({"side": side, "method": rr["method"], "host": rr["host"], "path": p,
                                "in_web_js": present, "category": rest_category(p)})
    return out

# ---------------------------------------------------------------- diff
SIG_KEYS = ["queryId", "operationType", "featureSwitches", "fieldToggles", "variables"]

def diff_snapshots(a, b, sdk):
    ga, gb = a["api"]["graphql"], b["api"]["graphql"]
    ra, rb = a["api"]["rest"], b["api"]["rest"]
    res = {"from": a["generated_at"], "to": b["generated_at"],
           "app_version": [a["meta"].get("app_version"), b["meta"].get("app_version")],
           "ops_added": [], "ops_removed": [], "ops_changed": [], "rest_added": [], "rest_removed": [],
           "tracked_fields_changed": [], "possible_renames": [], "info": {}}
    for n in sorted(set(gb) - set(ga)):
        res["ops_added"].append({"name": n, **{k: gb[n].get(k) for k in ("queryId", "operationType", "category", "variables", "featureSwitches")}})
    for n in sorted(set(ga) - set(gb)):
        res["ops_removed"].append({"name": n, **{k: ga[n].get(k) for k in ("queryId", "operationType", "category")}})
    for n in sorted(set(ga) & set(gb)):
        oa, ob = ga[n], gb[n]; ch = {"name": n, "category": ob.get("category")}
        if oa["queryId"] != ob["queryId"]: ch["queryId"] = [oa["queryId"], ob["queryId"]]
        if oa["operationType"] != ob["operationType"]: ch["operationType"] = [oa["operationType"], ob["operationType"]]
        for k in ("featureSwitches", "fieldToggles", "variables", "trackedFields", "alt_queryIds"):
            sa, sb = set(oa.get(k, [])), set(ob.get(k, []))
            if sa != sb: ch[k] = {"added": sorted(sb - sa), "removed": sorted(sa - sb)}
        if oa.get("fieldsHash") and ob.get("fieldsHash") and oa["fieldsHash"] != ob["fieldsHash"]:
            ch["selectionChanged"] = [oa.get("fieldCount"), ob.get("fieldCount")]
        if len(ch) > 2: res["ops_changed"].append(ch)
    added_q = {o["queryId"]: o["name"] for o in res["ops_added"]}
    for o in res["ops_removed"]:
        if o["queryId"] in added_q:
            res["possible_renames"].append([o["name"], added_q[o["queryId"]], o["queryId"]])
    res["rest_added"] = sorted(set(rb) - set(ra)); res["rest_removed"] = sorted(set(ra) - set(rb))
    ta, tb = a["api"].get("tracked_fields", {}), b["api"].get("tracked_fields", {})
    for f in TRACKED_FIELDS:
        oa_, ob_ = set(ta.get(f, {}).get("ops", [])), set(tb.get(f, {}).get("ops", []))
        pa, pb = ta.get(f, {}).get("raw_count", 0) > 0, tb.get(f, {}).get("raw_count", 0) > 0
        if oa_ != ob_ or pa != pb:
            res["tracked_fields_changed"].append({"field": f, "present": [pa, pb], "ops_added": sorted(ob_ - oa_), "ops_removed": sorted(oa_ - ob_)})
    fa, fb = a["api"].get("feature_switches_logged_out") or {}, b["api"].get("feature_switches_logged_out") or {}
    if fa != fb:
        res["info"]["feature_switches_logged_out"] = {"added": {k: fb[k] for k in fb if k not in fa},
                                                      "removed": sorted(k for k in fa if k not in fb),
                                                      "changed": {k: [fa[k], fb[k]] for k in fb if k in fa and fa[k] != fb[k]}}
    da_, db_ = (a["api"].get("feature_switch_defaults") or {}), (b["api"].get("feature_switch_defaults") or {})
    na_, nb_ = set(da_.get("known_switches", [])), set(db_.get("known_switches", []))
    va_, vb_ = da_.get("defaults", {}), db_.get("defaults", {})
    if na_ != nb_ or va_ != vb_:
        res["info"]["feature_switch_defaults"] = {"switches_added": sorted(nb_ - na_), "switches_removed": sorted(na_ - nb_),
                                                  "default_changed": {k: [va_.get(k), vb_.get(k)] for k in set(va_) | set(vb_) if va_.get(k) != vb_.get(k)}}
    ja, jb = set(a.get("js_files", {})), set(b.get("js_files", {}))
    res["info"]["js_files_added"] = len(jb - ja); res["info"]["js_files_removed"] = len(ja - jb)
    sa, sb = a["meta"].get("txid_signer_scripts", []), b["meta"].get("txid_signer_scripts", [])
    if sa != sb: res["info"]["txid_signer_scripts"] = [sa, sb]
    # SDK impact
    ca, cb = sdk_compare(a, sdk), sdk_compare(b, sdk)
    sdk_names, sdk_qids = set(), set()
    if sdk:
        for side in ("web", "android"):
            for n, o in sdk.get(side, {}).get("graphql", {}).items():
                sdk_names.add(n); sdk_qids.add(o["queryId"]); sdk_names.update(o.get("web_equivalent_hint", []))
    def mark(o):
        if o["name"] in sdk_names or (isinstance(o.get("queryId"), str) and o["queryId"] in sdk_qids) or \
           (isinstance(o.get("queryId"), list) and set(o["queryId"]) & sdk_qids):
            o["sdk_related"] = True
    for lst in (res["ops_added"], res["ops_removed"], res["ops_changed"]):
        for o in lst: mark(o)
    res["sdk_status_changes"] = []
    if ca and cb:
        for side in ("web", "android"):
            for n in cb[side]:
                x, y = ca[side].get(n, {}), cb[side][n]
                if (x.get("status"), x.get("web_queryId")) != (y.get("status"), y.get("web_queryId")):
                    res["sdk_status_changes"].append({"side": side, "sdk_op": n, "before": [x.get("status"), x.get("web_queryId")],
                                                       "after": [y.get("status"), y.get("web_queryId")]})
        ra_ = {(r["side"], r["path"]): r["in_web_js"] for r in ca["rest"]}
        for r in cb["rest"]:
            if ra_.get((r["side"], r["path"])) != r["in_web_js"]:
                res["sdk_status_changes"].append({"side": r["side"], "sdk_rest": r["path"], "in_web_js": [ra_.get((r["side"], r["path"])), r["in_web_js"]]})
    res["changed"] = bool(res["ops_added"] or res["ops_removed"] or res["ops_changed"] or res["rest_added"]
                          or res["rest_removed"] or res["tracked_fields_changed"] or res["sdk_status_changes"])
    res["status"] = "CHANGED" if res["changed"] else "NO_CHANGE"
    return res

def _sortkey(o):
    cat = o.get("category") or op_category(o["name"])
    return (0 if o.get("sdk_related") else 1, CAT_ORDER.index(cat) if cat in CAT_ORDER else 9, o["name"].lower())

def summarize_zh(d, max_other=25):
    L = []
    L.append(f"X 网页端接口变化  {d['from'][:16].replace('T',' ')} → {d['to'][:16].replace('T',' ')} (SGT)")
    av = d["app_version"]
    if av[0] != av[1]: L.append(f"构建版本 app_version: {str(av[0])[:10]} → {str(av[1])[:10]}")
    L.append(f"GraphQL：新增 {len(d['ops_added'])}，删除 {len(d['ops_removed'])}，变更 {len(d['ops_changed'])}；REST：新增 {len(d['rest_added'])}，删除 {len(d['rest_removed'])}")
    items = []
    for o in d["ops_added"]:
        items.append((o, f"＋ 新增 {o['name']} ({o['operationType']}, queryId {o['queryId']})" + (f" 变量: {', '.join(o['variables'][:8])}" if o.get('variables') else "")))
    for o in d["ops_removed"]:
        items.append((o, f"－ 删除 {o['name']} ({o['operationType']}, 原 queryId {o['queryId']})"))
    for o in d["ops_changed"]:
        parts = []
        if "queryId" in o: parts.append(f"queryId {o['queryId'][0]} → {o['queryId'][1]}")
        if "operationType" in o: parts.append(f"类型 {o['operationType'][0]} → {o['operationType'][1]}")
        for k, zh in (("variables", "变量"), ("featureSwitches", "features/开关"), ("fieldToggles", "fieldToggles"), ("trackedFields", "关注字段"), ("alt_queryIds", "备用queryId")):
            if k in o:
                s = []
                if o[k]["added"]: s.append("+" + ",".join(o[k]["added"]))
                if o[k]["removed"]: s.append("-" + ",".join(o[k]["removed"]))
                parts.append(f"{zh} {' '.join(s)}")
        if "selectionChanged" in o: parts.append(f"返回字段集变化({o['selectionChanged'][0]}→{o['selectionChanged'][1]} 个字段)")
        items.append((o, f"～ {o['name']}: " + "；".join(parts)))
    items.sort(key=lambda x: _sortkey(x[0]))
    cur = None; other_count = 0
    for o, line in items:
        cat = o.get("category") or op_category(o["name"])
        if cat != cur:
            cur = cat; L.append(f"【{CAT_ZH.get(cat, cat)}】")
        if cat == "other" and not o.get("sdk_related"):
            other_count += 1
            if other_count > max_other: continue
        tag = " ⚠SDK相关" if o.get("sdk_related") else ""
        tags = o.get("tags") or op_tags(o["name"])
        L.append("  " + line + tag + (f" [{'/'.join(tags)}]" if tags else ""))
    if other_count > max_other: L.append(f"  …其他类另有 {other_count - max_other} 项（见 JSON）")
    if d["possible_renames"]:
        L.append("【疑似改名（queryId 相同）】")
        for a_, b_, q in d["possible_renames"]: L.append(f"  {a_} → {b_} ({q})")
    if d["rest_added"] or d["rest_removed"]:
        L.append("【REST 路径】")
        for p in sorted(d["rest_added"], key=lambda p: (CAT_ORDER.index(rest_category(p)), p)): L.append(f"  ＋ {p}")
        for p in sorted(d["rest_removed"], key=lambda p: (CAT_ORDER.index(rest_category(p)), p)): L.append(f"  － {p}")
    if d["tracked_fields_changed"]:
        L.append("【User 字段 can_dm / follow_request_sent / profile_interstitial_type】")
        for t in d["tracked_fields_changed"]:
            L.append(f"  {t['field']}: JS 中出现 {t['present'][0]}→{t['present'][1]}；新增引用 op {t['ops_added'] or '-'}；移除 {t['ops_removed'] or '-'}")
    if d["sdk_status_changes"]:
        L.append("【对 SDK (go-twitter-api) 的影响】")
        for s in d["sdk_status_changes"]:
            if "sdk_op" in s:
                L.append(f"  [{s['side']}] {s['sdk_op']}: {s['before'][0]}({s['before'][1]}) → {s['after'][0]}({s['after'][1]})")
            else:
                L.append(f"  [{s['side']}] REST {s['sdk_rest']}: 在网页 JS 中 {s['in_web_js'][0]} → {s['in_web_js'][1]}")
    sdk_hits = [o for o, _ in items if o.get("sdk_related")]
    if sdk_hits:
        L.append("SDK 影响提示：上面标 ⚠SDK相关 的接口与 SDK 使用的接口同名/同 queryId/为其网页等价接口；queryId 变化意味着 SDK 里写死的 persisted queryId 可能开始返回 404/\"Query not found\"，需要更新 internal/clientprofile/web_chrome144.go。")
    if d["info"].get("feature_switches_logged_out"):
        L.append(f"（信息）未登录 featureSwitch 默认值变化: {json.dumps(d['info']['feature_switches_logged_out'], ensure_ascii=False)[:400]}")
    if d["info"].get("feature_switch_defaults"):
        L.append(f"（信息）网页内置 feature switch 列表/默认值变化: {json.dumps(d['info']['feature_switch_defaults'], ensure_ascii=False)[:500]}")
    if d["info"].get("txid_signer_scripts"):
        L.append("（信息）x-client-transaction-id 签名脚本 (sign.o) 换了版本 — SDK txid 生成可能需复核")
    return "\n".join(L)

# ---------------------------------------------------------------- commands
def write_diff(d, text):
    os.makedirs(DIFF_DIR, exist_ok=True)
    stamp = d["to"][:19].replace(":", "").replace("-", "").replace("T", "-")
    if d["changed"]:
        with open(os.path.join(DIFF_DIR, f"diff-{stamp}.json"), "w") as f: json.dump(d, f, indent=1, ensure_ascii=False)
        with open(os.path.join(DIFF_DIR, f"diff-{stamp}.md"), "w") as f: f.write(text + "\n")
    with open(os.path.join(DIFF_DIR, "latest_diff.json"), "w") as f: json.dump(d, f, indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- logged-in client detection
# 登录态页面用的是旧 webpack 客户端（ondemand.s）还是 x-web（sign.o）。每次 run 只发 1 个请求；
# cookie 值绝不打印 / 落盘。cookie 文件格式：一行 `auth_token=...; ct0=...; twid=...`。
LOGIN_COOKIE_FILE = os.environ.get("XWEB_COOKIE_FILE") or os.environ.get("TWITTER_WEB_COOKIE_FILE") or ""  # 只从环境变量取
LOGIN_URL = "https://x.com/home"
LOGIN_STATE = os.path.join(DATA_DIR, "logged_in_client.json")

def classify_client(html):
    """返回 (client, facts)。client ∈ old | xweb | unknown。按实际加载的入口脚本判断
    （页面里别处出现 x-web 字样——如配置 / 预取提示——不算）。"""
    srcs = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https://abs\.twimg\.com/[^"]+\.js)"', html)
    facts = {
        "entry_xweb": any("/x-web/" in u for u in srcs),
        "entry_client_web": any("/responsive-web/client-web" in u for u in srcs),
        "ondemand_s_ref": bool(re.search(r"ondemand\.s", html)),
        "sign_o_ref": bool(re.search(r"sign\.o[-.][A-Za-z0-9_-]+\.js", html)),
        "xweb_mentioned": "abs.twimg.com/x-web/" in html,
        "site_verification": 'name="twitter-site-verification"' in html,
    }
    if facts["entry_xweb"] or (facts["sign_o_ref"] and not facts["entry_client_web"]):
        client = "xweb"
    elif facts["entry_client_web"]:
        client = "old"
    else:
        client = "unknown"
    return client, facts

def logged_in_check():
    """返回 dict：status ∈ OK | SKIPPED；OK 时带 client / previous / changed。从不抛异常。"""
    if not LOGIN_COOKIE_FILE:
        return {"status": "SKIPPED", "reason": "XWEB_COOKIE_FILE not set"}
    try:
        with open(LOGIN_COOKIE_FILE) as f:
            cookie = f.read().strip()
    except OSError:
        return {"status": "SKIPPED", "reason": "cookie file missing"}
    if "auth_token=" not in cookie:
        return {"status": "SKIPPED", "reason": "cookie file has no auth_token"}
    try:
        r = requests.get(LOGIN_URL, headers={**HEADERS, "Cookie": cookie}, timeout=30, allow_redirects=True)
    except requests.RequestException as e:
        return {"status": "SKIPPED", "reason": f"request failed: {type(e).__name__}"}
    finally:
        cookie = None
    final = urlparse(r.url).path
    if r.status_code != 200:
        return {"status": "SKIPPED", "reason": f"HTTP {r.status_code}"}
    if "/login" in final or "/i/flow/login" in final or "/logout" in final:
        return {"status": "SKIPPED", "reason": "cookie expired (redirected to login)"}
    html = r.text
    if '"isLoggedIn":false' in html or ('"user_id"' not in html and '"screen_name"' not in html and "twid" not in html and "isLoggedIn" not in html):
        # 只认得出登录态时才下结论
        if '"isLoggedIn":true' not in html:
            return {"status": "SKIPPED", "reason": "page not logged-in (cookie expired?)"}
    client, facts = classify_client(html)
    prev = None
    try:
        with open(LOGIN_STATE) as f:
            prev = json.load(f).get("client")
    except (OSError, ValueError):
        pass
    res = {"status": "OK", "client": client, "previous": prev, "facts": facts, "url": LOGIN_URL,
           "changed": prev is not None and prev != client, "at": now().isoformat(timespec="seconds")}
    if client != "unknown":
        os.makedirs(ROOT, exist_ok=True)
        with open(LOGIN_STATE, "w") as f:
            json.dump({k: res[k] for k in ("client", "facts", "url", "at")}, f, ensure_ascii=False, indent=1)
    return res

def login_lines(res):
    """(首行前缀列表, 末尾信息列表)。"""
    if res["status"] == "SKIPPED":
        return [], [f"LOGGED_IN_CHECK_SKIPPED: {res['reason']}"]
    if res["changed"]:
        return [f"LOGGED_IN_CLIENT_CHANGED: {res['previous']}->{res['client']}"], []
    return [], [f"LOGGED_IN_CLIENT: {res['client']}"]

def attach_login(res):
    p = os.path.join(DIFF_DIR, "latest_diff.json")
    try:
        with open(p) as f: d = json.load(f)
    except (OSError, ValueError):
        return
    d["logged_in_client"] = res
    with open(p, "w") as f: json.dump(d, f, ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- xweb-ops.json manifest (schema 1)
# 公开清单：只收 SDK 用到的 x-web op。内容（ops / snapshot）不变时不重写，generated_at 保持不变。
MANIFEST_OPS = ["UserByScreenName", "UserRepliesTimeline", "bookmarkButtonAddMutation", "followUserMutation",
                "followersQuery", "followingQuery", "intentFollowUserByRestIdQuery", "likeButtonFavoriteMutation"]
# Relay provided variable → 取值：("const", v) 固定；("fs", feature switch, 默认值)。
PROVIDERS = {
    "xclientsfeaturesappviewerisloggedin": ("const", True),
    "xclientsfeaturestranslationnoteautotranslationenabled":
        ("fs", "responsive_web_grok_community_note_auto_translation_is_enabled", True),
}

def build_manifest(snap):
    fs = (snap.get("meta") or {}).get("feature_switches_logged_out") or {}
    ops = {}
    for name in MANIFEST_OPS:
        o = snap["api"]["graphql"].get(name)
        if not o:
            continue
        entry = {"query_id": o["queryId"], "type": o.get("operationType"), "variables": sorted(o.get("variables") or [])}
        pv = {}
        for flag in o.get("featureSwitches") or []:
            rule = PROVIDERS.get(flag)
            if rule is None:
                raise FetchError(f"unknown Relay provided variable {flag} on {name}; register it in PROVIDERS")
            val = rule[1] if rule[0] == "const" else fs.get(rule[1], rule[2])
            pv[f"__relay_internal__pv__{flag}relayprovider"] = val
        if pv:
            entry["provided_variables"] = pv
        ops[name] = entry
    app = (snap.get("meta") or {}).get("app_version") or ""
    return {"schema": 1, "snapshot": app[:10], "ops": ops}

def write_manifest(snap):
    """返回 True 表示清单内容有变化并已重写。"""
    new = build_manifest(snap)
    try:
        with open(MANIFEST_FILE) as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = None
    if old and {k: old.get(k) for k in ("schema", "snapshot", "ops")} == new:
        return False
    new["generated_at"] = now().isoformat(timespec="seconds")
    with open(MANIFEST_FILE, "w") as f:
        json.dump(new, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    return True

def cmd_run(args):
    rc, lines = _cmd_run(args)
    try:
        latest_snap = load(os.path.join(SNAP_DIR, "latest.json"))
        if write_manifest(latest_snap):
            lines.append("MANIFEST_UPDATED: xweb-ops.json")
    except (OSError, ValueError, FetchError, KeyError) as e:
        print(f"manifest not updated: {e}", file=sys.stderr)
    if getattr(args, 'no_login_check', False):
        login = {'status': 'SKIPPED', 'reason': 'disabled (--no-login-check)'}
    else:
        login = logged_in_check()
    head, tail = login_lines(login)
    for l in head + lines + tail: print(l)
    attach_login(login)
    if login.get('changed') and getattr(args, 'status_exit', False) and rc == 0:
        rc = 10
    return rc

def _cmd_run(args):
    out = []
    try:
        path, snap = do_fetch()
    except FetchError as e:
        msg = f"FETCH_ERROR: {e}"
        out.append(msg); print(msg, file=sys.stderr)
        os.makedirs(DIFF_DIR, exist_ok=True)
        with open(os.path.join(DIFF_DIR, "latest_diff.json"), "w") as f:
            json.dump({"status": "FETCH_ERROR", "changed": False, "error": str(e), "at": now().isoformat(timespec="seconds")}, f, ensure_ascii=False)
        return (2), out
    snaps = list_snapshots()
    prev = [p for p in snaps if p != path]
    if not prev:
        out.append("BASELINE")
        out.append(baseline_report(snap, load_sdk()))
        with open(os.path.join(DIFF_DIR if os.makedirs(DIFF_DIR, exist_ok=True) is None else DIFF_DIR, "latest_diff.json"), "w") as f:
            json.dump({"status": "BASELINE", "changed": False, "snapshot": path}, f)
        return (0), out
    old = load(prev[-1])
    # sanity: a collapse in op count is almost certainly a partial fetch, not a real removal
    if len(snap["api"]["graphql"]) < 0.6 * len(old["api"]["graphql"]):
        os.rename(path, path + ".suspect")
        msg = (f"FETCH_ERROR: extraction suspect — {len(snap['api']['graphql'])} ops now vs {len(old['api']['graphql'])} before; "
               f"snapshot quarantined as {os.path.basename(path)}.suspect")
        out.append(msg); print(msg, file=sys.stderr)
        with open(os.path.join(SNAP_DIR, "latest.json"), "w") as f: json.dump(old, f, indent=1, ensure_ascii=False)
        return (2), out
    d = diff_snapshots(old, snap, load_sdk())
    text = summarize_zh(d) if d["changed"] else ""
    write_diff(d, text)
    if not d["changed"]:
        os.remove(path)  # identical API surface: keep only the previous snapshot (js hashes are in latest.json)
        out.append("NO_CHANGE")
        out.append(f"(GraphQL {snap['counts']['graphql_total']} / REST {snap['counts']['rest_paths']} / JS {snap['counts']['js_files']}; "
              f"js files +{d['info'].get('js_files_added',0)}/-{d['info'].get('js_files_removed',0)})")
        return (0), out
    out.append("CHANGED"); out.append(text)
    return (10 if args.status_exit else 0), out

def cmd_fetch(args):
    try:
        path, snap = do_fetch()
    except FetchError as e:
        print(f"FETCH_ERROR: {e}"); return 2
    print(path); print(json.dumps(snap["counts"], ensure_ascii=False)); return 0

def cmd_diff(args):
    if args.a and args.b:
        a, b = load(args.a), load(args.b)
    else:
        s = list_snapshots()
        if len(s) < 2: print("NO_CHANGE\n(less than two snapshots)"); return 0
        a, b = load(s[-2]), load(s[-1])
    d = diff_snapshots(a, b, load_sdk())
    if args.json: print(json.dumps(d, indent=1, ensure_ascii=False)); return 0
    print(d["status"])
    if d["changed"]: print(summarize_zh(d))
    return 10 if (args.status_exit and d["changed"]) else 0

def latest():
    p = os.path.join(SNAP_DIR, "latest.json")
    if not os.path.exists(p): print("no snapshot yet; run `monitor.py run` first"); sys.exit(2)
    return load(p)

def ops_table(g, cats, limit=None):
    rows = sorted(((n, o) for n, o in g.items() if o["category"] in cats), key=lambda x: (CAT_ORDER.index(x[1]["category"]), x[0].lower()))
    return [f"  {n:48s} {o['operationType']:9s} {o['queryId']}" + (" [stored, type guessed]" if o.get("operationTypeGuessed") else "") for n, o in rows[:limit]]

def baseline_report(snap, sdk):
    g = snap["api"]["graphql"]; c = snap["counts"]; L = []
    L.append(f"基线快照 {snap['generated_at']}  构建 {snap['meta'].get('client_build')}  app_version {snap['meta'].get('app_version')}")
    L.append(f"GraphQL 操作 {c['graphql_total']} 个 {c['graphql_by_type']}（来源 {c['graphql_by_source']}），REST 路径 {c['rest_paths']} 条，JS 文件 {c['js_files']} 个")
    L.append("【关注/关系】"); L += ops_table(g, {"follow"})
    L.append("【帖子/推文/时间线】"); L += ops_table(g, {"tweet"})
    L.append("【私信】"); L += (ops_table(g, {"dm"}) or ["  (网页 JS 中没有 DM GraphQL 操作)"])
    L.append("【账号设置】"); L += ops_table(g, {"account"})
    tf = snap["api"]["tracked_fields"]
    L.append("【User 字段】")
    for f in TRACKED_FIELDS:
        L.append(f"  {f}: JS 出现 {tf[f]['raw_count']} 次，在 {len(tf[f]['ops'])} 个 op 的返回字段里: {', '.join(tf[f]['ops'][:12])}")
    return "\n".join(L)

def cmd_list(args):
    s = latest(); g = s["api"]["graphql"]
    for n in sorted(g, key=lambda n: (CAT_ORDER.index(g[n]["category"]), n.lower())):
        if args.keyword and args.keyword.lower() not in n.lower(): continue
        o = g[n]
        print(f"{o['category']:8s} {n:50s} {o['operationType']:9s} {o['queryId']}  vars={','.join(o.get('variables', []))}")
    return 0

def cmd_sdk(args):
    s = latest(); sdk = load_sdk()
    if not sdk: print("sdk_endpoints.json missing"); return 2
    c = sdk_compare(s, sdk)
    if args.json: print(json.dumps(c, indent=1, ensure_ascii=False)); return 0
    L = [f"SDK {sdk['sdk']}@{sdk['commit'][:7]} vs 网页 {s['generated_at']} (app_version {str(s['meta'].get('app_version'))[:10]})"]
    for side in ("web", "android"):
        st = {}
        for r in c[side].values(): st[r["status"]] = st.get(r["status"], 0) + 1
        L.append(f"== {side}: {len(c[side])} 个 op，状态统计 {st}")
        rows = sorted(c[side].items(), key=lambda x: (CAT_ORDER.index(x[1]["category"]), x[0].lower()))
        for n, r in rows:
            if side == "android" and r["status"] == "not_in_web" and not args.all: continue
            line = f"  [{CAT_ZH[r['category']]}] {n}: SDK {r['sdk_queryId']} → {r['status']}"
            if r.get("web_queryId"): line += f" (web {r.get('web_name')} {r['web_queryId']})"
            if r.get("web_equivalents"):
                line += "；网页等价: " + ", ".join(f"{h} {v['queryId']}" for h, v in r["web_equivalents"].items())
            if side == "web":
                line += f"；SDK 发 {r['sdk_features']} 个 features，其中 {len(r['sdk_features_absent_from_web_js'])} 个在网页 JS 中已不存在"
                if r.get("web_required_flags"): line += f"；网页该 op 的 provided 开关: {', '.join(r['web_required_flags'])}"
                if r.get("variables_web_only") is not None: line += f"；变量 网页多 {r['variables_web_only']} / SDK 多 {r['variables_sdk_only']}"
            L.append(line)
        if side == "android" and not args.all:
            L.append(f"  （其余 {sum(1 for r in c['android'].values() if r['status']=='not_in_web')} 个 Android op 在网页 JS 中不存在，用 --all 查看）")
    L.append("== REST")
    for r in c["rest"]:
        L.append(f"  [{r['side']}] {r['method']} {r['host']}{r['path']}: {'网页 JS 仍引用' if r['in_web_js'] else '网页 JS 中未出现'}")
    print("\n".join(L)); return 0

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--status-exit", action="store_true"); r.add_argument("--no-login-check", action="store_true")
    sp.add_parser("fetch")
    d = sp.add_parser("diff"); d.add_argument("a", nargs="?"); d.add_argument("b", nargs="?"); d.add_argument("--json", action="store_true"); d.add_argument("--status-exit", action="store_true")
    s = sp.add_parser("sdk"); s.add_argument("--json", action="store_true"); s.add_argument("--all", action="store_true")
    l = sp.add_parser("list"); l.add_argument("keyword", nargs="?")
    a = ap.parse_args()
    return {"run": cmd_run, "fetch": cmd_fetch, "diff": cmd_diff, "sdk": cmd_sdk, "list": cmd_list}[a.cmd](a)

if __name__ == "__main__":
    sys.exit(main())
