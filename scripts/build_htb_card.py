import html
import json
import pathlib
import re
import urllib.request
from datetime import datetime
from typing import Any

HTB_USER_ID = "378794"
HTB_URL = f"https://app.hackthebox.com/public/users/{HTB_USER_ID}"
OUT_FILE = pathlib.Path("assets/htb-card.svg")


def fetch(url: str, accept: str = "text/html") -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> Any:
    raw = fetch(url, accept="application/json")
    return json.loads(raw)


def find_api_endpoint(page: str) -> str | None:
    """
    Try to locate a JSON endpoint in the HTML.
    HTB often includes API calls like /api/v4/public/user/profile/<id> etc.
    We'll search for common patterns.
    """
    candidates = []

    # Common HTB API patterns (best-effort)
    patterns = [
        r'(["\'])(/api/[^"\']+%s[^"\']*)\1' % re.escape(HTB_USER_ID),
        r'(["\'])(https://[^"\']+/api/[^"\']+%s[^"\']*)\1' % re.escape(HTB_USER_ID),
        r'(["\'])(/api/[^"\']+public[^"\']+%s[^"\']*)\1' % re.escape(HTB_USER_ID),
    ]

    for pat in patterns:
        for m in re.finditer(pat, page, flags=re.IGNORECASE):
            url = m.group(2)
            if url.startswith("/"):
                url = "https://app.hackthebox.com" + url
            candidates.append(url)

    # Prefer endpoints that look like “profile” / “user” JSON
    for preferred in candidates:
        if any(k in preferred.lower() for k in ["profile", "user", "public"]):
            return preferred

    return candidates[0] if candidates else None


def walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def find_value(obj: Any, key_names: set[str]):
    """Find first occurrence of any key in key_names in a nested JSON structure."""
    for node in walk(obj):
        for k in list(node.keys()):
            if k in key_names and node[k] is not None:
                return node[k]
    return None


def find_labs(obj: Any):
    """
    Try to find lab/prolab/fortress lists.
    Returns dict with keys and lists if found.
    """
    out = {"prolabs": [], "miniprolabs": [], "fortresses": []}

    for node in walk(obj):
        if not isinstance(node, dict):
            continue

        # Heuristics: arrays of objects with 'name' and 'progress'/'percentage'
        for k in ["prolabs", "proLabs", "pro_labs"]:
            if k in node and isinstance(node[k], list):
                out["prolabs"] = node[k]
        for k in ["miniProLabs", "miniprolabs", "mini_pro_labs"]:
            if k in node and isinstance(node[k], list):
                out["miniprolabs"] = node[k]
        for k in ["fortresses", "fortress"]:
            if k in node and isinstance(node[k], list):
                out["fortresses"] = node[k]

    return out


def matrix_svg(data: dict[str, Any]) -> str:
    W, H = 980, 300
    pad = 28

    username = data.get("username") or "0x01r3ddw4rf"
    rank = data.get("rank") or "Pro Hacker"
    points = data.get("points") or "—"
    global_rank = data.get("global_rank") or "—"
    flags = data.get("flags") or "—"
    machines = data.get("machines") or "—"
    challenges = data.get("challenges") or "—"

    prolabs_done = data.get("prolabs_done") or "—"
    prolabs_total = data.get("prolabs_total") or "—"
    mini_done = data.get("mini_done") or "—"
    mini_total = data.get("mini_total") or "—"
    forts_done = data.get("forts_done") or "—"
    forts_total = data.get("forts_total") or "—"

    completed_names = data.get("completed_names") or []

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    def esc(x: str) -> str:
        return html.escape(str(x))

    # Render up to 6 completed items
    completed_names = [str(x) for x in completed_names][:6]
    completed_line = " · ".join(completed_names) if completed_names else "—"

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

  <text class="t h" x="{pad}" y="55" filter="url(#glow)">{esc(username)}</text>
  <text class="t s muted" x="{pad}" y="78">{esc(rank)} · {esc(HTB_URL)}</text>

  <text class="t k" x="{pad}" y="120">POINTS</text>
  <text class="t v" x="{pad}" y="145">{esc(points)}</text>

  <text class="t k" x="{pad+160}" y="120">GLOBAL</text>
  <text class="t v" x="{pad+160}" y="145">#{esc(global_rank)}</text>

  <text class="t k" x="{pad+320}" y="120">FLAGS</text>
  <text class="t v" x="{pad+320}" y="145">{esc(flags)}</text>

  <text class="t k" x="{pad+440}" y="120">MACHINES</text>
  <text class="t v" x="{pad+440}" y="145">{esc(machines)}</text>

  <text class="t k" x="{pad+590}" y="120">CHALLENGES</text>
  <text class="t v" x="{pad+590}" y="145">{esc(challenges)}</text>

  <text class="t k" x="{pad}" y="190">PRO LABS</text>
  <text class="t v" x="{pad}" y="215">{esc(prolabs_done)}/{esc(prolabs_total)}</text>

  <text class="t k" x="{pad+170}" y="190">MINI PRO LABS</text>
  <text class="t v" x="{pad+170}" y="215">{esc(mini_done)}/{esc(mini_total)}</text>

  <text class="t k" x="{pad+390}" y="190">FORTRESSES</text>
  <text class="t v" x="{pad+390}" y="215">{esc(forts_done)}/{esc(forts_total)}</text>

  <text class="t k" x="{pad}" y="250">COMPLETED</text>
  <text class="t s" x="{pad}" y="272">{esc(completed_line)}</text>

  <text class="t k muted" x="{pad}" y="{H-28}">updated {updated}</text>
