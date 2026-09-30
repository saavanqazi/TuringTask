"""probe_calendar.py - what the AGENT sees for the meetings Jack organised (run as rlgymagent):
  docker exec -u rlgymagent c1probe python3 /tmp/probe_calendar.py
Prints each organised event's description, lastModifiedDateTime and every attendee's response and time."""
import asyncio, json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    async with streamablehttp_client("http://127.0.0.1:7000/mcp/outlook-gym") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("search_calendar", {"start_date": "2026-04-27T00:00:00-07:00",
                                                        "end_date": "2026-05-17T23:59:59-07:00", "queries": [""]})
            d = json.loads("".join(getattr(c, "text", "") for c in res.content))
            for e in d["value"]:
                if not e.get("isOrganizer"):
                    continue
                print(f"== {e['subject']}  {e['start']['dateTime']} {e['start']['timeZone']}  lastModified={e.get('lastModifiedDateTime')}")
                print(f"   body: {(e.get('body') or {}).get('content')}")
                for a in e["attendees"]:
                    print(f"     {a['type']:8} {a['status']['response']:20} {a['status'].get('time')}  {a['emailAddress']['name']} <{a['emailAddress']['address']}>")

asyncio.run(main())
