import html
import json
import os
import pathlib
import re
import urllib.request
from datetime import datetime
from typing import Any, Optional


HTB_USER_ID = "378794"
PROFILE_URL = f"https://app.hackthebox.com/public/users/{HTB_USER_ID}"

OUT_SVG = pathlib.Path("assets/htb-card.svg")
OUT_DEBUG = pathlib.Path("assets/htb-debug.json")

BASIC_ENDPOINT = f"https://labs.hackthebox.com/api/v4/user/profile/basic/{HTB_USER_ID}"
PROLAB_ENDPOINT = "https://labs.hackthebox.com/api/v4/prolabs"
FORTRESS_ENDPOINT = "https://labs.hackthebox.com/api/v4/fortresses"
CHALLENGE_LIST_ENDPOINT = "https://labs.hackthebox.com/api/v4/challenge/list"

# Season endpoints are still elusive. We probe a wider set across multiple HTB domains.
SEASON_CANDIDATES = [
    # labs.*
    "https://labs.hackthebox.com/api/v4/seasons",
    "https://labs.hackthebox.com/api/v4/season",
    "https://labs.hackthebox.com/api/v4/seasons/me",
    "https://labs.hackthebox.com/api/v4/season/me",
    "https://labs.hackthebox.com/api/v4/seasons/current",
    "https://labs.hackthebox.com/api/v4/season/current",
    f"https://labs.hackthebox.com/api/v4/seasons/profile/{HTB_USER_ID}",
    f"https://labs.hackthebox.com/api/v4/season/profile/{HTB_USER_ID}",
    "https://labs.hackthebox.com/api/v4/competitive/seasons",
    "https://labs.hackthebox.com/api/v4/competitive/season",
    "https://labs.hackthebox.com/api/v4/seasonal",
    "https://labs.hackthebox.com/api/v4/seasonal/me",
    f"https://labs.hackthebox.com/api/v4/user/{HTB_USER_ID}/seasons",
    f"https://labs.hackthebox.com/api/v4/user/seasons/{HTB_USER_ID}",
    # app.*
    "https://app.hackthebox.com/api/v4/seasons",
    "https://app.hackthebox.com/api/v4/seasons/me",
    "https://app.hackthebox.com/api/v4/seasons/current",
    # www.*
    "https://www.hackthebox.com/api/v4/seasons",
    "https://www.hackthebox.com/api/v4/seasons/me",
    "https://www.hackthebox.com/api/v4/seasons/current",
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


def try_json(url: str, token: str) -> tuple[bool, Any, str]:
    try:
        return True, fetch_json(url, token), ""
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"


def walk(obj: Any):
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
    # direct list
    if isinstance(payload, list) and payload and all(isinstance(x, dict) for x in payload):
        return payload

    # common wrappers
    if isinstance(payload, dict):
        for k in ("data", "items", "result", "list", "labs", "entries"):
            v = payload.get(k)
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return v
            if isinstance(v, dict):
                for kk in ("data", "items", "list", "labs", "entries"):
                    vv = v.get(kk)
                    if isinstance(vv, list) and vv and all(isinstance(x, dict) for x in vv):
                        return vv

    # deep fallback: first list of dicts containing a name/title
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

        # completion fields seen across HTB payloads
        fields = [
            it.get("ownership"),
            it.get("progress"),
            it.get("percentage"),
            it.get("completion"),
            it.get("completed"),
            it.get("isCompleted"),
            it.get("is_completed"),
        ]

        pct_val = None
        for f in fields:
            if isinstance(f, bool):
                pct_val = 100.0 if f else 0.0
                break
            try:
                if f is not None:
                    pct_val = float(f)
                    break
            except Exception:
                continue

        if name and pct_val is not None and pct_val >= 100.0:
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


def probe_first_working(token: str, urls: list[str]) -> tuple[Optional[str], Any, list[str]]:
    errs: list[str] = []
    for u in urls:
        ok, payload, err = try_json(u, token)
        if ok:
            return u, payload, errs
        errs.append(f"{u} -> {err}")
    return None, None, errs


def find_season_fields(payload: Any) -> tuple[str, str, str]:
    rk = pts = None
    flags_solved = flags_total = None

    for node in walk(payload):
        if not isinstance(node, dict):
            continue
        rk = rk or node.get("seasonRank") or node.get("season_rank") or node.get("seasonalRanking") or node.get("ranking") or node.get("rank")
        pts = pts or node.get("seasonPoints") or node.get("season_points") or node.get("points") or node.get("score")
        flags_solved = flags_solved or node.get("flags") or node.get("flagsOwned") or node.get("solvedFlags")
        flags_total = flags_total or node.get("flagsTotal") or node.get("totalFlags") or node.get("maxFlags")

    season_rank = fmt_num(rk)
    season_points = fmt_num(pts)
    season_flags = "—/—"
    if flags_solved is not None and flags_total is not None:
        season_flags = fmt_counter(flags_solved, flags_total)

    return season_rank, season_points, season_flags


def wrap_names(names: list[str], max_chars: int = 92) -> list[str]:
    """
    Wrap a list of names into multiple lines of roughly max_chars length.
    """
    if not names:
        return ["—"]

    lines: list[str] = []
    cur = ""
    for name in names:
        chunk = name if cur == "" else f"{cur} · {name}"
        if len(chunk) <= max_chars:
            cur = chunk
        else:
            lines.append(cur if cur else name)
            cur = name
    if cur:
        lines.append(cur)
    return lines


def svg_card(base: dict[str, Any], extras: dict[str, Any]) -> str:
    W = 1080
    pad = 28

    name = base.get("name") or "Hack The Box"
    rank = base.get("rank") or "—"
    points = fmt_num(base.get("points"))
    global_rank = fmt_num(base.get("ranking"))
    user_owns = fmt_num(base.get("user_owns"))
    system_owns = fmt_num(base.get("system_owns"))
    respects = fmt_num(base.get("respects"))

    challenges = extras.get("challenges", "—/—")
    prolabs = extras.get("prolabs", "—/—")
    fortresses = extras.get("fortresses", "—/—")

    season_rank = extras.get("season_rank", "—")
    season_points = extras.get("season_points", "—")
    season_flags = extras.get("season_flags", "—/—")

    completed_lines = wrap_names(extras.get("completed", []), max_chars=98)

    # Dynamic height based on completed lines
    base_h = 320
    per_line = 18
    H = base_h + max(0, (len(completed_lines) - 1)) * per_line + 30

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    def esc(x: Any) -> str:
        return html.escape(str(x))

    scanlines = "\n".join(
        f'<rect x="0" y="{y}" width="{W}" height="1" fill="#00ff41" opacity="0.05"/>'
        for y in range(0, H, 4)
    )

    # Completed text lines
    y0 = 285
    completed_svg = []
    for i, line in enumerate(completed_lines):
        completed_svg.append(f'<text class="t s" x="{pad}" y="{y0 + i * per_line}">{esc(line)}</text>')
    completed_svg_str = "\n  ".join(completed_svg)

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

  <text class="t k" x="{pad}" y="195">PRO LABS</text>
  <text class="t v" x="{pad}" y="220">{esc(prolabs)}</text>

  <text class="t k" x="{pad+240}" y="195">FORTRESSES</text>
  <text class="t v" x="{pad+240}" y="220">{esc(fortresses)}</text>

  <text class="t k" x="{pad+480}" y="195">SEASON</text>
  <text class="t v" x="{pad+480}" y="220">#{esc(season_rank)} · {esc(season_points)} pts · {esc(season_flags)} flags</text>

  <text class="t k" x="{pad}" y="265">COMPLETED PRO LABS</text>
  {completed_svg_str}

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
        "challenges": {},
        "season_probe": {},
        "extras": {},
    }

    # BASIC
    ok, base_payload, err = try_json(BASIC_ENDPOINT, token)
    debug["basic"] = {"used": BASIC_ENDPOINT, "ok": ok, "error": err}
    if not ok or not isinstance(base_payload, dict):
        OUT_DEBUG.write_text(json.dumps(debug, indent=2), encoding="utf-8")
        raise SystemExit("Failed to fetch basic profile payload.")
    base = base_payload.get("profile") if isinstance(base_payload.get("profile"), dict) else base_payload

    extras: dict[str, Any] = {
        "prolabs": "—/—",
        "fortresses": "—/—",
        "completed": [],
        "challenges": "—/—",
        "season_rank": "—",
        "season_points": "—",
        "season_flags": "—/—",
    }

    # PROLABS
    ok, payload, err = try_json(PROLAB_ENDPOINT, token)
    debug["prolabs"] = {"used": PROLAB_ENDPOINT, "ok": ok, "error": err}
    if ok:
        items = extract_list(payload)
        if items:
            done, total, comp = extract_done_total_from_list(items)
            extras["prolabs"] = fmt_counter(done, total)
            extras["completed"] = merge_unique(extras["completed"], comp)

    # FORTRESSES
    ok, payload, err = try_json(FORTRESS_ENDPOINT, token)
    debug["fortresses"] = {"used": FORTRESS_ENDPOINT, "ok": ok, "error": err}
    if ok:
        items = extract_list(payload)
        if items:
            done, total, _ = extract_done_total_from_list(items)
            extras["fortresses"] = fmt_counter(done, total)

    # CHALLENGES (active counter; you confirmed 23/188 and it looks right)
    ok, payload, err = try_json(CHALLENGE_LIST_ENDPOINT, token)
    debug["challenges"] = {"used": CHALLENGE_LIST_ENDPOINT, "ok": ok, "error": err}
    if ok:
        items = extract_list(payload)
        if items:
            total = len(items)
            solved = sum(
                1
                for it in items
                if isinstance(it, dict)
                and (
                    it.get("solved") is True
                    or it.get("isSolved") is True
                    or it.get("completed") is True
                    or it.get("isCompleted") is True
                )
            )
            extras["challenges"] = fmt_counter(solved, total)

    # SEASON PROBE (still hunting)
    used, season_payload, errs = probe_first_working(token, SEASON_CANDIDATES)
    debug["season_probe"] = {"used": used, "errors": errs}
    if used and season_payload is not None:
        sr, sp, sf = find_season_fields(season_payload)
        extras["season_rank"] = sr
        extras["season_points"] = sp
        extras["season_flags"] = sf

    debug["extras"] = extras
    OUT_DEBUG.write_text(json.dumps(debug, indent=2), encoding="utf-8")

    OUT_SVG.write_text(svg_card(base, extras), encoding="utf-8")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_DEBUG}")


if __name__ == "__main__":
    main()
