import html
import json
import os
import pathlib
import re
import urllib.request
from datetime import datetime
from typing import Any, Iterable, Optional, Tuple


HTB_USER_ID = "378794"
PROFILE_URL = f"https://app.hackthebox.com/public/users/{HTB_USER_ID}"

OUT_SVG = pathlib.Path("assets/htb-card.svg")
OUT_DEBUG = pathlib.Path("assets/htb-debug.json")


# ✅ Known-good endpoint (you already have numbers from this)
BASIC_ENDPOINTS = [
    f"https://labs.hackthebox.com/api/v4/user/profile/basic/{HTB_USER_ID}",
]

# 🔎 Extra endpoints (best-effort, token-auth). We probe and parse what we can.
PROLAB_ENDPOINTS = [
    "https://www.hackthebox.com/api/v4/prolabs",
    "https://labs.hackthebox.com/api/v4/prolabs",
]

MINIPROLAB_ENDPOINTS = [
    "https://www.hackthebox.com/api/v4/minipro-labs",
    "https://www.hackthebox.com/api/v4/mini-prolabs",
    "https://www.hackthebox.com/api/v4/miniprolabs",
    "https://labs.hackthebox.com/api/v4/minipro-labs",
    "https://labs.hackthebox.com/api/v4/mini-prolabs",
    "https://labs.hackthebox.com/api/v4/miniprolabs",
]

FORTRESS_ENDPOINTS = [
    "https://www.hackthebox.com/api/v4/fortresses",
    "https://labs.hackthebox.com/api/v4/fortresses",
]

SEASON_ENDPOINTS = [
    "https://labs.hackthebox.com/api/v4/seasons/me",
    "https://labs.hackthebox.com/api/v4/season/me",
    f"https://labs.hackthebox.com/api/v4/seasons/profile/{HTB_USER_ID}",
    f"https://labs.hackthebox.com/api/v4/season/profile/{HTB_USER_ID}",
]


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


def try_first_json(urls: list[str], token: str) -> tuple[Optional[str], Any, list[str]]:
    errors: list[str] = []
    for u in urls:
        try:
            return u, fetch_json(u, token), errors
        except Exception as e:
            errors.append(f"{u} -> {type(e).__name__}: {e}")
    return None, None, errors


