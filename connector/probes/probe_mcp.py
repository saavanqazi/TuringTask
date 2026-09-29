"""probe_mcp.py - the Handbook §3.2 gym probe, through the agent's own MCP door.
Run INSIDE the container AS THE AGENT USER:
  docker exec -u rlgymagent c1probe python3 /tmp/probe_mcp.py
Answers: can the agent reach the data through tools, how many rows come back, does an
undated calendar search fail, is any listing silently truncated."""
import asyncio, json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://127.0.0.1:7000/mcp/outlook-gym"


def text_of(res):
    out = []
    for c in res.content or []:
        out.append(getattr(c, "text", "") or "")
    return "\n".join(out)


def summarise(label, res):
    t = text_of(res)
    print(f"--- {label}: isError={res.isError} chars={len(t)}")
    try:
        d = json.loads(t)
    except Exception:
        print(t[:600]); return None
    def walk(x, path="$"):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, list): print(f"   {path}.{k}: list of {len(v)}")
                elif isinstance(v, (int, str, bool)) and k.lower() in ("total", "count", "next", "nextpagetoken", "next_page_token", "has_more", "page", "page_size", "truncated", "@odata.nextlink"):
                    print(f"   {path}.{k} = {v}")
                walk(v, f"{path}.{k}") if isinstance(v, dict) else None
    walk(d)
    return d


async def main():
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            print("TOOLS:", [t.name for t in tools])
            for t in tools:
                if t.name in ("search_calendar", "search_email", "draft_email"):
                    print(f"  {t.name} schema: {json.dumps(t.inputSchema)[:700]}")
            cal = await s.call_tool("search_calendar", {"start_date": "2026-04-27T00:00:00-07:00", "end_date": "2026-05-17T23:59:59-07:00", "queries": [""]})
            d = summarise("calendar, stated window", cal)
            if d is not None:
                print(json.dumps(d)[:4000])
            summarise("calendar, undated", await s.call_tool("search_calendar", {"queries": [""]}))
            summarise("calendar, UTC window", await s.call_tool("search_calendar", {"start_date": "2026-04-27T00:00:00Z", "end_date": "2026-05-17T23:59:59Z", "queries": [""]}))
            summarise("calendar, wide window (Apr 20 - May 24)", await s.call_tool("search_calendar", {"start_date": "2026-04-20T00:00:00Z", "end_date": "2026-05-24T23:59:59Z", "queries": [""]}))
            mail = await s.call_tool("search_email", {"queries": [""]})
            d = summarise("mail, empty query (whole mailbox)", mail)
            if d is not None:
                print(json.dumps(d)[:3000])
            for who in ("charlotte.palmer", "diego.alvarez", "jack.miller", "jack.henry", "jared.ellis", "isla.hughes"):
                summarise(f"mail from {who}", await s.call_tool("search_email", {"queries": [f"from:{who}@contoso.example"]}))

asyncio.run(main())
