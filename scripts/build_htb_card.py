import html
import json
import os
import pathlib
import re
import urllib.request
from datetime import datetime
from typing import Any, Iterable

HTB_MEMBER_ID = "378794"
PROFILE_URL = f"https://app.hackthebox.com/public/users/{HTB_MEMBER_ID}"

# Commonly referenced HTB v4 endpoint for public profile by member_id
API_CANDIDATES = [
    f"https://www.hackthebox.com/api/v4/profile/{HTB_MEMBER_ID}",
    f"https://app.hackthebox.com/api/v4/profile/{HTB_MEMBER_ID}",
]

OUT_SVG = pathlib.Path("assets/htb-card.svg")
OUT_DEBUG = pathlib.Path("assets/htb-debug.json")


def fetch_json(url: str, token: str) -> Any:
    """
    HTB tokens are JWT-like; send as Authorization: Bearer <token>.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (GitHub Actions)",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8", errors="replace")
        return json.loads(data)


def walk(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def find_first_key(obj: Any, keys: set[str]) -> Any:
    """Find first occurrence of any key in keys, anywhere in nested JSON."""
    for node in walk(obj):
        if isinstance(node, dict):
            for k in keys:
                if k in node and node[k] is not None:
                    return node[k]
    return None


def find_profile_blob(payload: Any) -> dict[str, Any]:
    """
    Some responses wrap profile under 'profile' or similar.
    Also pick the dict that looks most like a user profile.
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("profile"), dict):
            return payload["profile"]

        # Heuristic: choose a dict containing username/name + stats-ish keys
        candidates = []
        for node in walk(payload):
            if not isinstance(node, dict):
                continue
            name = node.get("username") or node.get("name") or node.get("handle")
            has_stats = any(k in node for k in ("points", "rank", "globalRanking", "ranking", "flags"))
            if name and has_stats:
                candidates.append(node)
        if candidates:
            return max(candidates, key=lambda d: len(d.keys()))

        return payload
    return {}


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


def fmt_counter(x: Any) -> str:
    """
    Accepts:
      - "5/10" (string)
      - {"done":5,"total":10}
      - {"solved":5,"total":10}
    """
    if x is None:
        return "—/—"
    if isinstance(x, str) and "/" in x:
        return x
    if isinstance(x, dict):
        done = x.get("done", x.get("solved", x.get("completed")))
        total = x.get("total", x.get("max"))
        if done is not None and total is not None:
            return f"{fmt_num(done)}/{fmt_num(total)}"
    return "—/—"


def extract_completed_names(payload: Any) -> list[str]:
    """
    Try to find lists of labs/fortresses/prolabs in payload and extract names with 100% completion.
    """
    completed: list[str] = []
    list_keys = {"prolabs", "proLabs", "miniProLabs", "miniprolabs", "fortresses", "fortress"}

    for node in walk(payload):
        if not isinstance(node, dict):
            continue
        for k in list_keys:
            v = node.get(k)
            if isinstance(v, list):
                for item in v:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name") or item.get("title")
                    pct = item.get("progress") or item.get("percentage") or item.get("completion")
                    try:
                        if name and pct is not None and float(pct) >= 100.0:
                            completed.append(str(name))
                    except Exception:
                        pass

    # de-dupe, keep order
    seen = set()
    out = []
    for n in completed:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def svg_card(data: dict[str, Any]) -> str:
    W, H = 980, 310
    pad = 28

    username = data.get("username") or "Hack The Box"
    rank = data.get("rank") or "—"
    points = data.get("points") or "—"
    global_rank = data.get("global_rank") or "—"
    flags = data.get("flags") or "—"
    machines = data.get("machines") or "—"
    challenges = data.get("challenges") or "—"

    prolabs = data.get("prolabs") or "—/—"
    miniprolabs = data.get("miniprolabs") or "—/—"
    fortresses = data.get("fortresses") or "—/—"

    completed = data.get("completed") or []
    completed = completed[:8]
    completed_line = " · ".join(completed) if completed else "—"

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

  <text class="t h" x="{pad}" y="55" filter="url(#glow)">{esc(username)}</text>
  <text class="t s muted" x="{pad}" y="78">{esc(rank)} · {esc(PROFILE_URL)}</text>

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
  <text class="t v" x="{pad}" y="215">{esc(prolabs)}</text>

  <text class="t k" x="{pad+200}" y="190">MINI PRO LABS</text>
  <text class="t v" x="{pad+200}" y="215">{esc(miniprolabs)}</text>

  <text class="t k" x="{pad+440}" y="190">FORTRESSES</text>
  <text class="t v" x="{pad+440}" y="215">{esc(fortresses)}</text>

  <text class="t k" x="{pad}" y="255">COMPLETED</text>
  <text class="t s" x="{pad}" y="277">{esc(completed_line)}</text>

  <text class="t k muted" x="{pad}" y="{H-28}">updated {updated}</text>
</svg>
'''


def main() -> None:
    token = os.environ.get("HTB_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing HTB_TOKEN env var (set it via GitHub Actions secret).")

    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    payload = None
    used_api = None
    errors: list[str] = []

    for api in API_CANDIDATES:
        try:
            payload = fetch_json(api, token)
            used_api = api
            break
        except Exception as e:
            errors.append(f"{api} -> {type(e).__name__}: {e}")

    data: dict[str, Any] = {}
    profile = find_profile_blob(payload) if payload is not None else {}

    # Extract common fields (with flexible key names)
    data["username"] = profile.get("username") or profile.get("name") or profile.get("handle")
    data["rank"] = profile.get("rank") or profile.get("rankName") or profile.get("rank_name")

    data["points"] = fmt_num(profile.get("points") or find_first_key(payload, {"points", "userPoints"}))
    data["global_rank"] = fmt_num(profile.get("globalRanking") or profile.get("global_rank") or find_first_key(payload, {"globalRanking", "globalRank", "ranking"}))
    data["flags"] = fmt_num(profile.get("flags") or profile.get("totalFlags") or find_first_key(payload, {"flags", "totalFlags", "total_flags"}))
    data["machines"] = fmt_num(profile.get("machines") or profile.get("machinesOwned") or profile.get("machinesSolved") or find_first_key(payload, {"machines", "machinesOwned", "machinesSolved"}))
    data["challenges"] = fmt_num(profile.get("challenges") or profile.get("challengesSolved") or find_first_key(payload, {"challenges", "challengesSolved"}))

    data["prolabs"] = fmt_counter(profile.get("prolabs") or profile.get("proLabs") or find_first_key(payload, {"prolabs", "proLabs"}))
    data["miniprolabs"] = fmt_counter(profile.get("miniProLabs") or profile.get("miniprolabs") or find_first_key(payload, {"miniProLabs", "miniprolabs"}))
    data["fortresses"] = fmt_counter(profile.get("fortresses") or find_first_key(payload, {"fortresses"}))

    data["completed"] = extract_completed_names(payload) if payload is not None else []

    # Always write debug (safe: does NOT include your token)
    OUT_DEBUG.write_text(
        json.dumps(
            {
                "used_api": used_api,
                "errors": errors,
                "payload_type": type(payload).__name__ if payload is not None else None,
                "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else None,
                "profile_keys": list(profile.keys()) if isinstance(profile, dict) else None,
                "extracted": data,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    OUT_SVG.write_text(svg_card(data), encoding="utf-8")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_DEBUG}")


if __name__ == "__main__":
    main()