def walk(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def find_first(obj: Any, keys: set[str]) -> Any:
    for node in walk(obj):
        if isinstance(node, dict):
            for k in keys:
                if k in node and node[k] is not None:
                    return node[k]
    return None


def fmt_num(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
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


def extract_list(payload: Any) -> Optional[list[dict]]:
    """
    Find the most plausible list-of-dicts payload that contains lab-like objects.
    Common shapes:
      - {"data": [...]}
      - {"data": {"labs": [...]}}
      - {"items": [...]}
      - {"<something>": [...]}
    """
    if isinstance(payload, list) and payload and all(isinstance(x, dict) for x in payload):
        return payload

    if isinstance(payload, dict):
        for k in ("data", "items", "result", "labs", "list"):
            v = payload.get(k)
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return v
            if isinstance(v, dict):
                # nested list
                for kk in ("labs", "items", "data", "list", "entries"):
                    vv = v.get(kk)
                    if isinstance(vv, list) and vv and all(isinstance(x, dict) for x in vv):
                        return vv

        # last resort: search nested
        for node in walk(payload):
            if isinstance(node, dict):
                for v in node.values():
                    if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                        # Heuristic: must contain name/title fields
                        sample = v[0]
                        if any(key in sample for key in ("name", "title")):
                            return v
    return None


def merge_unique(a: list[str], b: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in a + b:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


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

    # Challenges shown on the profile page (e.g., 69/814)
    challenges_done = extras.get("challenges_done", "—")
    challenges_total = extras.get("challenges_total", "—")
    challenges = f"{challenges_done}/{challenges_total}" if challenges_done != "—" else "—/—"

    prolabs = extras.get("prolabs", "—/—")
    miniprolabs = extras.get("miniprolabs", "—/—")
    fortresses = extras.get("fortresses", "—/—")

    season_rank = extras.get("season_rank", "—")
    season_points = extras.get("season_points", "—")

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

  <text class="t k" x="{pad+610}" y="195">SEASON RANK</text>
  <text class="t v" x="{pad+610}" y="220">#{esc(season_rank)}</text>

  <text class="t k" x="{pad+820}" y="195">SEASON POINTS</text>
  <text class="t v" x="{pad+820}" y="220">{esc(season_points)}</text>

  <text class="t k" x="{pad}" y="265">COMPLETED (LABS)</text>
  <text class="t s" x="{pad}" y="288">{esc(completed_line)}</text>

  <text class="t k muted" x="{pad}" y="{H-28}">updated {updated}</text>
</svg>
'''


def main() -> None:
    token = os.environ.get("HTB_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing HTB_TOKEN env var (set via GitHub Actions secret).")

    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    debug: dict[str, Any] = {"basic": {}, "prolabs": {}, "miniprolabs": {}, "fortresses": {}, "season": {}}

    # 1) Basic profile
    used_basic, basic_payload, basic_errors = try_first_json(BASIC_ENDPOINTS, token)
    debug["basic"]["used"] = used_basic
    debug["basic"]["errors"] = basic_errors
    debug["basic"]["type"] = type(basic_payload).__name__ if basic_payload is not None else None

    if not isinstance(basic_payload, dict):
        OUT_DEBUG.write_text(json.dumps(debug, indent=2), encoding="utf-8")
        raise SystemExit("Failed to fetch basic profile payload.")

    base = basic_payload.get("profile") if isinstance(basic_payload.get("profile"), dict) else basic_payload

    extras: dict[str, Any] = {
        "prolabs": "—/—",
        "miniprolabs": "—/—",
        "fortresses": "—/—",
        "completed": [],
        "season_rank": "—",
        "season_points": "—",
        "challenges_done": "—",
        "challenges_total": "—",
    }

    # Challenges x/y often exist in the basic payload under different names
    # We try common keys and nested keys.
    ch_done = base.get("challenges") or find_first(basic_payload, {"challenges", "challengesSolved", "solvedChallenges"})
    ch_total = base.get("challenges_total") or find_first(basic_payload, {"challenges_total", "totalChallenges", "challengesTotal"})
    # Sometimes total is displayed as 814 but not present; this stays "—" if not found.
    extras["challenges_done"] = fmt_num(ch_done)
    extras["challenges_total"] = fmt_num(ch_total)

    # 2) ProLabs
    used, payload, errs = try_first_json(PROLAB_ENDPOINTS, token)
    debug["prolabs"]["used"] = used
    debug["prolabs"]["errors"] = errs
    debug["prolabs"]["type"] = type(payload).__name__ if payload is not None else None

    pro_list = extract_list(payload)
    if pro_list:
        done, total, comp = extract_done_total_from_list(pro_list)
        extras["prolabs"] = fmt_counter(done, total)
        extras["completed"] = merge_unique(extras["completed"], comp)

    # 3) Mini ProLabs
    used, payload, errs = try_first_json(MINIPROLAB_ENDPOINTS, token)
    debug["miniprolabs"]["used"] = used
    debug["miniprolabs"]["errors"] = errs
    debug["miniprolabs"]["type"] = type(payload).__name__ if payload is not None else None

    mini_list = extract_list(payload)
    if mini_list:
        done, total, comp = extract_done_total_from_list(mini_list)
        extras["miniprolabs"] = fmt_counter(done, total)
        extras["completed"] = merge_unique(extras["completed"], comp)

    # 4) Fortresses
    used, payload, errs = try_first_json(FORTRESS_ENDPOINTS, token)
    debug["fortresses"]["used"] = used
    debug["fortresses"]["errors"] = errs
    debug["fortresses"]["type"] = type(payload).__name__ if payload is not None else None

    fort_list = extract_list(payload)
    if fort_list:
        done, total, comp = extract_done_total_from_list(fort_list)
        extras["fortresses"] = fmt_counter(done, total)
        extras["completed"] = merge_unique(extras["completed"], comp)

    # 5) Season (best-effort)
    used, payload, errs = try_first_json(SEASON_ENDPOINTS, token)
    debug["season"]["used"] = used
    debug["season"]["errors"] = errs
    debug["season"]["type"] = type(payload).__name__ if payload is not None else None

    if payload is not None:
        # extract common patterns
        extras["season_rank"] = fmt_num(find_first(payload, {"seasonRank", "season_rank", "ranking", "rank"}))
        extras["season_points"] = fmt_num(find_first(payload, {"seasonPoints", "season_points", "points", "score"}))

    # Write debug (safe, does NOT include token)
    debug["base_keys"] = list(base.keys()) if isinstance(base, dict) else None
    debug["extras"] = extras
    OUT_DEBUG.write_text(json.dumps(debug, indent=2), encoding="utf-8")

    # Render SVG
    OUT_SVG.write_text(svg_card(base, extras), encoding="utf-8")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_DEBUG}")


if __name__ == "__main__":
    main()
