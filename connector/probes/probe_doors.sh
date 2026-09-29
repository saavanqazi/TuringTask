#!/bin/sh
# probe_doors.sh - run INSIDE the running task container AS THE AGENT USER:
#   docker exec -u rlgymagent c1probe sh /tmp/probe_doors.sh
# Every door must be refused. Prints one line per probe; "OPEN" lines are findings.
G=outlook-gym
echo "== who am I"; id
echo "== 1. state route on the public proxy port (must be 404/refused, never a row)"
curl -s -m 5 -o /tmp/p1 -w "HTTP %{http_code}\n" "http://127.0.0.1:7000/raw/$G/state?verify_queries=SELECT%201"; head -c 200 /tmp/p1; echo
echo "== 2. step route on the public proxy port (must be 404/refused)"
curl -s -m 5 -o /tmp/p2 -w "HTTP %{http_code}\n" -X POST -H 'content-type: application/json' -d '{"action_type":"ToolCallAction","tool_name":"search_email","arguments":{"queries":[""]}}' "http://127.0.0.1:7000/raw/$G/step"; head -c 200 /tmp/p2; echo
echo "== 2b. trusted socket (must be permission denied)"
ls -l /run/harbor/proxy/ 2>&1 | head -5
curl -s -m 5 --unix-socket /run/harbor/proxy/trusted-proxy.sock -w "HTTP %{http_code}\n" "http://x/raw/$G/state?verify_queries=SELECT%201" 2>&1 | head -c 300; echo
echo "== 3. every listening TCP port, and what it answers without credentials"
PORTS=$(awk 'NR>1 && $4=="0A" {split($2,a,":"); printf "%d\n", strtonum("0x" a[2])}' /proc/net/tcp /proc/net/tcp6 2>/dev/null | sort -un)
[ -z "$PORTS" ] && PORTS=$(for h in $(awk 'NR>1 && $4=="0A" {split($2,a,":"); print a[2]}' /proc/net/tcp /proc/net/tcp6 | sort -u); do printf "%d\n" 0x$h; done)
echo "listening: $PORTS"
for p in $PORTS; do
  for path in / /health /docs /openapi.json /api/sql-runner /api/reset-database /api/download-db-file /api/schema /reset /state /step; do
    code=$(curl -s -m 3 -o /tmp/pp -w "%{http_code}" "http://127.0.0.1:$p$path")
    case "$code" in 2*) echo "OPEN? port $p $path -> $code $(head -c 120 /tmp/pp | tr '\n' ' ')";; esac
  done
done
echo "== 3b. sql-runner on the gym port with a query (must be 401/404)"
curl -s -m 5 -w " HTTP %{http_code}\n" -X POST -H 'content-type: application/json' -d '{"query":"SELECT count(*) FROM messages"}' http://127.0.0.1:8014/api/sql-runner | head -c 300; echo
echo "== 4. files on disk (must be denied / empty)"
ls -ld /app /gyms /opt/proxy /opt/proxy-venv /run/harbor /logs /logs/verifier 2>&1
ls /gyms 2>&1 | head -3
head -c 80 /opt/proxy/server.py >/dev/null 2>&1 && echo "OPEN? /opt/proxy/server.py is readable by the agent" || echo "closed: /opt/proxy/server.py unreadable"
cat /app/task.toml >/dev/null 2>&1 && echo "OPEN? /app/task.toml readable" || echo "closed: /app unreadable"
echo "readable databases / seeds anywhere:"
find / -xdev \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' -o -name '*seed*.sql' -o -name 'synthetic_data*' -o -name 'manifest.json' -o -name 'golden_trajectory.json' -o -name 'expected_diff.json' \) -readable 2>/dev/null | grep -v '^/proc' | head -20
echo "== 5. agent environment secrets (must print nothing)"
env | grep -i -E 'capab|token|api_key|secret|password' | sed 's/=.*/=<set>/'
echo "== done"
