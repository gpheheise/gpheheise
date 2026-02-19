import html
import json
import pathlib
import urllib.request
from datetime import datetime
from typing import Any

HTB_ID = "378794"

API_CANDIDATES = [
    f"https://www.hackthebox.com/api/v4/profile/{HTB_ID}",
    # sometimes endpoints differ; keep this as a fallback attempt
    f"https://app.hackthebox.com/api/v4/profile/{HTB_ID}",
]

PROFILE_URL = f"https://app.hackthebox.com/public/users/{HTB_ID}"

OUT_SVG = pathlib.Path("assets/htb-card.svg")
OUT_DEBUG = pathlib.Path("assets/htb-debug.json")


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (GitHub Actions)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def esc(x: Any) -> str:
    return html.escape(str(x))


def matrix_svg(data: dict[str, Any]) -> str:
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
    completed = completed[:6]
    completed_line = " · ".join(completed) if completed else "—"

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

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
    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    payload = None
    errors = []
    used_api = None

    for api in API_CANDIDATES:
        try:
            payload = fetch_json(api)
            used_api = api
            break
        except Exception as e:
            errors.append(f"{api} -> {type(e).__name__}: {e}")

    data: dict[str, Any] = {}
    completed_names: list[str] = []

    if isinstance(payload, dict):
        # many HTB responses are { "profile": {...} } or direct profile
        prof = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload

        username = prof.get("name") or prof.get("username") or prof.get("handle")
        rank = prof.get("rank") or prof.get("rank_name") or prof.get("rankName")
        points = prof.get("points")
        global_rank = prof.get("global_ranking") or prof.get("globalRanking") or prof.get("global_rank")
        flags = prof.get("flags") or prof.get("total_flags") or prof.get("totalFlags")
        machines = prof.get("machines") or prof.get("machines_owned") or prof.get("machinesOwned")
        challenges = prof.get("challenges") or prof.get("challenges_solved") or prof.get("challengesSolved")

        # labs counters (if present)
        prolabs = prof.get("prolabs") or prof.get("proLabs")
        miniprolabs = prof.get("mini_prolabs") or prof.get("miniProLabs")
        fortresses = prof.get("fortresses")

        # labs lists (if present) - extract completed names
        for key in ["prolabs_list", "proLabs", "prolabs", "fortresses", "miniProLabs"]:
            v = prof.get(key)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("title")
                        pct = item.get("progress") or item.get("completion") or item.get("percentage")
                        try:
                            if name and pct is not None and float(pct) >= 100:
                                completed_names.append(str(name))
                        except Exception:
                            pass

        data = {
            "username": username,
            "rank": rank,
            "points": points,
            "global_rank": global_rank,
            "flags": flags,
            "machines": machines,
            "challenges": challenges,
            "prolabs": prolabs if isinstance(prolabs, str) else (None),
            "miniprolabs": miniprolabs if isinstance(miniprolabs, str) else (None),
            "fortresses": fortresses if isinstance(fortresses, str) else (None),
            "completed": completed_names,
        }

        # If counters are numbers like {"done":5,"total":10}, format them
        def fmt_counter(x):
            if isinstance(x, dict) and "done" in x and "total" in x:
                return f"{x['done']}/{x['total']}"
            return x

        data["prolabs"] = fmt_counter(prolabs) or "—/—"
        data["miniprolabs"] = fmt_counter(miniprolabs) or "—/—"
        data["fortresses"] = fmt_counter(fortresses) or "—/—"

    # Always write debug so we can tune keys fast
    OUT_DEBUG.write_text(
        json.dumps(
            {"used_api": used_api, "errors": errors, "payload_type": type(payload).__name__, "payload_keys": list(payload.keys()) if isinstance(payload, dict) else None},
            indent=2,
        ),
        encoding="utf-8",
    )

    OUT_SVG.write_text(matrix_svg(data), encoding="utf-8")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_DEBUG}")


if __name__ == "__main__":
    main()
