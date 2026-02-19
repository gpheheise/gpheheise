import html
import json
import os
import pathlib
import re
import urllib.request
import urllib.error
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

# ✅ Seasons endpoint you found
SEASON_RANKS_ENDPOINT = f"https://labs.hackthebox.com/api/v4/season/user/{HTB_USER_ID}/ranks"


def fetch_raw(url: str, token: str) -> tuple[int, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (GitHub Actions)",
            "Accept": "application/json,text/plain,*/*",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = getattr(r, "status", 200)
            ctype = r.headers.get("Content-Type", "")
            body = r.read().decode("utf-8", errors="replace")
            return status, ctype, body
    except urllib.error.HTTPError as e:
        ctype = e.headers.get("Content-Type", "") if e.headers else ""
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        return e.code, ctype, body


def try_json(url: str, token: str) -> tuple[bool, Any, dict]:
    status, ctype, body = fetch_raw(url, token)
    meta = {
        "url": url,
        "status": status,
        "content_type": ctype,
        "snippet": body[:220],
    }
    try:
        return True, json.loads(body), meta
    except Exception:
        return False, None, meta


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


def walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def extract_list(payload: Any) -> Optional[list[dict]]:
    if isinstance(payload, list) and payload and all(isinstance(x, dict) for x in payload):
        return payload

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


def wrap_names(names: list[str], max_chars: int = 98) -> list[str]:
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


def parse_latest_season(season_payload: Any) -> dict[str, str]:
    """
    Expected shape:
      {"data":[{...latest season...}, {...older...}]}
    We take the first element if present.
    """
    out = {
        "season_name": "—",
        "season_league": "—",
        "season_rank": "—",
        "season_total_ranks": "—",
        "season_points": "—",
        "season_flags": "—/—",
        "season_next_flags": "—/—",
    }

    data = None
    if isinstance(season_payload, dict) and isinstance(season_payload.get("data"), list):
        data = season_payload["data"]

    if not data:
        return out

    latest = data[0] if isinstance(data[0], dict) else None
    if not latest:
        return out

    out["season_name"] = str(latest.get("season_name") or "—")
    out["season_league"] = str(latest.get("league") or "—")
    out["season_rank"] = fmt_num(latest.get("rank"))
    out["season_total_ranks"] = fmt_num(latest.get("total_ranks"))
    out["season_points"] = fmt_num(latest.get("total_season_points"))

    tsf = latest.get("total_season_flags")
    if isinstance(tsf, dict):
        out["season_flags"] = fmt_counter(tsf.get("obtained"), tsf.get("total"))

    ftnr = latest.get("flags_to_next_rank")
    if isinstance(ftnr, dict):
        out["season_next_flags"] = fmt_counter(ftnr.get("obtained"), ftnr.get("total"))

    return out


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

    # season fields
    season_name = extras.get("season_name", "—")
    season_league = extras.get("season_league", "—")
    season_rank = extras.get("season_rank", "—")
    season_total_ranks = extras.get("season_total_ranks", "—")
    season_points = extras.get("season_points", "—")
    season_flags = extras.get("season_flags", "—/—")
    season_next_flags = extras.get("season_next_flags", "—/—")

    completed_lines = wrap_names(extras.get("completed", []), max_chars=98)

    base_h = 340
    per_line = 18
    H = base_h + max(0, (len(completed_lines) - 1)) * per_line + 30

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    def esc(x: Any) -> str:
        return html.escape(str(x))

    scanlines = "\n".join(
        f'<rect x="0" y="{y}" width="{W}" height="1" fill="#00ff41" opacity="0.05"/>'
        for y in range(0, H, 4)
    )

    y0 = 305
    completed_svg = "\n  ".join(
        f'<text class="t s" x="{pad}" y="{y0 + i * per_line}">{esc(line)}</text>'
        for i, line in enumerate(completed_lines)
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
  <text class="t s" x="{pad+480}" y="218">{esc(season_name)} · {esc(season_league)}</text>
  <text class="t v" x="{pad+480}" y="240">#{esc(season_rank)}/{esc(season_total_ranks)} · {esc(season_points)} pts · {esc(season_flags)} flags</text>
  <text class="t s muted" x="{pad+480}" y="262">next rank flags: {esc(season_next_flags)}</text>

  <text class="t k" x="{pad}" y="285">COMPLETED PRO LABS</text>
  {completed_svg}

  <text class="t k muted" x="{pad}" y="{H-28}">updated {updated}</text>
</svg>
'''


def main() -> None:
    token = os.environ.get("HTB_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing HTB_TOKEN env var (set via GitHub Actions secret).")

    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    debug: dict[str, Any] = {"basic": {}, "prolabs": {}, "fortresses": {}, "challenges": {}, "season": {}, "extras": {}}

    # BASIC
    ok, base_payload, meta = try_json(BASIC_ENDPOINT, token)
    debug["basic"] = {"ok": ok, **meta}
    if not ok or not isinstance(base_payload, dict):
        OUT_DEBUG.write_text(json.dumps(debug, indent=2), encoding="utf-8")
        raise SystemExit("Failed to fetch basic profile payload.")
    base = base_payload.get("profile") if isinstance(base_payload.get("profile"), dict) else base_payload

    extras: dict[str, Any] = {
        "prolabs": "—/—",
        "fortresses": "—/—",
        "completed": [],
        "challenges": "—/—",
        # season
        "season_name": "—",
        "season_league": "—",
        "season_rank": "—",
        "season_total_ranks": "—",
        "season_points": "—",
        "season_flags": "—/—",
        "season_next_flags": "—/—",
    }

    # PROLABS
    ok, payload, meta = try_json(PROLAB_ENDPOINT, token)
    debug["prolabs"] = {"ok": ok, **meta}
    if ok:
        items = extract_list(payload)
        if items:
            done, total, comp = extract_done_total_from_list(items)
            extras["prolabs"] = fmt_counter(done, total)
            extras["completed"] = merge_unique(extras["completed"], comp)

    # FORTRESSES
    ok, payload, meta = try_json(FORTRESS_ENDPOINT, token)
    debug["fortresses"] = {"ok": ok, **meta}
    if ok:
        items = extract_list(payload)
        if items:
            done, total, _ = extract_done_total_from_list(items)
            extras["fortresses"] = fmt_counter(done, total)

    # CHALLENGES (active list)
    ok, payload, meta = try_json(CHALLENGE_LIST_ENDPOINT, token)
    debug["challenges"] = {"ok": ok, **meta}
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

    # SEASON (new endpoint)
    ok, payload, meta = try_json(SEASON_RANKS_ENDPOINT, token)
    debug["season"] = {"ok": ok, **meta}
    if ok and payload is not None:
        s = parse_latest_season(payload)
        extras.update(s)

    debug["extras"] = extras
    OUT_DEBUG.write_text(json.dumps(debug, indent=2), encoding="utf-8")

    OUT_SVG.write_text(svg_card(base, extras), encoding="utf-8")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_DEBUG}")


if __name__ == "__main__":
    main()
