"""Gather the NBA writers whose Bluesky posts the box score's Takes show.

The page searches Bluesky for posts that mention a game's teams or top scorers, and keeps only
posts from the accounts in site/writers.json. Those accounts are the members of public Bluesky
lists of NBA media kept by writers and team media: national writers and analysts, plus the
beat writers of the teams that have such a list. Their DIDs are stored rather than handles,
since a DID never changes. Run this now and then to pick up the lists' changes:

    python scripts/bsky_writers.py
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "site" / "writers.json"
API = "https://public.api.bsky.app/xrpc/app.bsky.graph.getList"
HEADERS = {"User-Agent": "wl-draft-tracker/1.0"}

# (what it is, the list's address). Lists that mix in fans at large are left out.
LISTS = [
    ("NBA writers, broadcasters and podcasters (Howard Beck)", "at://did:plc:rkpzrwxex34r36ypejhew7ml/app.bsky.graph.list/3llmezwbnrp2d"),
    ("The Athletic NBA", "at://did:plc:z2pzwb4newtlavxdtn3xaoql/app.bsky.graph.list/3layti5jt6o25"),
    ("NBA reporters, news, stats and analytics", "at://did:plc:lamdmpph3lkgw4gorv36767a/app.bsky.graph.list/3lazb76xy6g2c"),
    ("Celtics media", "at://did:plc:5m4gfo3oxvcxdldgdbelb5eg/app.bsky.graph.list/3lbmqczidlv2t"),
    ("Bucks media", "at://did:plc:au5awlfgodoxfcgfoopx56th/app.bsky.graph.list/3lav7qdotkq2d"),
    ("Utah Jazz and NBA media", "at://did:plc:wotzm2tugydbfasrhdb7reuz/app.bsky.graph.list/3lar3py3nv32w"),
    ("Sacramento Kings media", "at://did:plc:4xaad7thmc4uqdhefbq6vizm/app.bsky.graph.list/3lapocmcm462s"),
    ("Indiana media (Pacers)", "at://did:plc:hhv67ydqswmrizaz5dqlz336/app.bsky.graph.list/3lb3k63d4v62p"),
    ("Toronto Raptors media", "at://did:plc:y4cegukryqe4vozpafu55ts5/app.bsky.graph.list/3lgfgk4ivuh25"),
    ("Sixers coverage", "at://did:plc:4h5iaiqguc3czeexhjxln4kv/app.bsky.graph.list/3lbb5fhgfad22"),
    ("Spurs media", "at://did:plc:wh4g7dsxka6mjibd6nx35xr5/app.bsky.graph.list/3mndiqcelsr2u"),
]


def get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def members(uri):
    """Every account on a list, a page of 100 at a time."""
    out, cursor = [], None
    while True:
        page = get({"list": uri, "limit": 100, **({"cursor": cursor} if cursor else {})})
        out += [item["subject"] for item in page.get("items", [])]
        cursor = page.get("cursor")
        if not cursor or not page.get("items"):
            return out


def main():
    dids = {}
    for name, uri in LISTS:
        people = members(uri)
        for p in people:
            dids.setdefault(p["did"], p.get("handle", ""))
        print(f"{len(people):4d}  {name}")
    OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "lists": [name for name, _ in LISTS],
        "dids": sorted(dids),
    }, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(dids)} writers -> {OUT}")


if __name__ == "__main__":
    main()
