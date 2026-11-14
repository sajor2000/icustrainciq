#!/bin/bash
# One command: get the Lookahead dashboard up and print its link.
#
#   scripts/launch.sh                 # run what is missing, then open the board
#   scripts/launch.sh --forecast      # also run a fresh forecast first
#   scripts/launch.sh --all           # publish code + stage ward + forecast + board
#   scripts/launch.sh --link          # just print the link of the running board
#   scripts/launch.sh --restart       # stop the running t7-twin and start it again
#   scripts/launch.sh --no-open       # never open a browser
#
# It is safe to re-run: each step is skipped when the cluster already has its
# output. Steps and what they leave behind are in docs/RUNBOOK.md.
set -euo pipefail
cd "$(dirname "$0")/.."

OPEN=1; WANT_CODE=0; WANT_WARD=0; WANT_FORECAST=0; LINK_ONLY=0; RESTART=0
for a in "$@"; do
  case "$a" in
    --all)      WANT_CODE=1; WANT_WARD=1; WANT_FORECAST=1 ;;
    --code)     WANT_CODE=1 ;;
    --ward)     WANT_WARD=1 ;;
    --forecast) WANT_FORECAST=1 ;;
    --link)     LINK_ONLY=1 ;;
    --restart)  RESTART=1 ;;
    --no-open)  OPEN=0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
wfid() { tr -d '"' | grep -oE '[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}' | head -1; }

# wait for a workflow, printing a dot a tick; fail with the log command to run
wait_for() { # wait_for <id> <name>
  local id="$1" name="$2" s
  printf '   %s ' "$name"
  while :; do
    s=$(fuzzball workflow describe "$id" 2>/dev/null | awk '/Status:/{print $2; exit}')
    case "$s" in
      *FINISHED*) echo " ok"; return 0 ;;
      *FAILED*|*ERRORED*|*CANCELED*)
        echo " $s"
        echo "   fuzzball workflow describe $id" >&2
        return 1 ;;
    esac
    printf '.'; sleep 15
  done
}

running_twin() {
  fuzzball workflow list 2>/dev/null |
    awk -F'|' '$4 ~ /Started/ && $5 ~ /t7-twin/ {gsub(/ /,"",$1); print $1; exit}'
}

board_link() { # board_link <workflow-id>
  fuzzball workflow endpoints list 2>/dev/null | grep "$1" | grep -oE 'https://[^ |]+' | head -1
}

# ---------- link only ----------
if [ "$LINK_ONLY" = 1 ]; then
  WF=$(running_twin); [ -n "$WF" ] || { echo "no running t7-twin"; exit 1; }
  URL=$(board_link "$WF")
  [ -n "$URL" ] && echo "$URL" || fuzzball workflow connect --name board --endpoint web "$WF"
  exit 0
fi

test -f fuzzball/ready/t7-twin.fz || {
  echo "no fuzzball/ready/: render it first"
  echo "  PATH=\"\$PWD/.venv/bin:\$PATH\" bash scripts/make_ready.sh \$(git rev-parse HEAD)"
  exit 1
}

# the cluster runs the commit baked into ready/, not the working tree
READY_REF=$(cat fuzzball/ready/CODE_REF 2>/dev/null || echo "")
HEAD_REF=$(git rev-parse HEAD 2>/dev/null || echo "")
if [ -n "$READY_REF" ] && [ "$READY_REF" != "$HEAD_REF" ]; then
  echo "note: ready/ is rendered at ${READY_REF:0:8}, HEAD is ${HEAD_REF:0:8}."
  echo "      re-render and pass --code if you want the cluster to run HEAD."
fi

# ---------- 1. publish code ----------
if [ "$WANT_CODE" = 1 ]; then
  say "publishing code (t7-code)"
  ID=$(fuzzball workflow start fuzzball/ready/t7-code.fz --name t7-fc-code | wfid)
  wait_for "$ID" "t7-code"
fi

# ---------- 2. stage the ward ----------
if [ "$WANT_WARD" = 1 ]; then
  say "staging the ward (t7-ward)"
  ID=$(fuzzball workflow start fuzzball/ready/t7-ward.fz --name t7-fc-ward | wfid)
  wait_for "$ID" "t7-ward"
fi

# ---------- 3. forecast ----------
if [ "$WANT_FORECAST" = 1 ]; then
  say "forecasting the unit (t7-forecast)"
  ID=$(fuzzball workflow start fuzzball/ready/t7-forecast-unit.fz --name t7-fc-forecast | wfid)
  wait_for "$ID" "t7-forecast" || {
    echo "   the forecast failed; the board will show its last numbers (or the empty state)" >&2
  }
fi

# ---------- 4. the board ----------
# `workflow stop` returns, and the workflow reads terminal, before the node releases
# the service ports. Starting too soon dies in under a second with
#   could not setup network: could not use tcp port 9000: already used
# so wait for the ports as well as the status.
if [ "$RESTART" = 1 ]; then
  OLD=$(running_twin)
  if [ -n "$OLD" ]; then
    say "stopping t7-twin ($OLD)"
    fuzzball workflow stop "$OLD" >/dev/null 2>&1 || true
    printf '   waiting for it to end '
    while :; do
      s=$(fuzzball workflow describe "$OLD" 2>/dev/null | awk '/Status:/{print $2; exit}')
      case "$s" in *FINISHED*|*FAILED*|*ERRORED*|*CANCELED*|*STOPPED*) echo " ok"; break ;; esac
      printf '.'; sleep 10
    done
    printf '   letting the node free its ports '
    for _ in $(seq 1 12); do printf '.'; sleep 15; done   # 3 min: 90 s was not always enough
    echo " ok"
  fi
fi

WF=$(running_twin)
if [ -n "$WF" ]; then
  say "t7-twin already running ($WF)"
else
  say "starting the app (t7-twin: board + dispatcher + Nemotron)"
  fuzzball workflow validate fuzzball/ready/t7-twin.fz >/dev/null
  WF=$(fuzzball workflow start fuzzball/ready/t7-twin.fz --name t7-twin | wfid)
  [ -n "$WF" ] || { echo "could not read a workflow id from 'workflow start'"; exit 1; }
  echo "   $WF"
fi

# the board answers only once its readiness probe passes; Nemotron loads 30B of
# weights from hfcache first, so allow a long wait rather than failing early
printf '   board '
for _ in $(seq 1 120); do
  S=$(fuzzball workflow describe "$WF" 2>/dev/null | awk -F'|' '$3 ~ /board/ {gsub(/ /,"",$2); print $2; exit}')
  case "$S" in
    Running) echo " ready"; break ;;
    Failed|Errored|Canceled)
      echo " $S"; echo "   fuzzball workflow log $WF board" >&2; exit 1 ;;
  esac
  printf '.'; sleep 10
done

URL=$(board_link "$WF")
echo
if [ -n "$URL" ]; then
  echo "dashboard: $URL"
  [ "$OPEN" = 1 ] && command -v open >/dev/null && open "$URL"
else
  echo "no URL from 'endpoints list'; opening with the CLI:"
  [ "$OPEN" = 1 ] && fuzzball workflow connect --name board --endpoint web "$WF"
fi
echo "workflow:  $WF"
echo "link again: scripts/launch.sh --link      stop: fuzzball workflow stop $WF"
