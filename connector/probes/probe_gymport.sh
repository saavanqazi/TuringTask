#!/bin/sh
# probe_gymport.sh - door 3 in depth: can the agent drive the outlook gym on 127.0.0.1:8014
# directly, skipping the proxy (and its tool trace)? Run INSIDE a throwaway container AS THE AGENT:
#   docker exec -u rlgymagent c1probe sh /tmp/probe_gymport.sh
# Every line must be 401/403/404/405/422 or refused. A 2xx that returns data is a finding.
P=http://127.0.0.1:8014
hit() { # method path [body]
  if [ -n "$3" ]; then
    code=$(curl -s -m 5 -o /tmp/g -w "%{http_code}" -X "$1" -H 'content-type: application/json' -d "$3" "$P$2")
  else
    code=$(curl -s -m 5 -o /tmp/g -w "%{http_code}" -X "$1" "$P$2")
  fi
  printf '%-6s %-40s -> %s  %s\n' "$1" "$2" "$code" "$(head -c 160 /tmp/g | tr '\n' ' ')"
}
id
hit POST /step '{"action_type":"ToolCallAction","tool_name":"search_email","arguments":{"queries":[""]}}'
hit POST /step '{"action_type":"ListToolsAction"}'
hit GET  /state
hit GET  "/state?verify_queries=SELECT%201"
hit POST /mcp '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"p","version":"1"}}}'
hit GET  /mcp
hit GET  /v1.0/me/messages
hit GET  /v1.0/me/events
hit GET  /me/messages
hit GET  /users
hit GET  /api/users
hit GET  /api/messages
hit GET  /api/tables
hit POST /api/sql-runner '{"query":"SELECT 1"}'
hit GET  /api/download-db-file
hit GET  /openapi.json
hit GET  /docs
hit POST /reset '{}'
echo "== same /step with a made-up database id header"
code=$(curl -s -m 5 -o /tmp/g -w "%{http_code}" -X POST -H 'content-type: application/json' -H 'x-database-id: db_x' -d '{"action_type":"ToolCallAction","tool_name":"search_email","arguments":{"queries":[""]}}' $P/step); echo "POST /step +db header -> $code $(head -c 160 /tmp/g)"
echo "== done"
