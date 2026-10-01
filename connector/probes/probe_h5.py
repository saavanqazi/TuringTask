"""probe_h5.py - what the AGENT sees after hardening 5 (run as rlgymagent):
  docker exec -u rlgymagent c1probe python3 /tmp/probe_h5.py
Prints every event Jack organised in the window (isCancelled, description, lastModified, each attendee's type,
response and time), then the whole mailbox (sender, time, subject, body) as one empty-query search returns it."""
import asyncio, json, re
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def payload(res):
    return json.loads("".join(getattr(c, "text", "") for c in res.content))


async def main():
    async with streamablehttp_client("http://127.0.0.1:7000/mcp/outlook-gym") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            d = payload(await s.call_tool("search_calendar", {"start_date": "2026-04-27T00:00:00-07:00",
                                                              "end_date": "2026-05-17T23:59:59-07:00", "queries": [""], "top": 50}))
            print(f"CALENDAR: {len(d['value'])} events in the window")
            for e in d["value"]:
                if not e.get("isOrganizer"):
                    continue
                print(f"== {e['subject']}  {e['start']['dateTime']} {e['start']['timeZone']}  isCancelled={e.get('isCancelled')}  lastModified={e.get('lastModifiedDateTime')}")
                print(f"   body: {(e.get('body') or {}).get('content')}")
                for a in e["attendees"]:
                    print(f"     {a['type']:8} {a['status']['response']:20} {a['status'].get('time')}  {a['emailAddress']['name']} <{a['emailAddress']['address']}>")
            m = payload(await s.call_tool("search_email", {"queries": [""], "top": 50}))
            print(f"\nMAILBOX: {len(m['value'])} messages")
            for x in sorted(m["value"], key=lambda x: x.get("receivedDateTime") or ""):
                body = re.sub(r"<[^>]+>", " ", ((x.get("body") or {}).get("content") or ""))
                body = re.sub(r"\s+", " ", body).strip()
                print(f"-- {x.get('receivedDateTime')}  {((x.get('from') or {}).get('emailAddress') or {}).get('address')}  {x.get('subject')!r}  id={x.get('id')}")
                print(f"   {body[:700]}")

asyncio.run(main())