</svg>
'''


def main() -> None:
    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    page = fetch(HTB_URL)

    api = find_api_endpoint(page)
    payload = None
    if api:
        try:
            payload = fetch_json(api)
        except Exception:
            payload = None

    # Fallback: save the first 50k chars of HTML to debug
    pathlib.Path("assets/htb-page-snippet.html").write_text(page[:50000], encoding="utf-8")

    data: dict[str, Any] = {}

    if payload:
        pathlib.Path("assets/htb-api.json").write_text(json.dumps(payload)[:500000], encoding="utf-8")

        # Best-effort key searches
        data["username"] = find_value(payload, {"username", "name", "handle"}) or "0x01r3ddw4rf"
        data["rank"] = find_value(payload, {"rank", "rankName", "userRank"}) or "Pro Hacker"
        data["points"] = find_value(payload, {"points", "userPoints"}) or "—"
        data["global_rank"] = find_value(payload, {"globalRanking", "globalRank", "ranking"}) or "—"
        data["flags"] = find_value(payload, {"flags", "totalFlags"}) or "—"
        data["machines"] = find_value(payload, {"machines", "machinesSolved"}) or "—"
        data["challenges"] = find_value(payload, {"challenges", "challengesSolved"}) or "—"

        labs = find_labs(payload)

        # If lists exist, derive totals and completed names
        completed = []
        for group in ["prolabs", "miniprolabs", "fortresses"]:
            for item in labs.get(group, []):
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("title")
                pct = item.get("progress") or item.get("percentage") or item.get("completion")
                if name is not None and pct is not None:
                    try:
                        pct_val = float(pct)
                    except Exception:
                        pct_val = None
                    if pct_val is not None and pct_val >= 100:
                        completed.append(name)

        data["completed_names"] = completed

        # Try to find the counters (done/total) in payload, else compute
        # (We compute from lists if present)
        def done_total(items):
            if not items:
                return None, None
            total = len(items)
            done = 0
            for item in items:
                if isinstance(item, dict):
                    pct = item.get("progress") or item.get("percentage") or item.get("completion")
                    try:
                        if pct is not None and float(pct) >= 100:
                            done += 1
                    except Exception:
                        pass
            return done, total

        d, t = done_total(labs.get("prolabs", []))
        if d is not None:
            data["prolabs_done"], data["prolabs_total"] = d, t

        d, t = done_total(labs.get("miniprolabs", []))
        if d is not None:
            data["mini_done"], data["mini_total"] = d, t

        d, t = done_total(labs.get("fortresses", []))
        if d is not None:
            data["forts_done"], data["forts_total"] = d, t
    else:
        # Minimal fallback (still renders a card)
        data = {
            "username": "0x01r3ddw4rf",
            "rank": "Pro Hacker",
        }

    OUT_FILE.write_text(matrix_svg(data), encoding="utf-8")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
