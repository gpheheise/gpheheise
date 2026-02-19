import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Iterable, Optional, Tuple


HTB_USER_ID = "378794"
PROFILE_URL = f"https://app.hackthebox.com/public/users/{HTB_USER_ID}"

OUT_SVG = pathlib.Path("assets/htb-card.svg")
OUT_DEBUG = pathlib.Path("assets/htb-debug.json")

BASIC_ENDPOINT = f"https://labs.hackthebox.com/api/v4/user/profile/basic/{HTB_USER_ID}"

# Working endpoints you already confirmed
PROLAB_ENDPOINT = "https://labs.hackthebox.com/api/v4/prolabs"
FORTRESS_ENDPOINT = "https://labs.hackthebox.com/api/v4/fortresses"

# Where we scrape JS bundle URLs from
PUBLIC_PAGE_URL = f"https://app.hackthebox.com/public/users/{HTB_USER_ID}"


def fetch_text(url: str, headers: Optional[dict[str, str]] = None) -> str:
    req = urllib.request.Request(
        url,
        headers=headers
        or {
            "User-Agent": "Mozilla/5.0 (GitHub Actions)",
            "Accept": "text/html,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_json(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (GitHub Actions)",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def try_json(url: str, token: str) -> tuple[bool, Any, str]:
    try:
        return True, fetch_json(url, token), ""
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"


def walk(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def fmt_num(x: Any) -> str:
    if x is None or isinstance(x, bool):
        return "—"
    if isinstance(x, (int, float)):
        if isinstance(x, float) and x.is_integer():
            x = int(x)
        return str(x)
    s = str(x).strip()
    m = re.search(r"[\d][\d,\.]*", s)
    return m.group(0) if m else (s if s else "—")


def fmt_counter(done: Any, total: Any) -> str:
    try:
        if done is None or total is None:
            return "—/—"
        return f"{int(float(done))}/{int(float(total))}"
    except Exception:
        return "—/—"


def extract_list(payload: Any) -> Optional[list[dict]]:
    if isinstance(payload, list) and payload and all(isinstance(x, dict) for x in payload):
        return payload
    if isinstance(payload, dict):
        # common shapes
        for k in ("data", "items", "result", "labs", "list"):
            v = payload.get(k)
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return v
            if isinstance(v, dict):
                for kk in ("labs", "items", "data", "list", "entries"):
                    vv = v.get(kk)
                    if isinstance(vv, list) and vv and all(isinstance(x, dict) for x in vv):
                        return vv
        # fallback: deepest list of dicts that looks like content
        for node in walk(payload):
            if isinstance(node, dict):
                for v in node.values():
                    if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                        sample = v[0]
                        if any(key in sample for key in ("name", "title")):
                            return v
    return None


def extract_done_total_from_list(items: list[dict]) -> tuple[int, int, list[str]]:
    total = len(items)
    done = 0
    completed_names: list[str] = []
    for it in items:
        name = it.get("name") or it.get("title")
        pct = it.get("ownership") or it.get("progress") or it.get("percentage") or it.get("completion")
        try:
            pct_f = float(pct) if pct is not None else None
        except Exception:
            pct_f = None
        if name and pct_f is not None and pct_f >= 100.0:
            done += 1
            completed_names.append(str(name))
    return done, total, completed_names


def merge_unique(a: list[str], b: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in a + b:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def discover_api_paths_from_js() -> tuple[list[str], dict[str, Any]]:
    """
    Download app.hackthebox.com public profile HTML,
    collect script src URLs, download a few chunks, scan for /api/v4/... strings.
    Returns discovered absolute URLs + debug info.
    """
    debug: dict[str, Any] = {"page_url": PUBLIC_PAGE_URL, "script_src": [], "scanned_scripts": [], "api_paths_found": []}

    page = fetch_text(PUBLIC_PAGE_URL)
    # collect JS script URLs
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', page, flags=re.IGNORECASE)
    # keep only next/static chunks and JS
    srcs = [s for s in srcs if s.endswith(".js")]
    # normalize
    abs_srcs = []
    for s in srcs:
        abs_srcs.append(urllib.parse.urljoin("https://app.hackthebox.com", s))
    debug["script_src"] = abs_srcs[:50]

    api_paths = set()

    # scan up to N scripts to keep runtime reasonable
    for s in abs_srcs[:12]:
        try:
            js = fetch_text(s, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
            debug["scanned_scripts"].append(s)
            # find occurrences like "/api/v4/...."
            for m in re.finditer(r'"/api/v4/[^"]+"', js):
                api_paths.add(m.group(0).strip('"'))
        except Exception:
            continue

    debug["api_paths_found"] = sorted(api_paths)

    # turn into absolute URLs (prefer labs.hackthebox.com and app.hackthebox.com)
    # We'll try both when probing.
    discovered = []
    for p in sorted(api_paths):
        discovered.append("https://labs.hackthebox.com" + p)
        discovered.append("https://app.hackthebox.com" + p)
    return discovered, debug


def pick_best_mini_prolabs(token: str, candidates: list[str], debug: dict[str, Any]) -> tuple[str, Any]:
    """
    Find an endpoint that returns a list containing 'mini' or 'pro' lab-like content.
    """
    for url in candidates:
        if not any(k in url.lower() for k in ("mini", "prolab", "pro-lab", "endgame", "lab")):
            continue
        ok, payload, err = try_json(url, token)
        if not ok:
            continue
        items = extract_list(payload)
        if items and len(items) >= 5:
            # heuristic: item looks like lab with name/title
            sample = items[0]
            if isinstance(sample, dict) and (("name" in sample) or ("title" in sample)):
                debug["mini_candidate_used"] = url
                return url, payload
    return "", None


def pick_best_challenges(token: str, candidates: list[str], debug: dict[str, Any]) -> tuple[str, Any]:
    """
    Find an endpoint that looks like challenges stats/list.
    """
    for url in candidates:
        if "challenge" not in url.lower():
            continue
        ok, payload, err = try_json(url, token)
        if not ok:
            continue
        # if it contains total/solved-ish keys or a big list
        solved = None
        total = None
        if isinstance(payload, dict):
            solved = payload.get("solved") or payload.get("completed") or payload.get("solvedChallenges")
            total = payload.get("total") or payload.get("totalChallenges")
        items = extract_list(payload)
        if (solved is not None and total is not None) or (items and len(items) > 100):
            debug["challenges_candidate_used"] = url
            return url, payload
    return "", None


def pick_best_season(token: str, candidates: list[str], debug: dict[str, Any]) -> tuple[str, Any]:
    """
    Find an endpoint that looks like seasonal ranking/stats.
    """
    for url in candidates:
        if not any(k in url.lower() for k in ("season", "competitive", "leaderboard", "ranking")):
            continue
        ok, payload, err = try_json(url, token)
        if not ok:
            continue
        # heuristics: contains rank/points/flags-ish keys
        if isinstance(payload, dict):
            if any(k in payload for k in ("seasonRank", "season_rank", "seasonalRanking", "ranking", "rank")):
                debug["season_candidate_used"] = url
                return url, payload
        # nested
        rk = None
        pts = None
        for node in walk(payload):
            if isinstance(node, dict):
                if rk is None:
                    rk = node.get("seasonRank") or node.get("season_rank") or node.get("seasonalRanking")
                if pts is None:
                    pts = node.get("seasonPoints") or node.get("season_points") or node.get("points")
        if rk is not None or pts is not None:
            debug["season_candidate_used"] = url
            return url, payload
    return "", None


def svg_card(base: dict[str, Any], extras: dict[str, Any]) -> str:
    W, H = 1080, 340
    pad = 28

    name = base.get("name") or base.get("username") or "Hack The Box"
    rank = base.get("rank") or "—"
    points = fmt_num(base.get("points"))
    global_rank = fmt_num(base.get("ranking"))
    user_owns = fmt_num(base.get("user_owns"))
    system_owns = fmt_num(base.get("system_owns"))
    respects = fmt_num(base.get("respects"))

    challenges = extras.get("challenges", "—/—")
    prolabs = extras.get("prolabs", "—/—")
    miniprolabs = extras.get("miniprolabs", "—/—")
    fortresses = extras.get("fortresses", "—/—")

    season_rank = extras.get("season_rank", "—")
    season_points = extras.get("season_points", "—")
    season_flags = extras.get("season_flags", "—/—")

    completed = extras.get("completed", [])
    completed_line = " · ".join(completed[:10]) if completed else "—"

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    def esc(x: Any) -> str:
        return html.escape(str(x))

    scanlines = "\n".join(
        f'<rect x="0" y="{y}" width="{W}" height="1" fill="#00ff41" opacity="0.05"/>'
        for y in range(0, H, 4)
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <style>
      .bg {{ fill: #000; }}
      .card {{ fill: #050a05; stroke: #00ff41; stroke-width: 1.2; }}
      .t {{ font-family: Consolas, Monaco, "Courier New", monospace; fill: #00ff41; }}
      .h {{ font-size: 22px; font-weight: 700; }}
      .s {{ font-size: 14px; opacity: 0.95; }}
      .k {{ font-size: 12px; opacity: 0.80; }}
      .v {{ font-size: 16px; font-weight: 700; }}
      .muted {{ opacity: 0.65; }}
    </style>
    <filter id="glow">
      <feGaussianBlur stdDeviation="1.2" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <rect class="bg" x="0" y="0" width="{W}" height="{H}"/>
  <rect class="card" x="14" y="14" rx="14" ry="14" width="{W-28}" height="{H-28}"/>
  {scanlines}

  <text class="t h" x="{pad}" y="55" filter="url(#glow)">{esc(name)}</text>
  <text class="t s muted" x="{pad}" y="78">{esc(rank)} · {esc(PROFILE_URL)}</text>

  <!-- Global stats -->
  <text class="t k" x="{pad}" y="120">POINTS</text>
  <text class="t v" x="{pad}" y="145">{esc(points)}</text>

  <text class="t k" x="{pad+170}" y="120">GLOBAL</text>
  <text class="t v" x="{pad+170}" y="145">#{esc(global_rank)}</text>

  <text class="t k" x="{pad+340}" y="120">USER OWNS</text>
  <text class="t v" x="{pad+340}" y="145">{esc(user_owns)}</text>

  <text class="t k" x="{pad+520}" y="120">SYSTEM OWNS</text>
  <text class="t v" x="{pad+520}" y="145">{esc(system_owns)}</text>

  <text class="t k" x="{pad+720}" y="120">RESPECTS</text>
  <text class="t v" x="{pad+720}" y="145">{esc(respects)}</text>

  <text class="t k" x="{pad+900}" y="120">CHALLENGES</text>
  <text class="t v" x="{pad+900}" y="145">{esc(challenges)}</text>

  <!-- Labs / Season -->
  <text class="t k" x="{pad}" y="195">PRO LABS</text>
  <text class="t v" x="{pad}" y="220">{esc(prolabs)}</text>

  <text class="t k" x="{pad+170}" y="195">MINI PRO LABS</text>
  <text class="t v" x="{pad+170}" y="220">{esc(miniprolabs)}</text>

  <text class="t k" x="{pad+400}" y="195">FORTRESSES</text>
  <text class="t v" x="{pad+400}" y="220">{esc(fortresses)}</text>

  <text class="t k" x="{pad+610}" y="195">SEASON</text>
  <text class="t v" x="{pad+610}" y="220">#{esc(season_rank)} · {esc(season_points)} pts · {esc(season_flags)} flags</text>

  <text class="t k" x="{pad}" y="265">COMPLETED</text>
  <text class="t s" x="{pad}" y="288">{esc(completed_line)}</text>

  <text class="t k muted" x="{pad}" y="{H-28}">updated {updated}</text>
</svg>
'''


def main() -> None:
    token = os.environ.get("HTB_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing HTB_TOKEN env var (set via GitHub Actions secret).")

    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    debug: dict[str, Any] = {
        "basic": {},
        "prolabs": {},
        "fortresses": {},
        "discovery": {},
        "mini": {},
        "challenges": {},
        "season": {},
    }

    # 1) Basic profile
    ok, base_payload, err = try_json(BASIC_ENDPOINT, token)
    debug["basic"]["used"] = BASIC_ENDPOINT
    debug["basic"]["ok"] = ok
    debug["basic"]["error"] = err
    if not ok or not isinstance(base_payload, dict):
        OUT_DEBUG.write_text(json.dumps(debug, indent=2), encoding="utf-8")
        raise SystemExit("Failed to fetch basic profile payload.")

    base = base_payload.get("profile") if isinstance(base_payload.get("profile"), dict) else base_payload

    extras: dict[str, Any] = {
        "prolabs": "—/—",
        "miniprolabs": "—/—",
        "fortresses": "—/—",
        "completed": [],
        "challenges": "—/—",
        "season_rank": "—",
        "season_points": "—",
        "season_flags": "—/—",
    }

    # 2) Prolabs
    ok, p, err = try_json(PROLAB_ENDPOINT, token)
    debug["prolabs"]["used"] = PROLAB_ENDPOINT
    debug["prolabs"]["ok"] = ok
    debug["prolabs"]["error"] = err
    if ok:
        items = extract_list(p)
        if items:
            done, total, comp = extract_done_total_from_list(items)
            extras["prolabs"] = fmt_counter(done, total)
            extras["completed"] = merge_unique(extras["completed"], comp)

    # 3) Fortresses
    ok, p, err = try_json(FORTRESS_ENDPOINT, token)
    debug["fortresses"]["used"] = FORTRESS_ENDPOINT
    debug["fortresses"]["ok"] = ok
    debug["fortresses"]["error"] = err
    if ok:
        items = extract_list(p)
        if items:
            done, total, comp = extract_done_total_from_list(items)
            extras["fortresses"] = fmt_counter(done, total)
            extras["completed"] = merge_unique(extras["completed"], comp)

    # 4) Discover endpoints from JS bundles
    discovered_urls, disc_dbg = discover_api_paths_from_js()
    debug["discovery"] = disc_dbg
    # keep candidates small
    discovered_urls = discovered_urls[:250]

    # 5) Mini Prolabs (discover)
    used, payload = pick_best_mini_prolabs(token, discovered_urls, debug["mini"])
    if used and payload is not None:
        items = extract_list(payload)
        if items:
            done, total, comp = extract_done_total_from_list(items)
            extras["miniprolabs"] = fmt_counter(done, total)
            extras["completed"] = merge_unique(extras["completed"], comp)

    # 6) Challenges (discover)
    used, payload = pick_best_challenges(token, discovered_urls, debug["challenges"])
    if used and payload is not None:
        # Try to get solved/total directly
        solved = None
        total = None
        if isinstance(payload, dict):
            solved = payload.get("solved") or payload.get("completed") or find_first(payload, {"solved", "completed", "solvedChallenges", "challengesSolved"})
            total = payload.get("total") or payload.get("totalChallenges") or find_first(payload, {"total", "totalChallenges", "challengesTotal"})
        if solved is None or total is None:
            # fallback: if it's a list of challenges, total is len(list), solved count by "solved" flag
            items = extract_list(payload)
            if items:
                total = len(items)
                solved = sum(1 for it in items if isinstance(it, dict) and (it.get("solved") is True or it.get("isSolved") is True))
        extras["challenges"] = fmt_counter(solved, total)

    # 7) Season (discover)
    used, payload = pick_best_season(token, discovered_urls, debug["season"])
    if used and payload is not None:
        # try a few key names
        rk = None
        pts = None
        flags_solved = None
        flags_total = None
        for node in walk(payload):
            if not isinstance(node, dict):
                continue
            rk = rk or node.get("seasonRank") or node.get("season_rank") or node.get("seasonalRanking") or node.get("ranking")
            pts = pts or node.get("seasonPoints") or node.get("season_points") or node.get("points") or node.get("score")
            flags_solved = flags_solved or node.get("flags") or node.get("flagsOwned") or node.get("solvedFlags")
            flags_total = flags_total or node.get("flagsTotal") or node.get("totalFlags") or node.get("maxFlags")
        extras["season_rank"] = fmt_num(rk)
        extras["season_points"] = fmt_num(pts)
        if flags_solved is not None and flags_total is not None:
            extras["season_flags"] = fmt_counter(flags_solved, flags_total)

    debug["extras"] = extras
    OUT_DEBUG.write_text(json.dumps(debug, indent=2), encoding="utf-8")

    OUT_SVG.write_text(svg_card(base, extras), encoding="utf-8")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_DEBUG}")


if __name__ == "__main__":
    main()
