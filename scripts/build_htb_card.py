import html
import json
import pathlib
import re
import urllib.request
from datetime import datetime
from typing import Any

HTB_URL = "https://app.hackthebox.com/public/users/378794"
OUT_FILE = pathlib.Path("assets/htb-card.svg")


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (GitHub Actions; +https://github.com/gpheheise/gpheheise)"
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def extract_next_data(page: str) -> dict[str, Any]:
    # Next.js embeds a big JSON blob in __NEXT_DATA__
    m = re.search(
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        page,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not m:
        raise RuntimeError("Could not find __NEXT_DATA__ in page HTML.")
    raw = m.group(1).strip()
    return json.loads(raw)


def walk(obj: Any):
    """Yield every node in nested dict/list structures."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def first_value(d: dict, keys: list[str]):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def pick_best_profile_blob(next_data: dict[str, Any]) -> dict[str, Any]:
    """
    HTB can structure this in many ways. We'll search for a dict that looks like a user profile payload.
    Heuristics: contains 'name'/'username' and some stats fields.
    """
    candidates = []
    for node in walk(next_data):
        if not isinstance(node, dict):
            continue

        name = first_value(node, ["name", "username", "handle", "nickname"])
        # "rank", "points", "globalRanking", "userId" etc. may appear
        has_stats = any(k in node for k in ["rank", "points", "globalRanking", "ranking", "userId", "id"])
        if name and has_stats:
            candidates.append(node)

    # pick the biggest candidate (usually the full payload)
    if not candidates:
        return {}
    return max(candidates, key=lambda x: len(x.keys()))


def numify(x: Any) -> str | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        if isinstance(x, float) and x.is_integer():
            x = int(x)
        return f"{x:,}".replace(",", "")
    s = str(x)
    m = re.search(r"[\d][\d,\.]*", s)
    return m.group(0) if m else s


def matrix_svg(data: dict[str, str | None]) -> str:
    W, H = 900, 220
    pad = 28

    username = data.get("username") or "Hack The Box"
    rank = data.get("rank") or "—"
    points = data.get("points") or "—"
    global_rank = data.get("global_rank") or "—"
    flags = data.get("flags") or "—"
    machines = data.get("machines") or "—"
    challenges = data.get("challenges") or "—"

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    scanlines = "\n".join(
        f'<rect x="0" y="{y}" width="{W}" height="1" fill="#00ff41" opacity="0.05"/>'
        for y in range(0, H, 4)
    )

    def esc(x: str) -> str:
        return html.escape(x)

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
  <text class="t s muted" x="{pad}" y="78">HTB · {esc(HTB_URL)}</text>

  <text class="t k" x="{pad}" y="120">RANK</text>
  <text class="t v" x="{pad}" y="145">{esc(rank)}</text>

  <text class="t k" x="{pad+190}" y="120">POINTS</text>
  <text class="t v" x="{pad+190}" y="145">{esc(points)}</text>

  <text class="t k" x="{pad+350}" y="120">GLOBAL</text>
  <text class="t v" x="{pad+350}" y="145">#{esc(global_rank)}</text>

  <text class="t k" x="{pad+520}" y="120">FLAGS</text>
  <text class="t v" x="{pad+520}" y="145">{esc(flags)}</text>

  <text class="t k" x="{pad+650}" y="120">MACHINES</text>
  <text class="t v" x="{pad+650}" y="145">{esc(machines)}</text>

  <text class="t k" x="{pad+780}" y="120">CHALLENGES</text>
  <text class="t v" x="{pad+780}" y="145">{esc(challenges)}</text>

  <text class="t k muted" x="{pad}" y="{H-28}">updated {updated}</text>
</svg>
'''


def main() -> None:
    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    page = fetch(HTB_URL)
    next_data = extract_next_data(page)

    blob = pick_best_profile_blob(next_data)

    # Try multiple possible key names — HTB may differ.
    username = first_value(blob, ["username", "name", "handle", "nickname"])
    rank = first_value(blob, ["rank", "userRank", "htbRank", "rankName"])
    points = first_value(blob, ["points", "userPoints", "htbPoints"])
    global_rank = first_value(blob, ["globalRanking", "globalRank", "ranking", "rankGlobal"])
    flags = first_value(blob, ["flags", "userFlags", "totalFlags"])
    machines = first_value(blob, ["machines", "userMachines", "machinesOwned", "machinesSolved"])
    challenges = first_value(blob, ["challenges", "userChallenges", "challengesSolved"])

    data = {
        "username": str(username) if username else None,
        "rank": str(rank) if rank else None,
        "points": numify(points),
        "global_rank": numify(global_rank),
        "flags": numify(flags),
        "machines": numify(machines),
        "challenges": numify(challenges),
    }

    # Helpful debug: write a small JSON snapshot for troubleshooting
    pathlib.Path("assets/htb-debug.json").write_text(
        json.dumps({"picked_blob_keys": list(blob.keys()), "data": data}, indent=2),
        encoding="utf-8",
    )

    OUT_FILE.write_text(matrix_svg(data), encoding="utf-8")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
