# Upstream review notes

> Status after merging origin/main 12c063b: this file was written before PR 16 merged. Some patches are already on main (for example the winnow log quieting, as `--counts-only`). Check each patch against main before pasting it.

CodeRabbit reviewed PRs 14, 16 and 19 on sajor2000/icustrainciq. The findings below sit in teammates' code (ICU-Twin), so we did not change it here. Each section is a message ready to paste, with the patch text. Patch files are named as in the triage folder; diff paths are repo-relative to sajor2000/icustrainciq. Nothing in this file has been sent yet.

## Kaveri (Fuzzball workflows, launch.sh, runbook, clif_now)

Paste into the ICU-Twin thread for Kaveri.

CodeRabbit reviewed the ICU-Twin port (PR 16 and PR 19 on sajor2000/icustrainciq). Every finding below was checked against the code and has a patch attached. Please confirm 3 live, since we could not.

### pr19-07-08: t7-forecast.fz:75, ready/t7-forecast-room12.fz:75 and the unit ready file

Why it matters: The HOURS=0 shortcut skips the winnow and reuses +6 h cuts left by any earlier daytime run, so the 07:00 scheduled run can score a stale cut. Always winnow at the run clock.

Patch `pr19-07-08-always-winnow-at-run-clock.patch`:

```diff
diff --git a/backend/fuzzball/ready/t7-forecast-room12.fz b/backend/fuzzball/ready/t7-forecast-room12.fz
index 4c6405d..f4d289b 100644
--- a/backend/fuzzball/ready/t7-forecast-room12.fz
+++ b/backend/fuzzball/ready/t7-forecast-room12.fz
@@ -70,14 +70,11 @@ jobs:
       #!/bin/bash
       set -euo pipefail
       HOURS=0
-      # t7-ward already winnowed this ward at the 07:00 cut (clock 0). Re-winnow only when
-      # the demo clock moves the cut, which changes every stay's at-cut flags and labels.
-      if [ "$HOURS" = "0" ] && [ -f /store/stage/tokenized_output/held_out_for_inference.parquet ]; then
-        echo "winnow: skipped (t7-ward cut this ward at the same 07:00 clock)"
-      else
-        python -c "from icutwin.scoring.winnower import main; main()" /store/stage/tokenized_output \
-          --demo-clock-hours "$HOURS"
-      fi
+      # Always winnow at this run's clock: a clock-0 run after a +6 h run would otherwise reuse the
+      # +6 h cuts left in the persistent label files (features and labels would still agree, so no
+      # freshness check could catch it). 25 stays: seconds.
+      python -c "from icutwin.scoring.winnower import main; main()" /store/stage/tokenized_output \
+        --demo-clock-hours "$HOURS"
       # one short forward pass per stage-ward stay (25 in the final cohort)
       python -c "from icutwin.scoring.extractor import main; main()" /store/stage/tokenized_output -m /data/model_output/final
       ls /store/stage/tokenized_output/features-*.parquet | wc -l
diff --git a/backend/fuzzball/ready/t7-forecast-unit.fz b/backend/fuzzball/ready/t7-forecast-unit.fz
index d1ec58a..c506398 100644
--- a/backend/fuzzball/ready/t7-forecast-unit.fz
+++ b/backend/fuzzball/ready/t7-forecast-unit.fz
@@ -70,14 +70,11 @@ jobs:
       #!/bin/bash
       set -euo pipefail
       HOURS=0
-      # t7-ward already winnowed this ward at the 07:00 cut (clock 0). Re-winnow only when
-      # the demo clock moves the cut, which changes every stay's at-cut flags and labels.
-      if [ "$HOURS" = "0" ] && [ -f /store/stage/tokenized_output/held_out_for_inference.parquet ]; then
-        echo "winnow: skipped (t7-ward cut this ward at the same 07:00 clock)"
-      else
-        python -c "from icutwin.scoring.winnower import main; main()" /store/stage/tokenized_output \
-          --demo-clock-hours "$HOURS"
-      fi
+      # Always winnow at this run's clock: a clock-0 run after a +6 h run would otherwise reuse the
+      # +6 h cuts left in the persistent label files (features and labels would still agree, so no
+      # freshness check could catch it). 25 stays: seconds.
+      python -c "from icutwin.scoring.winnower import main; main()" /store/stage/tokenized_output \
+        --demo-clock-hours "$HOURS"
       # one short forward pass per stage-ward stay (25 in the final cohort)
       python -c "from icutwin.scoring.extractor import main; main()" /store/stage/tokenized_output -m /data/model_output/final
       ls /store/stage/tokenized_output/features-*.parquet | wc -l
diff --git a/backend/fuzzball/t7-forecast.fz b/backend/fuzzball/t7-forecast.fz
index 43b20c8..330c94c 100644
--- a/backend/fuzzball/t7-forecast.fz
+++ b/backend/fuzzball/t7-forecast.fz
@@ -70,14 +70,11 @@ jobs:
       #!/bin/bash
       set -euo pipefail
       HOURS=@HOURS@
-      # t7-ward already winnowed this ward at the 07:00 cut (clock 0). Re-winnow only when
-      # the demo clock moves the cut, which changes every stay's at-cut flags and labels.
-      if [ "$HOURS" = "0" ] && [ -f /store/stage/tokenized_output/held_out_for_inference.parquet ]; then
-        echo "winnow: skipped (t7-ward cut this ward at the same 07:00 clock)"
-      else
-        python -c "from icutwin.scoring.winnower import main; main()" /store/stage/tokenized_output \
-          --demo-clock-hours "$HOURS"
-      fi
+      # Always winnow at this run's clock: a clock-0 run after a +6 h run would otherwise reuse the
+      # +6 h cuts left in the persistent label files (features and labels would still agree, so no
+      # freshness check could catch it). 25 stays: seconds.
+      python -c "from icutwin.scoring.winnower import main; main()" /store/stage/tokenized_output \
+        --demo-clock-hours "$HOURS"
       # one short forward pass per stage-ward stay (25 in the final cohort)
       python -c "from icutwin.scoring.extractor import main; main()" /store/stage/tokenized_output -m /data/model_output/final
       ls /store/stage/tokenized_output/features-*.parquet | wc -l
```

### pr19-06: t7-forecast.fz:52 and the ready room12 file

Why it matters: The fallback t7-fit writes labels to /store/train, but the precheck and --baseline read /data/tokenized_output. Fall back to /store/train labels when job 4 did not write them.

Patch `pr19-06-fallback-training-labels.patch`:

```diff
diff --git a/backend/fuzzball/ready/t7-forecast-room12.fz b/backend/fuzzball/ready/t7-forecast-room12.fz
index 4c6405d..582be9e 100644
--- a/backend/fuzzball/ready/t7-forecast-room12.fz
+++ b/backend/fuzzball/ready/t7-forecast-room12.fz
@@ -49,7 +49,8 @@ jobs:
       # the probe comes from job 4 (workflows/job_4_probe in vaishvikc/ICU-Twin), fit on the training split beside
       # the model it belongs to; probe_src/ records the code that cut, extracted and fit it
       test -f /store/train/probe-final.joblib -a -f /store/train/probe-final.meta.json || { echo "no staged probe: see docs/RUNBOOK.md (job 4 fits it; it is staged to /store/train with its provenance sidecar)"; exit 1; }
-      test -f /data/tokenized_output/train_for_inference.parquet || { echo "no winnowed training split: job 4 writes it"; exit 1; }
+      # job 4 leaves the winnowed training labels in /data/tokenized_output; the t7-fit fallback leaves them in /store/train
+      test -f /data/tokenized_output/train_for_inference.parquet -o -f /store/train/train_for_inference.parquet || { echo "no winnowed training split: job 4 (or t7-fit) writes it"; exit 1; }
       test -d /store/stage/tokenized_output || { echo "no stage ward tokens: run t7-ward first"; exit 1; }
       test -f /store/stage/stage_ward.csv || { echo "no stage ward list: run t7-ward first"; exit 1; }
       test -d /data/model_output/final || { echo "no model at /data/model_output/final"; exit 1; }
@@ -96,6 +97,7 @@ jobs:
       WARD="--real-ward"   # empty: open demo ward; --real-ward: real MIMIC-IV rooms (opt-in, local only)
       STAGE=/store/stage/tokenized_output
       CLIF=/data/dashboard_data      # the ward's CLIF folder: the open demo, or a cohort folder on a team volume
+      BASE=/data/tokenized_output; test -f "$BASE/train_for_inference.parquet" || BASE=/store/train   # job 4's labels, else t7-fit's
       # rooms.py applies the saved probes (never refits) and writes rooms.json; ids stay on the volume
       COMMON="--model /data/model_output/final --probes /store/train/probe-final.joblib --stay-ids /store/stage/stage_ward.csv --out /store/rooms.json --demo-clock-hours $HOURS --demographics $CLIF --clif-now $CLIF --tz America/Chicago $WARD --names fake"
       if [ "$SCOPE" = "room" ]; then
@@ -104,6 +106,6 @@ jobs:
         python /store/code/app/rooms.py $STAGE $COMMON
         CAP=""; test -f /store/capacity.json && CAP="--capacity /store/capacity.json"
         python /store/code/app/aggregate.py $STAGE /store/forecast.json --beds 25 --score rep \
-          --baseline /data/tokenized_output --stage-csv /store/stage/stage_ward.csv --demo-clock-hours "$HOURS" --clif-now $CLIF --tz America/Chicago $WARD $CAP
+          --baseline "$BASE" --stage-csv /store/stage/stage_ward.csv --demo-clock-hours "$HOURS" --clif-now $CLIF --tz America/Chicago $WARD $CAP
         python -c "import json; d=json.load(open('/store/forecast.json')); print('made_at', d.get('made_at'), 'rows', len(d.get('resources', {})))"
       fi
diff --git a/backend/fuzzball/ready/t7-forecast-unit.fz b/backend/fuzzball/ready/t7-forecast-unit.fz
index d1ec58a..9d8b614 100644
--- a/backend/fuzzball/ready/t7-forecast-unit.fz
+++ b/backend/fuzzball/ready/t7-forecast-unit.fz
@@ -49,7 +49,8 @@ jobs:
       # the probe comes from job 4 (workflows/job_4_probe in vaishvikc/ICU-Twin), fit on the training split beside
       # the model it belongs to; probe_src/ records the code that cut, extracted and fit it
       test -f /store/train/probe-final.joblib -a -f /store/train/probe-final.meta.json || { echo "no staged probe: see docs/RUNBOOK.md (job 4 fits it; it is staged to /store/train with its provenance sidecar)"; exit 1; }
-      test -f /data/tokenized_output/train_for_inference.parquet || { echo "no winnowed training split: job 4 writes it"; exit 1; }
+      # job 4 leaves the winnowed training labels in /data/tokenized_output; the t7-fit fallback leaves them in /store/train
+      test -f /data/tokenized_output/train_for_inference.parquet -o -f /store/train/train_for_inference.parquet || { echo "no winnowed training split: job 4 (or t7-fit) writes it"; exit 1; }
       test -d /store/stage/tokenized_output || { echo "no stage ward tokens: run t7-ward first"; exit 1; }
       test -f /store/stage/stage_ward.csv || { echo "no stage ward list: run t7-ward first"; exit 1; }
       test -d /data/model_output/final || { echo "no model at /data/model_output/final"; exit 1; }
@@ -96,6 +97,7 @@ jobs:
       WARD="--real-ward"   # empty: open demo ward; --real-ward: real MIMIC-IV rooms (opt-in, local only)
       STAGE=/store/stage/tokenized_output
       CLIF=/data/dashboard_data      # the ward's CLIF folder: the open demo, or a cohort folder on a team volume
+      BASE=/data/tokenized_output; test -f "$BASE/train_for_inference.parquet" || BASE=/store/train   # job 4's labels, else t7-fit's
       # rooms.py applies the saved probes (never refits) and writes rooms.json; ids stay on the volume
       COMMON="--model /data/model_output/final --probes /store/train/probe-final.joblib --stay-ids /store/stage/stage_ward.csv --out /store/rooms.json --demo-clock-hours $HOURS --demographics $CLIF --clif-now $CLIF --tz America/Chicago $WARD --names fake"
       if [ "$SCOPE" = "room" ]; then
@@ -104,6 +106,6 @@ jobs:
         python /store/code/app/rooms.py $STAGE $COMMON
         CAP=""; test -f /store/capacity.json && CAP="--capacity /store/capacity.json"
         python /store/code/app/aggregate.py $STAGE /store/forecast.json --beds 25 --score rep \
-          --baseline /data/tokenized_output --stage-csv /store/stage/stage_ward.csv --demo-clock-hours "$HOURS" --clif-now $CLIF --tz America/Chicago $WARD $CAP
+          --baseline "$BASE" --stage-csv /store/stage/stage_ward.csv --demo-clock-hours "$HOURS" --clif-now $CLIF --tz America/Chicago $WARD $CAP
         python -c "import json; d=json.load(open('/store/forecast.json')); print('made_at', d.get('made_at'), 'rows', len(d.get('resources', {})))"
       fi
diff --git a/backend/fuzzball/t7-forecast.fz b/backend/fuzzball/t7-forecast.fz
index 43b20c8..ca42514 100644
--- a/backend/fuzzball/t7-forecast.fz
+++ b/backend/fuzzball/t7-forecast.fz
@@ -49,7 +49,8 @@ jobs:
       # the probe comes from job 4 (workflows/job_4_probe in vaishvikc/ICU-Twin), fit on the training split beside
       # the model it belongs to; probe_src/ records the code that cut, extracted and fit it
       test -f /store/train/probe-final.joblib -a -f /store/train/probe-final.meta.json || { echo "no staged probe: see docs/RUNBOOK.md (job 4 fits it; it is staged to /store/train with its provenance sidecar)"; exit 1; }
-      test -f /data/tokenized_output/train_for_inference.parquet || { echo "no winnowed training split: job 4 writes it"; exit 1; }
+      # job 4 leaves the winnowed training labels in /data/tokenized_output; the t7-fit fallback leaves them in /store/train
+      test -f /data/tokenized_output/train_for_inference.parquet -o -f /store/train/train_for_inference.parquet || { echo "no winnowed training split: job 4 (or t7-fit) writes it"; exit 1; }
       test -d /store/stage/tokenized_output || { echo "no stage ward tokens: run t7-ward first"; exit 1; }
       test -f /store/stage/stage_ward.csv || { echo "no stage ward list: run t7-ward first"; exit 1; }
       test -d /data/model_output/final || { echo "no model at /data/model_output/final"; exit 1; }
@@ -96,6 +97,7 @@ jobs:
       WARD="@WARD_FLAG@"   # empty: open demo ward; --real-ward: real MIMIC-IV rooms (opt-in, local only)
       STAGE=/store/stage/tokenized_output
       CLIF=@CLIF_DIR@      # the ward's CLIF folder: the open demo, or a cohort folder on a team volume
+      BASE=/data/tokenized_output; test -f "$BASE/train_for_inference.parquet" || BASE=/store/train   # job 4's labels, else t7-fit's
       # rooms.py applies the saved probes (never refits) and writes rooms.json; ids stay on the volume
       COMMON="--model /data/model_output/final --probes /store/train/probe-final.joblib --stay-ids /store/stage/stage_ward.csv --out /store/rooms.json --demo-clock-hours $HOURS --demographics $CLIF --clif-now $CLIF --tz America/Chicago $WARD @NAMES@"
       if [ "$SCOPE" = "room" ]; then
@@ -104,6 +106,6 @@ jobs:
         python /store/code/app/rooms.py $STAGE $COMMON
         CAP=""; test -f /store/capacity.json && CAP="--capacity /store/capacity.json"
         python /store/code/app/aggregate.py $STAGE /store/forecast.json --beds 25 --score rep \
-          --baseline /data/tokenized_output --stage-csv /store/stage/stage_ward.csv --demo-clock-hours "$HOURS" --clif-now $CLIF --tz America/Chicago $WARD $CAP
+          --baseline "$BASE" --stage-csv /store/stage/stage_ward.csv --demo-clock-hours "$HOURS" --clif-now $CLIF --tz America/Chicago $WARD $CAP
         python -c "import json; d=json.load(open('/store/forecast.json')); print('made_at', d.get('made_at'), 'rows', len(d.get('resources', {})))"
       fi
```

### pr19-13: backend/scripts/launch.sh:143

Why it matters: fuzzball describe prints a running job as Started; the loop only breaks on Running, so every launch waits the full 20 minutes (per docs.ciq.com status page; please confirm live).

Patch `pr19-13-launch-board-started-status.patch`:

```diff
diff --git a/backend/scripts/launch.sh b/backend/scripts/launch.sh
index bd2baf4..ca26faf 100755
--- a/backend/scripts/launch.sh
+++ b/backend/scripts/launch.sh
@@ -140,7 +140,7 @@ printf '   board '
 for _ in $(seq 1 120); do
   S=$(fuzzball workflow describe "$WF" 2>/dev/null | awk -F'|' '$3 ~ /board/ {gsub(/ /,"",$2); print $2; exit}')
   case "$S" in
-    Running) echo " ready"; break ;;
+    Running|Started) echo " ready"; break ;;
     Failed|Errored|Canceled)
       echo " $S"; echo "   fuzzball workflow log $WF board" >&2; exit 1 ;;
   esac
```

### pr19-11: launch.sh:52

Why it matters: running_twin matches only Started, so a Pending twin gets a duplicate submit.

Patch `pr19-11-launch-reuse-queued-twin.patch`:

```diff
diff --git a/backend/scripts/launch.sh b/backend/scripts/launch.sh
index bd2baf4..299bb57 100755
--- a/backend/scripts/launch.sh
+++ b/backend/scripts/launch.sh
@@ -49,7 +49,7 @@ wait_for() { # wait_for <id> <name>
 
 running_twin() {
   fuzzball workflow list 2>/dev/null |
-    awk -F'|' '$4 ~ /Started/ && $5 ~ /t7-twin/ {gsub(/ /,"",$1); print $1; exit}'
+    awk -F'|' 'tolower($4) !~ /finished|failed|errored|cancel|stopped|down/ && $5 ~ /t7-twin/ {gsub(/ /,"",$1); print $1; exit}'
 }
 
 board_link() { # board_link <workflow-id>
```

### pr19-12: launch.sh:84

Why it matters: --code and --all publish while a forecast, fit or ward job is active; refuse instead.

Patch `pr19-12-launch-no-publish-during-forecast.patch`:

```diff
diff --git a/backend/scripts/launch.sh b/backend/scripts/launch.sh
index bd2baf4..6c84aa4 100755
--- a/backend/scripts/launch.sh
+++ b/backend/scripts/launch.sh
@@ -79,7 +79,14 @@ if [ -n "$READY_REF" ] && [ "$READY_REF" != "$HEAD_REF" ]; then
 fi
 
 # ---------- 1. publish code ----------
+# t7-code swaps /store/code and /store/py, which a running forecast, t7-fit or t7-ward imports
+busy_jobs() {
+  fuzzball workflow list 2>/dev/null |
+    awk -F'|' 'tolower($4) !~ /finished|failed|errored|cancel|stopped|down/ && $5 ~ /t7-(fc-)?(forecast|fit|ward)/ {gsub(/ /,"",$5); print $5}'
+}
 if [ "$WANT_CODE" = 1 ]; then
+  BUSY=$(busy_jobs)
+  [ -z "$BUSY" ] || { echo "not publishing code: still active on the cluster: $BUSY" >&2; exit 1; }
   say "publishing code (t7-code)"
   ID=$(fuzzball workflow start fuzzball/ready/t7-code.fz --name t7-fc-code | wfid)
   wait_for "$ID" "t7-code"
```

### pr19-m7: launch.sh:148

Why it matters: The readiness loop falls through to success after 120 polls; exit nonzero on timeout.

Patch `pr19-m7-launch-fail-on-readiness-timeout.patch`:

```diff
diff --git a/backend/scripts/launch.sh b/backend/scripts/launch.sh
index bd2baf4..c959515 100755
--- a/backend/scripts/launch.sh
+++ b/backend/scripts/launch.sh
@@ -137,15 +137,17 @@ fi
 # the board answers only once its readiness probe passes; Nemotron loads 30B of
 # weights from hfcache first, so allow a long wait rather than failing early
 printf '   board '
+READY=0
 for _ in $(seq 1 120); do
   S=$(fuzzball workflow describe "$WF" 2>/dev/null | awk -F'|' '$3 ~ /board/ {gsub(/ /,"",$2); print $2; exit}')
   case "$S" in
-    Running) echo " ready"; break ;;
+    Running|Started) echo " ready"; READY=1; break ;;
     Failed|Errored|Canceled)
       echo " $S"; echo "   fuzzball workflow log $WF board" >&2; exit 1 ;;
   esac
   printf '.'; sleep 10
 done
+[ "$READY" = 1 ] || { echo " not ready after 20 min"; echo "   fuzzball workflow describe $WF" >&2; exit 1; }
 
 URL=$(board_link "$WF")
 echo
```

### pr19-m6: launch.sh:56

Why it matters: grep with no match under pipefail and set -e skips the connect fallback when the URL is empty.

Patch `pr19-m6-launch-empty-url-falls-through.patch`:

```diff
diff --git a/backend/scripts/launch.sh b/backend/scripts/launch.sh
index bd2baf4..29719b2 100755
--- a/backend/scripts/launch.sh
+++ b/backend/scripts/launch.sh
@@ -53,7 +53,7 @@ running_twin() {
 }
 
 board_link() { # board_link <workflow-id>
-  fuzzball workflow endpoints list 2>/dev/null | grep "$1" | grep -oE 'https://[^ |]+' | head -1
+  fuzzball workflow endpoints list 2>/dev/null | grep "$1" | grep -oE 'https://[^ |]+' | head -1 || true
 }
 
 # ---------- link only ----------
```

### pr19-00: icutwin clif_now vitals_before_cut (rooms.py:251 on the PR 19 tree)

Why it matters: is_not_null keeps inf and NaN, so write_json can emit Infinity (invalid JSON). Drop non-finite values before the median.

Patch `pr19-00-vitals-non-finite.patch`:

```diff
diff --git a/backend/app/clif_now.py b/backend/app/clif_now.py
index dd06081..f873c77 100644
--- a/backend/app/clif_now.py
+++ b/backend/app/clif_now.py
@@ -22,6 +22,7 @@ the winnower sets it, `stay_cuts`), not the site's wall-clock 07:00.
 """
 
 import datetime as dt
+import math
 import pathlib
 
 import polars as pl
@@ -234,7 +235,9 @@ def vitals_before_cut(clif_dir, stays: dict) -> dict[str, dict]:
         return {}
     cols = [HOSP, "recorded_dttm", "vital_category", "vital_value"]
     lf = _read(clif_dir, "vitals", cols, ["recorded_dttm"]).filter(
-        pl.col("vital_category").is_in(VITALS) & pl.col("vital_value").is_not_null()
+        pl.col("vital_category").is_in(VITALS)
+        & pl.col("vital_value").is_not_null()
+        & pl.col("vital_value").is_finite()  # NaN / inf would reach rooms.json as invalid JSON
     )
     span = dt.timedelta(hours=VITALS_HOURS)
     ago = (pl.col("cut") - pl.col("recorded_dttm")).dt.total_seconds()
@@ -250,6 +253,8 @@ def vitals_before_cut(clif_dir, stays: dict) -> dict[str, dict]:
     )
     out: dict[str, dict] = {}
     for sid, cat, hh, v in rows.iter_rows():
+        if v is None or not math.isfinite(v):
+            continue
         series = out.setdefault(sid, {}).setdefault(cat, [])
         series.append({"h": int(hh), "v": round(float(v), 1)})
     return out
diff --git a/backend/tests/test_clif_now.py b/backend/tests/test_clif_now.py
index 7572dd4..97496f4 100644
--- a/backend/tests/test_clif_now.py
+++ b/backend/tests/test_clif_now.py
@@ -259,3 +259,23 @@ def test_vitals_before_cut_hourly_median_relative_hours(tmp_path):
 
 def test_vitals_before_cut_without_a_vitals_table(tmp_path):
     assert clif_now.vitals_before_cut(_clif(tmp_path), {"s1": CUT}) == {}
+
+
+def test_vitals_before_cut_drops_non_finite_readings(tmp_path):
+    d = _clif(tmp_path, ids=("s1",))
+    pl.DataFrame(
+        [
+            ("s1", h(0.5), "heart_rate", float("inf")),
+            ("s1", h(0.4), "heart_rate", 100.0),
+            ("s1", h(1.5), "map", float("nan")),
+        ],
+        schema={
+            "hospitalization_id": pl.String,
+            "recorded_dttm": pl.Datetime("us", "UTC"),
+            "vital_category": pl.String,
+            "vital_value": pl.Float64,
+        },
+        orient="row",
+    ).write_parquet(d / "clif_vitals.parquet")
+    got = clif_now.vitals_before_cut(d, {"s1": CUT})
+    assert got == {"s1": {"heart_rate": [{"h": 1, "v": 100.0}]}}
```

### pr19-03: RUNBOOK.md:97

Why it matters: No restart step after t7-code; launch.sh --restart exists but is undocumented.

Patch `pr19-03-runbook-restart-after-code.patch`:

```diff
diff --git a/backend/docs/RUNBOOK.md b/backend/docs/RUNBOOK.md
index f04d4b6..650b1c7 100644
--- a/backend/docs/RUNBOOK.md
+++ b/backend/docs/RUNBOOK.md
@@ -82,7 +82,15 @@ fuzzball workflow start fuzzball/ready/t7-code.fz --name t7-fc-code
 ```
 
 `t7-code` is CPU-only and safe beside training, but **not** beside a forecast,
-`t7-fit` or `t7-ward` — it swaps the code they import.
+`t7-fit` or `t7-ward` — it swaps the code they import (`launch.sh --code` refuses
+while one of them is active).
+
+The board and dispatcher import their code once, when `t7-twin` starts. A running
+`t7-twin` keeps serving the previous code after `t7-code` finishes, so restart it:
+
+```bash
+bash scripts/launch.sh --restart
+```
 
 ---
 
```

### pr19-04: RUNBOOK.md:147

Why it matters: The cp for the probe needs the /data and /store mounts, which a laptop does not have; use a small staging job. (Syntax checked locally, server validation timed out.)

Patch `pr19-04-runbook-probe-staging-job.patch`:

```diff
diff --git a/backend/docs/RUNBOOK.md b/backend/docs/RUNBOOK.md
index f04d4b6..55afdbb 100644
--- a/backend/docs/RUNBOOK.md
+++ b/backend/docs/RUNBOOK.md
@@ -143,15 +143,31 @@ beside the model it belongs to. The forecast reads it from
 `/store/train/probe-final.joblib`; `fuzzball/t7-fit.fz` is a fallback for when
 job 4 has not run. If `twin-store` is ever recreated, stage it again:
 
-```bash
-cp /data/model_output/final/probe.joblib /store/train/probe-final.joblib
-```
-
-and write its provenance sidecar (`apply_probes` refuses a probe without one):
-
-```python
-from icutwin.scoring.rep_based import write_scores_meta
-write_scores_meta(Path("/store/train/probe-final.joblib"), Path("/data/model_output/final"))
+The copy needs the cluster's `/data` and `/store` mounts, so it cannot run from the
+laptop. Run it as a one-off job (save as `stage-probe.fz`, then
+`fuzzball workflow validate stage-probe.fz && fuzzball workflow start stage-probe.fz --name t7-fc-stage-probe`).
+It creates `/store/train`, copies the probe and writes its provenance sidecar
+(`apply_probes` refuses a probe without one):
+
+```yaml
+version: v4
+volumes:
+  data: {name: mimic_clif, use: team7}
+  store: {name: twin-store, use: team7}
+jobs:
+  stage-probe:
+    image: {uri: "docker://nvcr.io/nvidia/pytorch:25.11-py3"}
+    mounts: {/data: data, /store: store}
+    env: [HOME=/tmp, TMPDIR=/tmp, "PYTHONPATH=/store/py:/store/code"]
+    resource: {cpu: {cores: 2}, memory: {size: 8GB}}
+    policy: {timeout: {execute: 10m}}
+    script: |
+      #!/bin/bash
+      set -euo pipefail
+      mkdir -p /store/train
+      cp /data/model_output/final/probe.joblib /store/train/probe-final.joblib
+      python -c 'import pathlib; from icutwin.scoring.rep_based import write_scores_meta; write_scores_meta(pathlib.Path("/store/train/probe-final.joblib"), pathlib.Path("/data/model_output/final"))'
+      ls -l /store/train/probe-final.joblib /store/train/probe-final.meta.json
 ```
 
 **Two GPUs total.** Nemotron holds one for the whole demo, the forecast uses the
```

### pr19-m5: RUNBOOK.md:153

Why it matters: Path is used but not imported. pr19-04 supersedes this; send one of them.

Patch `pr19-m5-runbook-import-path.patch`:

```diff
diff --git a/backend/docs/RUNBOOK.md b/backend/docs/RUNBOOK.md
index f04d4b6..7c35407 100644
--- a/backend/docs/RUNBOOK.md
+++ b/backend/docs/RUNBOOK.md
@@ -150,6 +150,7 @@ cp /data/model_output/final/probe.joblib /store/train/probe-final.joblib
 and write its provenance sidecar (`apply_probes` refuses a probe without one):
 
 ```python
+from pathlib import Path
 from icutwin.scoring.rep_based import write_scores_meta
 write_scores_meta(Path("/store/train/probe-final.joblib"), Path("/data/model_output/final"))
 ```
```

### pr16-11: t7-lookahead-forecast.fz:57 (PR 16 branch)

Why it matters: The cut uses now() at publish time but HOURS at dispatch, so it is wrong across 07:00. Freeze the cut at dispatch with a new @CUT_ANCHOR@ token.

Patch `pr16-11-dispatch-time-cut-anchor.patch`:

```diff
diff --git a/backend/app/dispatcher.py b/backend/app/dispatcher.py
index 568c208..6599ee5 100644
--- a/backend/app/dispatcher.py
+++ b/backend/app/dispatcher.py
@@ -234,6 +234,7 @@ def render_template(
     names: str = "",
     code_ref: str = "",
     code_sha256: str = "",
+    cut_anchor: str = "",
 ) -> str:
     """every token of any Fuzzfile in fuzzball/, in one place: the dispatcher's
     per-run copies and scripts/render_fz.py (people) both come through here.
@@ -251,6 +252,15 @@ def render_template(
         text.replace("@SCOPE@", scope)
         .replace("@ROOM@", str(int(room or 0)))
         .replace("@HOURS@", f"{float(hours):g}")
+        # the morning cut the demo clock counts from, fixed when the run is rendered, so
+        # a run that crosses 07:00 while extracting keeps the cut its HOURS belong to
+        .replace(
+            "@CUT_ANCHOR@",
+            cut_anchor
+            or last_cut(dt.datetime.now(zoneinfo.ZoneInfo("America/Chicago")))
+            .astimezone(dt.timezone.utc)
+            .isoformat(timespec="seconds"),
+        )
     )
     if code_ref:
         text = text.replace("@CODE_REF@", code_ref)
@@ -543,7 +553,12 @@ class Dispatcher:
 
     # ---- starting a run ----------------------------------------------------------
     def render(
-        self, scope: str, room: int | None, hours: float, name: str
+        self,
+        scope: str,
+        room: int | None,
+        hours: float,
+        name: str,
+        cut_anchor: str = "",
     ) -> pathlib.Path:
         """a per-run copy of the template with the run's scope, room, demo clock and ward mode"""
         text = render_template(
@@ -551,6 +566,7 @@ class Dispatcher:
             scope=scope,
             room=room,
             hours=hours,
+            cut_anchor=cut_anchor,
             real_ward=self.real_ward,
             clif_dir=self.clif_dir,
             ward_ids=self.ward_ids,
@@ -627,7 +643,10 @@ class Dispatcher:
                 "pending": True,
             }
         try:  # the CLI call runs without the lock; the pending entry blocks a second start
-            path = self.render(scope, room, hours, name)
+            anchor = last_cut(now, self.at).astimezone(dt.timezone.utc)
+            path = self.render(
+                scope, room, hours, name, anchor.isoformat(timespec="seconds")
+            )
             wid = workflow_id(self._cli("workflow", "start", str(path), "--name", name))
         except Exception as e:
             with self.lock:
diff --git a/backend/fuzzball/t7-lookahead-forecast.fz b/backend/fuzzball/t7-lookahead-forecast.fz
index 1ae023e..974c7c2 100644
--- a/backend/fuzzball/t7-lookahead-forecast.fz
+++ b/backend/fuzzball/t7-lookahead-forecast.fz
@@ -54,7 +54,7 @@ jobs:
       if test -f /context/capacity.json; then CAP=(--capacity /context/capacity.json); fi
       # The replay offset moves each historical stay's own cut, rather than asserting
       # that all historical stays occupied one ICU on the same calendar morning.
-      CUT=$(python -c 'import datetime as d,sys; from zoneinfo import ZoneInfo; from app.dispatcher import last_cut; z=ZoneInfo("America/Chicago"); n=d.datetime.now(z); print((last_cut(n).astimezone(d.UTC)+d.timedelta(hours=float(sys.argv[1]))).astimezone(z).isoformat(timespec="seconds"))' "$HOURS")
+      CUT=$(python -c 'import datetime as d,sys; from zoneinfo import ZoneInfo; print((d.datetime.fromisoformat(sys.argv[1])+d.timedelta(hours=float(sys.argv[2]))).astimezone(ZoneInfo("America/Chicago")).isoformat(timespec="seconds"))' "@CUT_ANCHOR@" "$HOURS")
       # --no-extract applies saved probes to the GPU features; no second CPU forward pass.
       python /store/code/scripts/run_cohort.py "$CLIF_DIR" \
         --ward-ids @WARD_IDS@ --tokenized-output "$ROOT" \
diff --git a/backend/tests/test_dispatcher.py b/backend/tests/test_dispatcher.py
index 1d8b71c..b37f85a 100644
--- a/backend/tests/test_dispatcher.py
+++ b/backend/tests/test_dispatcher.py
@@ -643,6 +643,7 @@ def render_any(name: str, **ward) -> str:
     text = text.replace("@CODE_REF@", "0" * 40).replace("@CODE_SHA256@", "1" * 64)
     text = (
         text.replace("@SCOPE@", "unit").replace("@ROOM@", "0").replace("@HOURS@", "0")
+        .replace("@CUT_ANCHOR@", "2026-11-15T13:00:00+00:00")
     )
     return d.render_ward(text, **ward)
 
@@ -1094,3 +1095,16 @@ def test_a_failed_token_refresh_is_retried_within_the_hour(tmp_path, monkeypatch
     monkeypatch.setattr(d, "refresh_token", lambda: calls.append(2) or True)
     s.tick()
     assert calls == [1, 2] and s.last_refresh == t0 + 3601
+
+
+def test_forecast_cut_anchor_is_fixed_when_the_run_is_rendered():
+    import pathlib
+
+    from app.dispatcher import render_template
+
+    fz = pathlib.Path(__file__).resolve().parents[1] / "fuzzball/t7-lookahead-forecast.fz"
+    text = render_template(
+        fz.read_text(), hours=6, cut_anchor="2026-11-15T13:00:00+00:00",
+        ward_ids="x", names="",
+    )
+    assert "@CUT_ANCHOR@" not in text and "2026-11-15T13:00:00+00:00" in text
```

### pr16-10: t7-lookahead-forecast.fz:35 (PR 16 branch)

Why it matters: The winnower logs outcome rates of the real 25-stay cohort at INFO into workflow logs. We already applied the same logger quieting to our t7-forecast, t7-ward and t7-fit (commit on fix/review-patches); worth doing in ICU-Twin too.

Patch `pr16-10-quiet-winnower-rates.patch`:

```diff
diff --git a/backend/fuzzball/t7-lookahead-forecast.fz b/backend/fuzzball/t7-lookahead-forecast.fz
index 1ae023e..ecb890f 100644
--- a/backend/fuzzball/t7-lookahead-forecast.fz
+++ b/backend/fuzzball/t7-lookahead-forecast.fz
@@ -31,7 +31,8 @@ jobs:
       test -f /store/model/mdl-icutwin/config.json || { echo "trained forecaster prerequisite missing; context stays pending"; exit 1; }
       test -f /context/roster.csv || { echo "private roster prerequisite missing"; exit 1; }
       test -f "$ROOT/vocab.yaml" || { echo "selected25 cache prerequisite missing: run t7-lookahead-prepare once"; exit 1; }
-      python -c 'from icutwin.scoring.winnower import main; main()' "$ROOT" \
+      # The winnower logs outcome rates of the selected cohort at INFO; quiet that logger so workflow logs keep counts only.
+      python -c 'import logging; from icutwin.common import logger; logger.setLevel(logging.WARNING); from icutwin.scoring.winnower import main; main()' "$ROOT" \
         -c /store/code/examples/winnow_24h.yaml --demo-clock-hours @HOURS@
       python -c 'from icutwin.scoring.extractor import main; main()' "$ROOT" \
         --model /store/model/mdl-icutwin --stay-ids /context/roster.csv
```

## Vaishvik (icutwin/ scoring and training; also for ICU-Twin)

Paste into the ICU-Twin thread for Vaishvik.

CodeRabbit findings on icutwin/ code in our port, all verified, patches attached.

### pr19-09: icutwin/scoring/metrics.py:138

Why it matters: nan_to_num turns unavailable scores into 0, which are then scored and reported as metrics. Filter non-finite predictions instead.

Patch `pr19-09-metrics-nan-not-zero.patch`:

```diff
diff --git a/backend/icutwin/scoring/metrics.py b/backend/icutwin/scoring/metrics.py
index f866e2b..30c4a45 100644
--- a/backend/icutwin/scoring/metrics.py
+++ b/backend/icutwin/scoring/metrics.py
@@ -125,9 +125,11 @@ def summarize_preds(logger, df_res, target_tokens, n_samples: int = 10_000) -> d
                     .to_numpy()
                     .T
                 )
+                y_score = y_score.astype(float)
                 ok = y_qual.astype(bool)
-                if (nf := np.sum(~np.isfinite(y_score[ok].astype(float)))) > 0:
+                if (nf := np.sum(~np.isfinite(y_score[ok]))) > 0:
                     logger.warning(f"{nf} non-finite {method} estimates for {tt}.")
+                ok &= np.isfinite(y_score)  # an unavailable prediction is not a score of 0
                 if len(np.unique(y_true[ok])) < 2:
                     logger.warning(
                         f"{ok.sum()} scoreable {method} rows for {tt}, "
@@ -135,7 +137,7 @@ def summarize_preds(logger, df_res, target_tokens, n_samples: int = 10_000) -> d
                     )
                     continue
                 y_true = y_true[ok].astype(int)
-                y_score = np.nan_to_num(y_score[ok].astype(float))
+                y_score = y_score[ok]
                 v_rare = y_true.mean().item() < 0.001
                 if v_rare:
                     logger.warning("using stratified sampling due to rarity")
diff --git a/backend/tests/test_metrics.py b/backend/tests/test_metrics.py
index 5349f39..bc3c4fa 100644
--- a/backend/tests/test_metrics.py
+++ b/backend/tests/test_metrics.py
@@ -91,3 +91,14 @@ def test_one_class_is_skipped_not_crashed():
         {"X_past": [False] * 4, "X_future": [False] * 4, "X_rep_score": [0.1] * 4}
     )
     assert summarize_preds(Capture(), df, ["X"], n_samples=10) == {}
+
+
+def test_unavailable_predictions_are_not_scored_as_zero():
+    df = pl.DataFrame(  # a probe skipped in training: every score NaN, held-out labels have both classes
+        {
+            "X_past": [False] * 4,
+            "X_future": [False, True, False, True],
+            "X_rep_score": [float("nan")] * 4,
+        }
+    )
+    assert summarize_preds(Capture(), df, ["X"], n_samples=10) == {}
```

### pr19-10: icutwin/scoring/rep_based.py:155

Why it matters: RepBasedScorer with --probe never calls verify_scores, so the probe sidecar is never checked.

Patch `pr19-10-probe-option-verifies-provenance.patch`:

```diff
diff --git a/backend/icutwin/scoring/rep_based.py b/backend/icutwin/scoring/rep_based.py
index a4f8c92..4e46082 100644
--- a/backend/icutwin/scoring/rep_based.py
+++ b/backend/icutwin/scoring/rep_based.py
@@ -152,6 +152,8 @@ class RepBasedScorer:
     ):
         self.root, self.cfg = root, cfg
         # fitted probe per task; loaded from `probe` (inference only) or fit on train
+        if probe:  # a probe fit on other weights would score without any error
+            verify_scores(pathlib.Path(probe).expanduser().resolve(), model_home)
         self.probes = joblib.load(probe) if probe else {}
         self.fit_info = {}  # training side of each fit, for the metrics file
         self.fit = probe is None
diff --git a/backend/tests/test_rep_probes.py b/backend/tests/test_rep_probes.py
index 3aee45b..1a8f4c3 100644
--- a/backend/tests/test_rep_probes.py
+++ b/backend/tests/test_rep_probes.py
@@ -111,3 +111,17 @@ def test_scores_file_provenance(cohorts, tmp_path):
     (home / "model.safetensors").write_bytes(b"weights-v2")
     with pytest.raises(ValueError, match="other weights"):
         rep_based.verify_scores(out, home)
+
+
+def test_probe_option_refuses_a_probe_from_other_weights(cohorts, tmp_path):
+    train, _, _ = cohorts
+    home = _home(tmp_path, b"weights-v1")
+    probe = _fit(train, home)
+    cfg = OmegaConf.create(CFG)
+    rep_based.RepBasedScorer(train, {}, home, cfg, "logistic", probe=probe)  # same weights
+    (home / "model.safetensors").write_bytes(b"weights-v2")
+    with pytest.raises(ValueError, match="other weights"):
+        rep_based.RepBasedScorer(train, {}, home, cfg, "logistic", probe=probe)
+    rep_based.scores_meta_path(probe).unlink()
+    with pytest.raises(ValueError, match="no probe-"):
+        rep_based.RepBasedScorer(train, {}, home, cfg, "logistic", probe=probe)
```

### pr16-12: run_cohort.py:222 (patch written against the PR 19 tree)

Why it matters: Features are not tied to the weights, so --no-extract can reuse stale features. Add weights_sha256 to the features and refuse a mismatch or a missing value in apply_probes. Six legacy test fixtures (test_lookahead, test_rep_probes) need the weights_sha256 column; that refusal of legacy files is intended.

Patch `pr16-12-features-carry-weights-digest.patch`:

```diff
diff --git a/backend/icutwin/scoring/extractor.py b/backend/icutwin/scoring/extractor.py
index f6a462b..adf96df 100644
--- a/backend/icutwin/scoring/extractor.py
+++ b/backend/icutwin/scoring/extractor.py
@@ -36,6 +36,7 @@ from transformers import AutoModelForCausalLM
 
 from icutwin.common import logger, merge_config
 from icutwin.model.decoder import ExactPrefix, load_split, stay_offsets
+from icutwin.scoring.rep_based import weights_digest
 
 SPLITS = ("train", "tuning", "held_out")
 
@@ -183,7 +184,10 @@ class Extractor:
                 order.select(
                     ["hospitalization_id"] if n == 1 else ["row", "hospitalization_id"]
                 )
-                .with_columns(features=pl.Series(list(feats)))
+                .with_columns(
+                    features=pl.Series(list(feats)),
+                    weights_sha256=pl.lit(weights_digest(self.model_home)),
+                )
                 .join(stored_cuts(src), on="hospitalization_id", how="left")
             )
             if stay_ids is not None:
diff --git a/backend/icutwin/scoring/rep_based.py b/backend/icutwin/scoring/rep_based.py
index a4f8c92..b8b8f33 100644
--- a/backend/icutwin/scoring/rep_based.py
+++ b/backend/icutwin/scoring/rep_based.py
@@ -146,6 +146,27 @@ def check_features_current(root, model_name: str, stay_ids=None) -> None:
         )
 
 
+def check_features_weights(root, model_name: str, model_home, stay_ids=None) -> None:
+    """refuse features extracted with other weights than model_home's: the cut check
+    cannot see that. icutwin-extract stores `weights_sha256` on every row; a file
+    without it (made before it was stored) is refused too, so it is extracted again."""
+    root, want = pathlib.Path(root), weights_digest(model_home)
+    for s in SPLITS:
+        f = root / f"features-{s}-{model_name}.parquet"
+        if not f.is_file():
+            continue
+        if "weights_sha256" not in pl.read_parquet_schema(f):
+            raise StaleFeatures(f"{f.name} has no weights checksum: run icutwin-extract again")
+        got = pl.read_parquet(f, columns=["hospitalization_id", "weights_sha256"])
+        if stay_ids is not None:
+            got = got.filter(pl.col("hospitalization_id").is_in(list(stay_ids)))
+        if got.filter(pl.col("weights_sha256").ne_missing(want)).height:
+            raise StaleFeatures(
+                f"{f.name} was extracted with other weights than {model_home}: "
+                "run icutwin-extract again"
+            )
+
+
 class RepBasedScorer:
     def __init__(
         self, root, lookup, model_home, cfg, estimator_type="logistic-CV-z", probe=None
@@ -343,6 +364,7 @@ def apply_probes(
     verify_scores(probe, model_home)
     probes = joblib.load(probe)
     check_features_current(root, model_name, stay_ids)
+    check_features_weights(root, model_name, model_home, stay_ids)
     labels, xs = [], []
     for s in SPLITS:
         f, lab = (
diff --git a/backend/tests/test_rep_probes.py b/backend/tests/test_rep_probes.py
index 3aee45b..671ceeb 100644
--- a/backend/tests/test_rep_probes.py
+++ b/backend/tests/test_rep_probes.py
@@ -111,3 +111,23 @@ def test_scores_file_provenance(cohorts, tmp_path):
     (home / "model.safetensors").write_bytes(b"weights-v2")
     with pytest.raises(ValueError, match="other weights"):
         rep_based.verify_scores(out, home)
+
+
+def _stamp(root, digest):
+    for f in root.glob("features-*.parquet"):
+        pl.read_parquet(f).with_columns(
+            weights_sha256=pl.lit(digest, dtype=pl.String)
+        ).write_parquet(f)
+
+
+def test_features_from_other_weights_or_without_a_checksum_are_refused(cohorts, tmp_path):
+    train, demo, _ = cohorts
+    home = _home(tmp_path, b"weights-v1")
+    probe = _fit(train, home)
+    with pytest.raises(rep_based.StaleFeatures, match="no weights checksum"):
+        rep_based.apply_probes(demo, home, probe)  # legacy features
+    _stamp(demo, "0" * 64)
+    with pytest.raises(rep_based.StaleFeatures, match="other weights"):
+        rep_based.apply_probes(demo, home, probe)
+    _stamp(demo, rep_based.weights_digest(home))
+    rep_based.apply_probes(demo, home, probe)
```

### pr19-m0: icutwin/scoring/extractor.py:186

Why it matters: An empty shard gets a Null feature dtype, which breaks merge_shards.

Patch `pr19-m0-extractor-empty-shard-dtype.patch`:

```diff
diff --git a/backend/icutwin/scoring/extractor.py b/backend/icutwin/scoring/extractor.py
index f6a462b..1a4e6dd 100644
--- a/backend/icutwin/scoring/extractor.py
+++ b/backend/icutwin/scoring/extractor.py
@@ -183,7 +183,7 @@ class Extractor:
                 order.select(
                     ["hospitalization_id"] if n == 1 else ["row", "hospitalization_id"]
                 )
-                .with_columns(features=pl.Series(list(feats)))
+                .with_columns(features=feature_series(feats))
                 .join(stored_cuts(src), on="hospitalization_id", how="left")
             )
             if stay_ids is not None:
@@ -196,6 +196,12 @@ class Extractor:
             )
 
 
+def feature_series(feats) -> pl.Series:
+    """one feature row per stay; built from the 2-D array so an empty shard (fewer
+    stays than shards) gets the same dtype as a populated one, not Null"""
+    return pl.Series(feats)
+
+
 def merge_shards(root: pathlib.Path, model_name: str, n: int):
     """the N `--shard` parts -> features-{split}-<model>.parquet, rows in the
     order of {split}_for_inference.parquet (rep-based scoring relies on it)"""
diff --git a/backend/tests/test_extractor.py b/backend/tests/test_extractor.py
index a396500..bd88b1c 100644
--- a/backend/tests/test_extractor.py
+++ b/backend/tests/test_extractor.py
@@ -23,3 +23,12 @@ def test_merge_shards_restores_row_order(tmp_path):
         assert df.columns == ["hospitalization_id", "features"]
         assert df["hospitalization_id"].to_list() == [f"h{r}" for r in range(7)]
     assert not list(tmp_path.glob("*of2.parquet"))  # parts removed
+
+
+def test_empty_shard_has_the_same_feature_dtype():
+    import numpy as np
+
+    from icutwin.scoring.extractor import feature_series
+
+    full = feature_series(np.ones((2, 4), np.float16))
+    assert feature_series(np.empty((0, 4), np.float16)).dtype == full.dtype
```

### pr19-05: train_fuzzball_continue.yaml:6

Why it matters: A 2-epoch override changes the packed dataset, so a resume skips the wrong rows. The patch is a comment only; the real fix is a stable dataset or sampler in decoder.py. Not demo relevant.

Patch `pr19-05-train-continue-caveat.patch`:

```diff
diff --git a/backend/examples/train_fuzzball_continue.yaml b/backend/examples/train_fuzzball_continue.yaml
index 03c9e91..a0b3af3 100644
--- a/backend/examples/train_fuzzball_continue.yaml
+++ b/backend/examples/train_fuzzball_continue.yaml
@@ -1,6 +1,10 @@
 # icutwin-train overrides to continue a 1-epoch checkpoint for one more epoch (2 GB10 nodes, DDP).
-# HF resume restores weights, optimizer, scheduler and RNG, skips the steps already done,
-# and trains epoch 2; the linear LR picks up at the middle of a 2-epoch schedule.
+# HF resume restores weights, optimizer, scheduler and RNG and skips the steps already done.
+# CAVEAT: icutwin.model.decoder.train packs one pass per epoch into ONE Dataset, so asking for 2
+# epochs here builds a different (twice as long) dataset than the 1-epoch run saw. Trainer shuffles
+# it and skips the old step count into that new order, so it can replay epoch-1 rows and skip
+# epoch-2 rows instead of completing one more pass. Treat the result as "more training", not as an
+# exact second epoch, until the dataset/sampler is kept stable across resume (upstream change).
 port: !!int 0 # no live page on the cluster
 training_args:
   num_train_epochs: !!int 2 # epoch 1 is the checkpoint
```

## Dema (board page)

Paste into the ICU-Twin thread for Dema. Our copy of the page already has the fixes marked 'in our copy'; the question is whether ICU-Twin main should take them.

CodeRabbit findings on the board page. Patches are against the PR 19 page (01, m1, m2, m3 apply in that order after 02) and the older PR 16 page (06 to 08).

### pr19-01: index.html:1186

Why it matters: A skipped CRRT event shows 'Predicted new* 0' where it should say no data. In our copy: done (f9640f7).

Patch `pr19-01-skipped-event-unavailable.patch`:

```diff
diff --git a/backend/app/static/index.html b/backend/app/static/index.html
index f755510..95673d6 100644
--- a/backend/app/static/index.html
+++ b/backend/app/static/index.html
@@ -1182,13 +1182,13 @@ details.more summary:hover{color:var(--blue)}
       const frees = k==="leave" ? ["imv","crrt"].map(x=>[x,may.filter(r=>r.on_now[x]).length]).filter(x=>x[1]) : [];
       return `<article class="wc${lv?` lv-${lv}`:""}" data-k="${k}" style="order:${first===k?0:1};--w:${Math.max(4,Math.min(10,n))}" aria-labelledby="wc-${k}">
         <h3 id="wc-${k}">${NAME[k]}${st?`<span class="band lv-${lv}"${T(DEF.band[st])}>${st}</span>`:""}</h3>
-        <div class="stats">${sup?`<span${T(`Patients on ${START[k]} at 07:00`)}><i>On now</i><b>${ls.now_by[k]}</b><small>beds</small></span>`:""}${mach ? (free!=null?`<span class="free"${T(`${k==="imv"?"Ventilators":"CRRT machines"} free: ${free}${machines[k]!=null?` of ${machines[k]} on the unit`:""}`)}><i>Free</i><b>${free}</b><small>${machines[k]!=null?`of ${machines[k]}`:"&nbsp;"}</small></span>`:`<span${T(`No total is set for ${k==="imv"?"ventilators":"CRRT machines"}: set it in Settings, under Capacity`)}><i>Free</i><b>–</b><small><button type="button" class="chg capset-go" aria-label="Set the total ${k==="imv"?"ventilators":"CRRT machines"} in settings">not set</button></small></span>`) : ""}<span class="exp"${T("Beds at or above this event's threshold: a flag per bed, not a certainty")}><i>Predicted new*</i><b>${n}</b></span></div>
-        ${q?`<p class="fc"${T(DEF.bar(`Unit forecast: ${EVW[k]}`,q))}>Unit forecast <b>${q.p50}</b> ${rgT(q)}</p>`:""}
+        <div class="stats">${sup?`<span${T(`Patients on ${START[k]} at 07:00`)}><i>On now</i><b>${ls.now_by[k]}</b><small>beds</small></span>`:""}${mach ? (free!=null?`<span class="free"${T(`${k==="imv"?"Ventilators":"CRRT machines"} free: ${free}${machines[k]!=null?` of ${machines[k]} on the unit`:""}`)}><i>Free</i><b>${free}</b><small>${machines[k]!=null?`of ${machines[k]}`:"&nbsp;"}</small></span>`:`<span${T(`No total is set for ${k==="imv"?"ventilators":"CRRT machines"}: set it in Settings, under Capacity`)}><i>Free</i><b>–</b><small><button type="button" class="chg capset-go" aria-label="Set the total ${k==="imv"?"ventilators":"CRRT machines"} in settings">not set</button></small></span>`) : ""}<span class="exp"${T("Beds at or above this event's threshold: a flag per bed, not a certainty")}><i>Predicted new*</i><b>${q?n:"–"}</b></span></div>
+        ${q?`<p class="fc"${T(DEF.bar(`Unit forecast: ${EVW[k]}`,q))}>Unit forecast <b>${q.p50}</b> ${rgT(q)}</p>`:`<p class="fc">Unit forecast <b>unavailable</b></p>`}
         ${freeable?`<p class="frees"${T(`Beds on ${START[k]} now with ${P(lines.leave)} or more to leave the ICU`)}><i>${ic(k,true)}</i><b>${freeable}</b> may free up if likely leavers go</p>`:""}
         ${frees.length?`<p class="frees">If these beds leave, they free ${frees.map(([x,m])=>`<i>${ic(x,true)}</i><b>${m}</b> ${x==="imv"?(m===1?"ventilator":"ventilators"):"CRRT"}`).join(" ")}</p>`:""}
         ${mach ? usageBar(onN, free, n, `${onN} in use now, ${onN+n} with the ${n} flagged${free!=null?`, ${onN+free} in total`:"; no total set"}`) : ""}
         <span class="gl">Beds to watch</span>
-        <p class="bedline"${T(DEF.flag)}>Beds at <b>${P(lines[k])}</b> or more · <b>${nb(n)}</b> <button type="button" class="chg" aria-label="Change the threshold for ${NAME[k]} in settings">Change</button></p>
+        <p class="bedline"${T(DEF.flag)}>Beds at <b>${P(lines[k])}</b> or more · <b>${q?nb(n):"not available"}</b> <button type="button" class="chg" aria-label="Change the threshold for ${NAME[k]} in settings">Change</button></p>
         ${n?`<div class="set">${may.map(r=>fig(r, k!=="leave" && w3.includes(r.room) && topRisk(r)[0]===k ? "w" : "", null, esc(pct(riskOf(r,k))), `${pct(riskOf(r,k))} chance of ${EVW[k]}`, k==="leave" ? SUP.filter(x=>r.on_now[x]).map(x=>`<i>${ic(x,true)}</i>`).join("") : "")).join("")}</div>`:""}</article>`; };
     const cards=["death",...SUP,"leave"].map(card).join(""), rest=rs.filter(r=>!flagged.has(r.room));
     el.innerHTML = cards + (rest.length ? `<article class="wc rest" aria-labelledby="wc-rest"><h3 id="wc-rest">Other beds</h3><p class="bedline"><b>under every threshold · ${nb(rest.length)}</b></p>
diff --git a/mockups/command-center.html b/mockups/command-center.html
index f755510..95673d6 100644
--- a/mockups/command-center.html
+++ b/mockups/command-center.html
@@ -1182,13 +1182,13 @@ details.more summary:hover{color:var(--blue)}
       const frees = k==="leave" ? ["imv","crrt"].map(x=>[x,may.filter(r=>r.on_now[x]).length]).filter(x=>x[1]) : [];
       return `<article class="wc${lv?` lv-${lv}`:""}" data-k="${k}" style="order:${first===k?0:1};--w:${Math.max(4,Math.min(10,n))}" aria-labelledby="wc-${k}">
         <h3 id="wc-${k}">${NAME[k]}${st?`<span class="band lv-${lv}"${T(DEF.band[st])}>${st}</span>`:""}</h3>
-        <div class="stats">${sup?`<span${T(`Patients on ${START[k]} at 07:00`)}><i>On now</i><b>${ls.now_by[k]}</b><small>beds</small></span>`:""}${mach ? (free!=null?`<span class="free"${T(`${k==="imv"?"Ventilators":"CRRT machines"} free: ${free}${machines[k]!=null?` of ${machines[k]} on the unit`:""}`)}><i>Free</i><b>${free}</b><small>${machines[k]!=null?`of ${machines[k]}`:"&nbsp;"}</small></span>`:`<span${T(`No total is set for ${k==="imv"?"ventilators":"CRRT machines"}: set it in Settings, under Capacity`)}><i>Free</i><b>–</b><small><button type="button" class="chg capset-go" aria-label="Set the total ${k==="imv"?"ventilators":"CRRT machines"} in settings">not set</button></small></span>`) : ""}<span class="exp"${T("Beds at or above this event's threshold: a flag per bed, not a certainty")}><i>Predicted new*</i><b>${n}</b></span></div>
-        ${q?`<p class="fc"${T(DEF.bar(`Unit forecast: ${EVW[k]}`,q))}>Unit forecast <b>${q.p50}</b> ${rgT(q)}</p>`:""}
+        <div class="stats">${sup?`<span${T(`Patients on ${START[k]} at 07:00`)}><i>On now</i><b>${ls.now_by[k]}</b><small>beds</small></span>`:""}${mach ? (free!=null?`<span class="free"${T(`${k==="imv"?"Ventilators":"CRRT machines"} free: ${free}${machines[k]!=null?` of ${machines[k]} on the unit`:""}`)}><i>Free</i><b>${free}</b><small>${machines[k]!=null?`of ${machines[k]}`:"&nbsp;"}</small></span>`:`<span${T(`No total is set for ${k==="imv"?"ventilators":"CRRT machines"}: set it in Settings, under Capacity`)}><i>Free</i><b>–</b><small><button type="button" class="chg capset-go" aria-label="Set the total ${k==="imv"?"ventilators":"CRRT machines"} in settings">not set</button></small></span>`) : ""}<span class="exp"${T("Beds at or above this event's threshold: a flag per bed, not a certainty")}><i>Predicted new*</i><b>${q?n:"–"}</b></span></div>
+        ${q?`<p class="fc"${T(DEF.bar(`Unit forecast: ${EVW[k]}`,q))}>Unit forecast <b>${q.p50}</b> ${rgT(q)}</p>`:`<p class="fc">Unit forecast <b>unavailable</b></p>`}
         ${freeable?`<p class="frees"${T(`Beds on ${START[k]} now with ${P(lines.leave)} or more to leave the ICU`)}><i>${ic(k,true)}</i><b>${freeable}</b> may free up if likely leavers go</p>`:""}
         ${frees.length?`<p class="frees">If these beds leave, they free ${frees.map(([x,m])=>`<i>${ic(x,true)}</i><b>${m}</b> ${x==="imv"?(m===1?"ventilator":"ventilators"):"CRRT"}`).join(" ")}</p>`:""}
         ${mach ? usageBar(onN, free, n, `${onN} in use now, ${onN+n} with the ${n} flagged${free!=null?`, ${onN+free} in total`:"; no total set"}`) : ""}
         <span class="gl">Beds to watch</span>
-        <p class="bedline"${T(DEF.flag)}>Beds at <b>${P(lines[k])}</b> or more · <b>${nb(n)}</b> <button type="button" class="chg" aria-label="Change the threshold for ${NAME[k]} in settings">Change</button></p>
+        <p class="bedline"${T(DEF.flag)}>Beds at <b>${P(lines[k])}</b> or more · <b>${q?nb(n):"not available"}</b> <button type="button" class="chg" aria-label="Change the threshold for ${NAME[k]} in settings">Change</button></p>
         ${n?`<div class="set">${may.map(r=>fig(r, k!=="leave" && w3.includes(r.room) && topRisk(r)[0]===k ? "w" : "", null, esc(pct(riskOf(r,k))), `${pct(riskOf(r,k))} chance of ${EVW[k]}`, k==="leave" ? SUP.filter(x=>r.on_now[x]).map(x=>`<i>${ic(x,true)}</i>`).join("") : "")).join("")}</div>`:""}</article>`; };
     const cards=["death",...SUP,"leave"].map(card).join(""), rest=rs.filter(r=>!flagged.has(r.room));
     el.innerHTML = cards + (rest.length ? `<article class="wc rest" aria-labelledby="wc-rest"><h3 id="wc-rest">Other beds</h3><p class="bedline"><b>under every threshold · ${nb(rest.length)}</b></p>
```

### pr19-02: index.html:1193

Why it matters: The Deaths card listed beds and ranked by death risk, which conflicts with PRODUCT.md:66 and DESIGN.md:501 (death never colours or marks a bed). J.C. decided to keep the card and show only the unit death count and range. In our copy: done.

Patch `pr19-02-no-per-bed-death.patch`:

```diff
diff --git a/backend/app/static/index.html b/backend/app/static/index.html
index 95673d6..e2f1d3c 100644
--- a/backend/app/static/index.html
+++ b/backend/app/static/index.html
@@ -1153,7 +1153,7 @@ details.more summary:hover{color:var(--blue)}
       ${pred?`<line x1="${x(sum)}" x2="${x(sum)}" y1="16" y2="34" stroke="var(--ink)" stroke-width="3" stroke-dasharray="3 2"/>${x(sum)-x(on)>24?`<text x="${Math.min(x(sum),286)}" y="11" text-anchor="${x(sum)>280?"end":"middle"}" font-size="14" font-weight="700">${sum}*</text>`:""}`:""}
       ${tot!=null?`<text x="294" y="45" text-anchor="end" font-size="13">${tot} total</text>`:""}</svg>`; }
   /* a bed's top risk: its highest chance among death and the supports it is not on yet; the three highest in the unit pulse (Dema's rule), with ties */
-  const RISKK = ["death","imv","vasopressor","crrt"];
+  const RISKK = ["imv","vasopressor","crrt"];      // death never marks or ranks a bed (PRODUCT.md, DESIGN.md)
   const riskOf = (r,k) => k==="death" ? r.p.death : k==="leave" ? r.p.icu_departure : r.on_now[k] ? null : r.p[k];
   const topRisk = r => { let best=null; for(const k of RISKK){ const v=riskOf(r,k); if(v!=null && (!best || v>best[1])) best=[k,v]; } return best; };
   const topBeds = () => { const l=RM.rooms.map(r=>[r.room,topRisk(r)]).filter(x=>x[1]).sort((a,b)=>b[1][1]-a[1][1]); if(l.length<=3) return l.map(x=>x[0]);
@@ -1175,7 +1175,7 @@ details.more summary:hover{color:var(--blue)}
     const NAME={death:"Deaths", imv:"Ventilator", vasopressor:"Vasopressor", crrt:"CRRT", leave:"Leave the ICU to ward or step-down"}, EVW={death:"death in hospital", imv:"starting a ventilator", vasopressor:"starting a vasopressor", crrt:"starting CRRT", leave:"leaving the ICU"}, SHORTEV={death:"Death", imv:"Vent", vasopressor:"Press", crrt:"CRRT"};
     const w3=topBeds(), nb=n=>n?`${n} ${n===1?"bed":"beds"}`:"no beds", flagged=new Set();
     const card = k => { const sup=SUP.includes(k), c = k==="death" ? FC.resources.death : k==="leave" ? FC.resources.icu_departure : ls.expected_by[k], q = c && c.p50!=null ? c : null;
-      const may=rs.filter(r=>{ const v=riskOf(r,k); return v!=null && v>=lines[k]; }).sort((a,b)=>riskOf(b,k)-riskOf(a,k)), n=may.length; if(k!=="leave") for(const r of may) flagged.add(r.room);
+      const may=k==="death" ? [] : rs.filter(r=>{ const v=riskOf(r,k); return v!=null && v>=lines[k]; }).sort((a,b)=>riskOf(b,k)-riskOf(a,k)), n=k==="death" ? (q?q.p50:0) : may.length; if(k!=="leave") for(const r of may) flagged.add(r.room);
       const mach = k==="imv"||k==="crrt", free = sup ? machFree(k) : null, onN = sup ? rs.filter(r=>r.on_now[k]).length : 0;
       const st = free==null ? null : n>free ? "SHORT" : n===free && n>0 ? "AT LIMIT" : null, lv = st==="SHORT" ? "red" : st ? "amber" : "";      // Dema's rule: flagged beds against what is free
       const freeable = k==="imv"||k==="crrt" ? rs.filter(r=>r.on_now[k] && r.p.icu_departure!=null && r.p.icu_departure>=lines.leave).length : 0;
@@ -1187,9 +1187,9 @@ details.more summary:hover{color:var(--blue)}
         ${freeable?`<p class="frees"${T(`Beds on ${START[k]} now with ${P(lines.leave)} or more to leave the ICU`)}><i>${ic(k,true)}</i><b>${freeable}</b> may free up if likely leavers go</p>`:""}
         ${frees.length?`<p class="frees">If these beds leave, they free ${frees.map(([x,m])=>`<i>${ic(x,true)}</i><b>${m}</b> ${x==="imv"?(m===1?"ventilator":"ventilators"):"CRRT"}`).join(" ")}</p>`:""}
         ${mach ? usageBar(onN, free, n, `${onN} in use now, ${onN+n} with the ${n} flagged${free!=null?`, ${onN+free} in total`:"; no total set"}`) : ""}
-        <span class="gl">Beds to watch</span>
-        <p class="bedline"${T(DEF.flag)}>Beds at <b>${P(lines[k])}</b> or more · <b>${q?nb(n):"not available"}</b> <button type="button" class="chg" aria-label="Change the threshold for ${NAME[k]} in settings">Change</button></p>
-        ${n?`<div class="set">${may.map(r=>fig(r, k!=="leave" && w3.includes(r.room) && topRisk(r)[0]===k ? "w" : "", null, esc(pct(riskOf(r,k))), `${pct(riskOf(r,k))} chance of ${EVW[k]}`, k==="leave" ? SUP.filter(x=>r.on_now[x]).map(x=>`<i>${ic(x,true)}</i>`).join("") : "")).join("")}</div>`:""}</article>`; };
+        ${k==="death"?"":`<span class="gl">Beds to watch</span>
+        <p class="bedline"${T(DEF.flag)}>Beds at <b>${P(lines[k])}</b> or more · <b>${q?nb(n):"not available"}</b> <button type="button" class="chg" aria-label="Change the threshold for ${NAME[k]} in settings">Change</button></p>`}
+        ${may.length?`<div class="set">${may.map(r=>fig(r, k!=="leave" && w3.includes(r.room) && topRisk(r)[0]===k ? "w" : "", null, esc(pct(riskOf(r,k))), `${pct(riskOf(r,k))} chance of ${EVW[k]}`, k==="leave" ? SUP.filter(x=>r.on_now[x]).map(x=>`<i>${ic(x,true)}</i>`).join("") : "")).join("")}</div>`:""}</article>`; };
     const cards=["death",...SUP,"leave"].map(card).join(""), rest=rs.filter(r=>!flagged.has(r.room));
     el.innerHTML = cards + (rest.length ? `<article class="wc rest" aria-labelledby="wc-rest"><h3 id="wc-rest">Other beds</h3><p class="bedline"><b>under every threshold · ${nb(rest.length)}</b></p>
         <div class="set">${rest.map(r=>{ const t=topRisk(r); return fig(r, "", null, t?`${SHORTEV[t[0]]}<br>${esc(pct(t[1]))}`:"–", t?`highest chance: ${EVW[t[0]]}, ${pct(t[1])}`:"no estimate"); }).join("")}</div></article>` : "");
diff --git a/mockups/command-center.html b/mockups/command-center.html
index 95673d6..e2f1d3c 100644
--- a/mockups/command-center.html
+++ b/mockups/command-center.html
@@ -1153,7 +1153,7 @@ details.more summary:hover{color:var(--blue)}
       ${pred?`<line x1="${x(sum)}" x2="${x(sum)}" y1="16" y2="34" stroke="var(--ink)" stroke-width="3" stroke-dasharray="3 2"/>${x(sum)-x(on)>24?`<text x="${Math.min(x(sum),286)}" y="11" text-anchor="${x(sum)>280?"end":"middle"}" font-size="14" font-weight="700">${sum}*</text>`:""}`:""}
       ${tot!=null?`<text x="294" y="45" text-anchor="end" font-size="13">${tot} total</text>`:""}</svg>`; }
   /* a bed's top risk: its highest chance among death and the supports it is not on yet; the three highest in the unit pulse (Dema's rule), with ties */
-  const RISKK = ["death","imv","vasopressor","crrt"];
+  const RISKK = ["imv","vasopressor","crrt"];      // death never marks or ranks a bed (PRODUCT.md, DESIGN.md)
   const riskOf = (r,k) => k==="death" ? r.p.death : k==="leave" ? r.p.icu_departure : r.on_now[k] ? null : r.p[k];
   const topRisk = r => { let best=null; for(const k of RISKK){ const v=riskOf(r,k); if(v!=null && (!best || v>best[1])) best=[k,v]; } return best; };
   const topBeds = () => { const l=RM.rooms.map(r=>[r.room,topRisk(r)]).filter(x=>x[1]).sort((a,b)=>b[1][1]-a[1][1]); if(l.length<=3) return l.map(x=>x[0]);
@@ -1175,7 +1175,7 @@ details.more summary:hover{color:var(--blue)}
     const NAME={death:"Deaths", imv:"Ventilator", vasopressor:"Vasopressor", crrt:"CRRT", leave:"Leave the ICU to ward or step-down"}, EVW={death:"death in hospital", imv:"starting a ventilator", vasopressor:"starting a vasopressor", crrt:"starting CRRT", leave:"leaving the ICU"}, SHORTEV={death:"Death", imv:"Vent", vasopressor:"Press", crrt:"CRRT"};
     const w3=topBeds(), nb=n=>n?`${n} ${n===1?"bed":"beds"}`:"no beds", flagged=new Set();
     const card = k => { const sup=SUP.includes(k), c = k==="death" ? FC.resources.death : k==="leave" ? FC.resources.icu_departure : ls.expected_by[k], q = c && c.p50!=null ? c : null;
-      const may=rs.filter(r=>{ const v=riskOf(r,k); return v!=null && v>=lines[k]; }).sort((a,b)=>riskOf(b,k)-riskOf(a,k)), n=may.length; if(k!=="leave") for(const r of may) flagged.add(r.room);
+      const may=k==="death" ? [] : rs.filter(r=>{ const v=riskOf(r,k); return v!=null && v>=lines[k]; }).sort((a,b)=>riskOf(b,k)-riskOf(a,k)), n=k==="death" ? (q?q.p50:0) : may.length; if(k!=="leave") for(const r of may) flagged.add(r.room);
       const mach = k==="imv"||k==="crrt", free = sup ? machFree(k) : null, onN = sup ? rs.filter(r=>r.on_now[k]).length : 0;
       const st = free==null ? null : n>free ? "SHORT" : n===free && n>0 ? "AT LIMIT" : null, lv = st==="SHORT" ? "red" : st ? "amber" : "";      // Dema's rule: flagged beds against what is free
       const freeable = k==="imv"||k==="crrt" ? rs.filter(r=>r.on_now[k] && r.p.icu_departure!=null && r.p.icu_departure>=lines.leave).length : 0;
@@ -1187,9 +1187,9 @@ details.more summary:hover{color:var(--blue)}
         ${freeable?`<p class="frees"${T(`Beds on ${START[k]} now with ${P(lines.leave)} or more to leave the ICU`)}><i>${ic(k,true)}</i><b>${freeable}</b> may free up if likely leavers go</p>`:""}
         ${frees.length?`<p class="frees">If these beds leave, they free ${frees.map(([x,m])=>`<i>${ic(x,true)}</i><b>${m}</b> ${x==="imv"?(m===1?"ventilator":"ventilators"):"CRRT"}`).join(" ")}</p>`:""}
         ${mach ? usageBar(onN, free, n, `${onN} in use now, ${onN+n} with the ${n} flagged${free!=null?`, ${onN+free} in total`:"; no total set"}`) : ""}
-        <span class="gl">Beds to watch</span>
-        <p class="bedline"${T(DEF.flag)}>Beds at <b>${P(lines[k])}</b> or more · <b>${q?nb(n):"not available"}</b> <button type="button" class="chg" aria-label="Change the threshold for ${NAME[k]} in settings">Change</button></p>
-        ${n?`<div class="set">${may.map(r=>fig(r, k!=="leave" && w3.includes(r.room) && topRisk(r)[0]===k ? "w" : "", null, esc(pct(riskOf(r,k))), `${pct(riskOf(r,k))} chance of ${EVW[k]}`, k==="leave" ? SUP.filter(x=>r.on_now[x]).map(x=>`<i>${ic(x,true)}</i>`).join("") : "")).join("")}</div>`:""}</article>`; };
+        ${k==="death"?"":`<span class="gl">Beds to watch</span>
+        <p class="bedline"${T(DEF.flag)}>Beds at <b>${P(lines[k])}</b> or more · <b>${q?nb(n):"not available"}</b> <button type="button" class="chg" aria-label="Change the threshold for ${NAME[k]} in settings">Change</button></p>`}
+        ${may.length?`<div class="set">${may.map(r=>fig(r, k!=="leave" && w3.includes(r.room) && topRisk(r)[0]===k ? "w" : "", null, esc(pct(riskOf(r,k))), `${pct(riskOf(r,k))} chance of ${EVW[k]}`, k==="leave" ? SUP.filter(x=>r.on_now[x]).map(x=>`<i>${ic(x,true)}</i>`).join("") : "")).join("")}</div>`:""}</article>`; };
     const cards=["death",...SUP,"leave"].map(card).join(""), rest=rs.filter(r=>!flagged.has(r.room));
     el.innerHTML = cards + (rest.length ? `<article class="wc rest" aria-labelledby="wc-rest"><h3 id="wc-rest">Other beds</h3><p class="bedline"><b>under every threshold · ${nb(rest.length)}</b></p>
         <div class="set">${rest.map(r=>{ const t=topRisk(r); return fig(r, "", null, t?`${SHORTEV[t[0]]}<br>${esc(pct(t[1]))}`:"–", t?`highest chance: ${EVW[t[0]]}, ${pct(t[1])}`:"no estimate"); }).join("")}</div></article>` : "");
```

### pr19-m1: index.html:1178

Why it matters: Leaving beds were also listed under Other beds. In our copy: already fixed.

Patch `pr19-m1-other-beds-include-leaving.patch`:

```diff
diff --git a/backend/app/static/index.html b/backend/app/static/index.html
index e2f1d3c..af47b8c 100644
--- a/backend/app/static/index.html
+++ b/backend/app/static/index.html
@@ -1175,7 +1175,7 @@ details.more summary:hover{color:var(--blue)}
     const NAME={death:"Deaths", imv:"Ventilator", vasopressor:"Vasopressor", crrt:"CRRT", leave:"Leave the ICU to ward or step-down"}, EVW={death:"death in hospital", imv:"starting a ventilator", vasopressor:"starting a vasopressor", crrt:"starting CRRT", leave:"leaving the ICU"}, SHORTEV={death:"Death", imv:"Vent", vasopressor:"Press", crrt:"CRRT"};
     const w3=topBeds(), nb=n=>n?`${n} ${n===1?"bed":"beds"}`:"no beds", flagged=new Set();
     const card = k => { const sup=SUP.includes(k), c = k==="death" ? FC.resources.death : k==="leave" ? FC.resources.icu_departure : ls.expected_by[k], q = c && c.p50!=null ? c : null;
-      const may=k==="death" ? [] : rs.filter(r=>{ const v=riskOf(r,k); return v!=null && v>=lines[k]; }).sort((a,b)=>riskOf(b,k)-riskOf(a,k)), n=k==="death" ? (q?q.p50:0) : may.length; if(k!=="leave") for(const r of may) flagged.add(r.room);
+      const may=k==="death" ? [] : rs.filter(r=>{ const v=riskOf(r,k); return v!=null && v>=lines[k]; }).sort((a,b)=>riskOf(b,k)-riskOf(a,k)), n=k==="death" ? (q?q.p50:0) : may.length; for(const r of may) flagged.add(r.room);
       const mach = k==="imv"||k==="crrt", free = sup ? machFree(k) : null, onN = sup ? rs.filter(r=>r.on_now[k]).length : 0;
       const st = free==null ? null : n>free ? "SHORT" : n===free && n>0 ? "AT LIMIT" : null, lv = st==="SHORT" ? "red" : st ? "amber" : "";      // Dema's rule: flagged beds against what is free
       const freeable = k==="imv"||k==="crrt" ? rs.filter(r=>r.on_now[k] && r.p.icu_departure!=null && r.p.icu_departure>=lines.leave).length : 0;
diff --git a/mockups/command-center.html b/mockups/command-center.html
index e2f1d3c..af47b8c 100644
--- a/mockups/command-center.html
+++ b/mockups/command-center.html
@@ -1175,7 +1175,7 @@ details.more summary:hover{color:var(--blue)}
     const NAME={death:"Deaths", imv:"Ventilator", vasopressor:"Vasopressor", crrt:"CRRT", leave:"Leave the ICU to ward or step-down"}, EVW={death:"death in hospital", imv:"starting a ventilator", vasopressor:"starting a vasopressor", crrt:"starting CRRT", leave:"leaving the ICU"}, SHORTEV={death:"Death", imv:"Vent", vasopressor:"Press", crrt:"CRRT"};
     const w3=topBeds(), nb=n=>n?`${n} ${n===1?"bed":"beds"}`:"no beds", flagged=new Set();
     const card = k => { const sup=SUP.includes(k), c = k==="death" ? FC.resources.death : k==="leave" ? FC.resources.icu_departure : ls.expected_by[k], q = c && c.p50!=null ? c : null;
-      const may=k==="death" ? [] : rs.filter(r=>{ const v=riskOf(r,k); return v!=null && v>=lines[k]; }).sort((a,b)=>riskOf(b,k)-riskOf(a,k)), n=k==="death" ? (q?q.p50:0) : may.length; if(k!=="leave") for(const r of may) flagged.add(r.room);
+      const may=k==="death" ? [] : rs.filter(r=>{ const v=riskOf(r,k); return v!=null && v>=lines[k]; }).sort((a,b)=>riskOf(b,k)-riskOf(a,k)), n=k==="death" ? (q?q.p50:0) : may.length; for(const r of may) flagged.add(r.room);
       const mach = k==="imv"||k==="crrt", free = sup ? machFree(k) : null, onN = sup ? rs.filter(r=>r.on_now[k]).length : 0;
       const st = free==null ? null : n>free ? "SHORT" : n===free && n>0 ? "AT LIMIT" : null, lv = st==="SHORT" ? "red" : st ? "amber" : "";      // Dema's rule: flagged beds against what is free
       const freeable = k==="imv"||k==="crrt" ? rs.filter(r=>r.on_now[k] && r.p.icu_departure!=null && r.p.icu_departure>=lines.leave).length : 0;
```

### pr19-m2: index.html:1220

Why it matters: The tile shows status by colour only; add a visible word (check 390 px layout, .st class). In our copy the Next 24 h tile shows the icon and percentage but no status word; the patch does not apply because the status vocabulary changed (D22/D25).

Patch `pr19-m2-visible-trajectory-word.patch`:

```diff
diff --git a/backend/app/static/index.html b/backend/app/static/index.html
index af47b8c..1fec874 100644
--- a/backend/app/static/index.html
+++ b/backend/app/static/index.html
@@ -1217,7 +1217,7 @@ details.more summary:hover{color:var(--blue)}
       if(topNew(r)) next += it(DEF.any,svg("any"),anyNew(r));
       if(showLeave(r)) next += it(DEF.out(r.p.icu_departure),ic("leave",false),r.p.icu_departure);
       else if(t==="hold") next += `<small class="mu"${T(DEF.stay)}>leaving &lt;${P(lines.base)}</small>`;
-      b.innerHTML=`<span class="bt"><span class="rm">${r.room}</span>${whoH(r)}</span>
+      b.innerHTML=`<span class="bt"><span class="rm">${r.room}</span>${whoH(r)}<span class="st" aria-hidden="true">${esc(word)}</span></span>
         <span class="nowl" aria-hidden="true">${on.length?on.map(k=>`<span class="nx"${T(DEF.on(k))}>${ic(k,true)}</span>`).join(""):`<small class="mu"${T(DEF.none)}>No life support</small>`}</span>
         <span class="nextl" aria-hidden="true"><span class="cap">Next 24 h</span>${next||`<small class="mu"${T(DEF.same)}>nothing new</small>`}</span>`; }
     if(nowMode()){ const on=onList(r), n=on.length;      // Now: only what is running at 07:00; weight is the number of supports
diff --git a/mockups/command-center.html b/mockups/command-center.html
index af47b8c..1fec874 100644
--- a/mockups/command-center.html
+++ b/mockups/command-center.html
@@ -1217,7 +1217,7 @@ details.more summary:hover{color:var(--blue)}
       if(topNew(r)) next += it(DEF.any,svg("any"),anyNew(r));
       if(showLeave(r)) next += it(DEF.out(r.p.icu_departure),ic("leave",false),r.p.icu_departure);
       else if(t==="hold") next += `<small class="mu"${T(DEF.stay)}>leaving &lt;${P(lines.base)}</small>`;
-      b.innerHTML=`<span class="bt"><span class="rm">${r.room}</span>${whoH(r)}</span>
+      b.innerHTML=`<span class="bt"><span class="rm">${r.room}</span>${whoH(r)}<span class="st" aria-hidden="true">${esc(word)}</span></span>
         <span class="nowl" aria-hidden="true">${on.length?on.map(k=>`<span class="nx"${T(DEF.on(k))}>${ic(k,true)}</span>`).join(""):`<small class="mu"${T(DEF.none)}>No life support</small>`}</span>
         <span class="nextl" aria-hidden="true"><span class="cap">Next 24 h</span>${next||`<small class="mu"${T(DEF.same)}>nothing new</small>`}</span>`; }
     if(nowMode()){ const on=onList(r), n=on.length;      // Now: only what is running at 07:00; weight is the number of supports
```

### pr19-m3: index.html:1300

Why it matters: One Escape closes Settings and the bed together. In our copy: done (preventDefault plus defaultPrevented check).

Patch `pr19-m3-escape-closes-one-panel.patch`:

```diff
diff --git a/backend/app/static/index.html b/backend/app/static/index.html
index 1fec874..1ac55b3 100644
--- a/backend/app/static/index.html
+++ b/backend/app/static/index.html
@@ -1087,7 +1087,7 @@ details.more summary:hover{color:var(--blue)}
     if(!on) return; paintFlag(); $("set-h").focus({preventScroll:true}); if(at) $(at).scrollIntoView({block:"start"}); else menu.scrollTop=0; }
   gear.onclick=()=>setMenu(menu.hidden);
   $("setclose").onclick=()=>{ setMenu(false); gear.focus(); };
-  document.addEventListener("keydown", e=>{ if(e.key==="Escape" && !menu.hidden){ setMenu(false); gear.focus(); } });
+  document.addEventListener("keydown", e=>{ if(e.key==="Escape" && !menu.hidden){ e.preventDefault(); setMenu(false); gear.focus(); } });
   document.addEventListener("pointerdown", e=>{ if(!menu.hidden && !menu.contains(e.target) && !gear.contains(e.target)) setMenu(false); });
   function paintLegend(){
     if(nowMode()) $("legend").innerHTML = SUP.map(k=>`<span${T(DEF.on(k))}>${ic(k,true)}${SHORTN[k]}</span>`).join("")+`<i class="sep"></i><span>Life support running at 07:00</span>`;
@@ -1297,7 +1297,7 @@ details.more summary:hover{color:var(--blue)}
   const VIT=[["heart_rate","Heart rate","bpm"],["map","Mean arterial pressure","mmHg",65],["spo2","SpO2","%"],["respiratory_rate","Respiratory rate","/min"]];
   const closeRoom = () => { location.hash=$("back").getAttribute("href"); };
   roomview.addEventListener("pointerdown", e=>{ if(e.target===roomview) closeRoom(); });
-  document.addEventListener("keydown", e=>{ if(e.key==="Escape" && room!==null && $("setmenu").hidden) closeRoom(); });
+  document.addEventListener("keydown", e=>{ if(e.key==="Escape" && room!==null && $("setmenu").hidden && !e.defaultPrevented) closeRoom(); });
   function paintScope(){ const el=$("chat-scope"); el.textContent = chatScope!==null ? `Bed ${chatScope}` : "Unit"; el.disabled = room===null;      // what the chat is about; on a room page it switches between that room and the unit
     el.setAttribute("aria-label", chatScope!==null ? `Asking about bed ${chatScope}. Switch to the unit` : room!==null ? `Asking about the unit. Switch to bed ${room}` : "Asking about the unit"); }
   function showRoom(n){
diff --git a/mockups/command-center.html b/mockups/command-center.html
index 1fec874..1ac55b3 100644
--- a/mockups/command-center.html
+++ b/mockups/command-center.html
@@ -1087,7 +1087,7 @@ details.more summary:hover{color:var(--blue)}
     if(!on) return; paintFlag(); $("set-h").focus({preventScroll:true}); if(at) $(at).scrollIntoView({block:"start"}); else menu.scrollTop=0; }
   gear.onclick=()=>setMenu(menu.hidden);
   $("setclose").onclick=()=>{ setMenu(false); gear.focus(); };
-  document.addEventListener("keydown", e=>{ if(e.key==="Escape" && !menu.hidden){ setMenu(false); gear.focus(); } });
+  document.addEventListener("keydown", e=>{ if(e.key==="Escape" && !menu.hidden){ e.preventDefault(); setMenu(false); gear.focus(); } });
   document.addEventListener("pointerdown", e=>{ if(!menu.hidden && !menu.contains(e.target) && !gear.contains(e.target)) setMenu(false); });
   function paintLegend(){
     if(nowMode()) $("legend").innerHTML = SUP.map(k=>`<span${T(DEF.on(k))}>${ic(k,true)}${SHORTN[k]}</span>`).join("")+`<i class="sep"></i><span>Life support running at 07:00</span>`;
@@ -1297,7 +1297,7 @@ details.more summary:hover{color:var(--blue)}
   const VIT=[["heart_rate","Heart rate","bpm"],["map","Mean arterial pressure","mmHg",65],["spo2","SpO2","%"],["respiratory_rate","Respiratory rate","/min"]];
   const closeRoom = () => { location.hash=$("back").getAttribute("href"); };
   roomview.addEventListener("pointerdown", e=>{ if(e.target===roomview) closeRoom(); });
-  document.addEventListener("keydown", e=>{ if(e.key==="Escape" && room!==null && $("setmenu").hidden) closeRoom(); });
+  document.addEventListener("keydown", e=>{ if(e.key==="Escape" && room!==null && $("setmenu").hidden && !e.defaultPrevented) closeRoom(); });
   function paintScope(){ const el=$("chat-scope"); el.textContent = chatScope!==null ? `Bed ${chatScope}` : "Unit"; el.disabled = room===null;      // what the chat is about; on a room page it switches between that room and the unit
     el.setAttribute("aria-label", chatScope!==null ? `Asking about bed ${chatScope}. Switch to the unit` : room!==null ? `Asking about the unit. Switch to bed ${room}` : "Asking about the unit"); }
   function showRoom(n){
```

### pr16-06: index.html:906 (PR 16 page)

Why it matters: trajectory returns 'steady' when on_now is null but p is present; defensive guard for unknown support.

Patch `pr16-06-trajectory-unknown-support.patch`:

```diff
diff --git a/backend/app/static/index.html b/backend/app/static/index.html
index b3ba59f..5655ca7 100644
--- a/backend/app/static/index.html
+++ b/backend/app/static/index.html
@@ -907,7 +907,7 @@ details.more summary:hover{color:var(--ink)}
   function traj(r){ if(r.present===false) return "ended"; if(isPending()) return "unknown"; const a=anyNew(r), dep=r.p.icu_departure;
     if(a>=upLine(lines.base) || SUP.some(k=>!r.on_now[k] && r.p[k]!=null && r.p[k]>=upLine(lines[k]))) return "worse";
     if(a>=lines.base || nextList(r).length) return "watch";
-    if(a==null || dep==null) return "unknown";
+    if(a==null || dep==null || unknownList(r).length) return "unknown";
     if(onList(r).length && dep<lines.base) return "hold";
     return dep!=null && dep>=lines.leave ? "leave" : "steady"; }
   /* a room flagged by the combined chance alone (no single support at its line): a plus in a ring carries the combined chance */
diff --git a/mockups/command-center.html b/mockups/command-center.html
index b3ba59f..5655ca7 100644
--- a/mockups/command-center.html
+++ b/mockups/command-center.html
@@ -907,7 +907,7 @@ details.more summary:hover{color:var(--ink)}
   function traj(r){ if(r.present===false) return "ended"; if(isPending()) return "unknown"; const a=anyNew(r), dep=r.p.icu_departure;
     if(a>=upLine(lines.base) || SUP.some(k=>!r.on_now[k] && r.p[k]!=null && r.p[k]>=upLine(lines[k]))) return "worse";
     if(a>=lines.base || nextList(r).length) return "watch";
-    if(a==null || dep==null) return "unknown";
+    if(a==null || dep==null || unknownList(r).length) return "unknown";
     if(onList(r).length && dep<lines.base) return "hold";
     return dep!=null && dep>=lines.leave ? "leave" : "steady"; }
   /* a room flagged by the combined chance alone (no single support at its line): a plus in a ring carries the combined chance */
```

### pr16-07: index.html:1272 (PR 16 page)

Why it matters: machFree clamps to 0 while usageBar shows on+free as the total, so a total below use reads wrong. The same defect exists at other lines on the PR 19 page.

Patch `pr16-07-machine-total-below-use.patch`:

```diff
diff --git a/backend/app/static/index.html b/backend/app/static/index.html
index b3ba59f..9239e40 100644
--- a/backend/app/static/index.html
+++ b/backend/app/static/index.html
@@ -1030,7 +1030,7 @@ details.more summary:hover{color:var(--ink)}
   }
   /* Dema's capacity bar, used when a number free is set: the whole bar is the total (in use + free); solid = in use now,
      lighter = with the flagged beds; it turns red when that passes the total. */
-  function usageBar(on, free, pred, tip){ const tot=on+free, sum=on+pred, over=sum>tot, max=Math.max(tot,1), x=v=>Math.round((6+(Math.min(v,max)/max)*288)*10)/10, col=over?"var(--red)":"var(--blue)";
+  function usageBar(on, free, pred, tip, total){ const tot=total!=null?total:on+free, sum=on+pred, over=sum>tot, max=Math.max(tot,1), x=v=>Math.round((6+(Math.min(v,max)/max)*288)*10)/10, col=over?"var(--red)":"var(--blue)";
     return `<svg class="ubar" viewBox="0 0 300 46" preserveAspectRatio="xMinYMid meet" role="img" aria-label="${on} in use now, ${sum} with the flagged beds, ${tot} in total${over?": over the total":""}"${tip?T(tip):""}>
       <rect x="0" y="0" width="300" height="46" fill="none" pointer-events="all"/><line x1="6" x2="294" y1="25" y2="25" stroke="var(--fig)" stroke-width="10" stroke-linecap="round"/>
       ${sum?`<line x1="6" x2="${x(sum)}" y1="25" y2="25" stroke="${col}" stroke-opacity=".4" stroke-width="10" stroke-linecap="round"/>`:""}
@@ -1060,7 +1060,7 @@ details.more summary:hover{color:var(--ink)}
       return `<article class="wc${lv?` lv-${lv}`:""}" data-k="${k}" style="order:${first===k?0:1};--w:${Math.max(5,Math.min(10,Math.max(on.length,n)))}" aria-labelledby="wc-${k}">
         <header>${ic(k,true)}<div><h3 id="wc-${k}">${CARDN[k]}</h3><p class="wsub">patients expected to start ${START[k]} in the next 24 h</p></div>${st?`<span class="band lv-${lv}"${T(DEF.band[st])}>${st}</span>`:""}</header>
         <div class="nums"><span${T(`Patients on ${START[k]} at 07:00`)}><b>${ls.now_by[k]}</b><i>on now</i></span>${free!=null?`<span${T(`${k==="imv"?"Ventilators":"CRRT machines"} free: ${free}${machines[k]!=null?` of ${machines[k]} on the unit`:""}`)}><b>${free}</b><i>free${machines[k]!=null?` of ${machines[k]}`:""}</i></span>`:""}<span class="f"${T(DEF.bar("Expected new starts",q))}><b>+${q.p50}</b><i>expected new starts (${q.p10} to ${q.p90})</i></span></div>
-        ${free!=null ? usageBar(on.length, free, n, `${on.length} in use now, ${on.length+n} with the ${n} flagged, ${on.length+free} in total`) : bar(q,null,null,top,DEF.bar("Expected new starts",q))}
+        ${free!=null ? usageBar(on.length, free, n, `${on.length} in use now, ${on.length+n} with the ${n} flagged, ${machines[k]!=null?machines[k]:on.length+free} in total`, machines[k]) : bar(q,null,null,top,DEF.bar("Expected new starts",q))}
         ${freeable?`<p class="frees"${T(`Beds on ${START[k]} now with ${P(lines.leave)} or more to leave the ICU`)}><i>${ic(k,true)}</i><b>${freeable}</b> may free up if likely leavers go</p>`:""}
         <span class="gl">On now</span>${set(on.map(r=>fig(r,"on",null,"",`on ${START[k]} now`)),"None")}
         <span class="gl"${T(DEF.flag)}>Beds at ${P(lines[k])} or more · ${n} ${n===1?"bed":"beds"}</span>${set(may.map(r=>fig(r,r.p[k]>=upLine(lines[k])?"w":"",r.p[k],esc(pct(r.p[k])),`${pct(r.p[k])} chance of starting ${START[k]}`)),"None")}</article>`; };
diff --git a/mockups/command-center.html b/mockups/command-center.html
index b3ba59f..9239e40 100644
--- a/mockups/command-center.html
+++ b/mockups/command-center.html
@@ -1030,7 +1030,7 @@ details.more summary:hover{color:var(--ink)}
   }
   /* Dema's capacity bar, used when a number free is set: the whole bar is the total (in use + free); solid = in use now,
      lighter = with the flagged beds; it turns red when that passes the total. */
-  function usageBar(on, free, pred, tip){ const tot=on+free, sum=on+pred, over=sum>tot, max=Math.max(tot,1), x=v=>Math.round((6+(Math.min(v,max)/max)*288)*10)/10, col=over?"var(--red)":"var(--blue)";
+  function usageBar(on, free, pred, tip, total){ const tot=total!=null?total:on+free, sum=on+pred, over=sum>tot, max=Math.max(tot,1), x=v=>Math.round((6+(Math.min(v,max)/max)*288)*10)/10, col=over?"var(--red)":"var(--blue)";
     return `<svg class="ubar" viewBox="0 0 300 46" preserveAspectRatio="xMinYMid meet" role="img" aria-label="${on} in use now, ${sum} with the flagged beds, ${tot} in total${over?": over the total":""}"${tip?T(tip):""}>
       <rect x="0" y="0" width="300" height="46" fill="none" pointer-events="all"/><line x1="6" x2="294" y1="25" y2="25" stroke="var(--fig)" stroke-width="10" stroke-linecap="round"/>
       ${sum?`<line x1="6" x2="${x(sum)}" y1="25" y2="25" stroke="${col}" stroke-opacity=".4" stroke-width="10" stroke-linecap="round"/>`:""}
@@ -1060,7 +1060,7 @@ details.more summary:hover{color:var(--ink)}
       return `<article class="wc${lv?` lv-${lv}`:""}" data-k="${k}" style="order:${first===k?0:1};--w:${Math.max(5,Math.min(10,Math.max(on.length,n)))}" aria-labelledby="wc-${k}">
         <header>${ic(k,true)}<div><h3 id="wc-${k}">${CARDN[k]}</h3><p class="wsub">patients expected to start ${START[k]} in the next 24 h</p></div>${st?`<span class="band lv-${lv}"${T(DEF.band[st])}>${st}</span>`:""}</header>
         <div class="nums"><span${T(`Patients on ${START[k]} at 07:00`)}><b>${ls.now_by[k]}</b><i>on now</i></span>${free!=null?`<span${T(`${k==="imv"?"Ventilators":"CRRT machines"} free: ${free}${machines[k]!=null?` of ${machines[k]} on the unit`:""}`)}><b>${free}</b><i>free${machines[k]!=null?` of ${machines[k]}`:""}</i></span>`:""}<span class="f"${T(DEF.bar("Expected new starts",q))}><b>+${q.p50}</b><i>expected new starts (${q.p10} to ${q.p90})</i></span></div>
-        ${free!=null ? usageBar(on.length, free, n, `${on.length} in use now, ${on.length+n} with the ${n} flagged, ${on.length+free} in total`) : bar(q,null,null,top,DEF.bar("Expected new starts",q))}
+        ${free!=null ? usageBar(on.length, free, n, `${on.length} in use now, ${on.length+n} with the ${n} flagged, ${machines[k]!=null?machines[k]:on.length+free} in total`, machines[k]) : bar(q,null,null,top,DEF.bar("Expected new starts",q))}
         ${freeable?`<p class="frees"${T(`Beds on ${START[k]} now with ${P(lines.leave)} or more to leave the ICU`)}><i>${ic(k,true)}</i><b>${freeable}</b> may free up if likely leavers go</p>`:""}
         <span class="gl">On now</span>${set(on.map(r=>fig(r,"on",null,"",`on ${START[k]} now`)),"None")}
         <span class="gl"${T(DEF.flag)}>Beds at ${P(lines[k])} or more · ${n} ${n===1?"bed":"beds"}</span>${set(may.map(r=>fig(r,r.p[k]>=upLine(lines[k])?"w":"",r.p[k],esc(pct(r.p[k])),`${pct(r.p[k])} chance of starting ${START[k]}`)),"None")}</article>`; };
```

### pr16-08: index.html:1385 (PR 16 page)

Why it matters: Close does not invalidate a pending /api/ask, so a late answer lands in a closed chat. Same on the PR 19 page at other lines.

Patch `pr16-08-close-invalidates-pending-answers.patch`:

```diff
diff --git a/backend/app/static/index.html b/backend/app/static/index.html
index b3ba59f..e19aa40 100644
--- a/backend/app/static/index.html
+++ b/backend/app/static/index.html
@@ -1304,7 +1304,7 @@ details.more summary:hover{color:var(--ink)}
   /* ---------- chat widget: a launcher at the bottom right and a non-modal panel. Open or closed is remembered; the draft and messages last for the session. ---------- */
   const log=$("log"), chatbtn=$("chatbtn"), chatpanel=$("chatpanel"), qEl=$("q"), sendBtn=$("send");
   const CHAT_DOWN = "Can't reach the chat right now. Try again.";
-  let chatScope=null, chatSeen=null, askCtl=null;      // chatScope: a room number, or null for the unit
+  let chatScope=null, chatSeen=null, askCtl=null, chatGen=0; const askCtls=new Set();      // chatScope: a room number, or null for the unit
   const UNIT_Q = ["Who should we worry about first?","How many ventilators will we need?","Who is likely to leave today?","Summarise the next 24 hours"];
   const roomQ = n => { const r=R(n); return [`Why is this room ${r?TRAJ[traj(r)][0]:"flagged"}?`,"What changed in the last 12 hours?","Chance of leaving the ICU?"]; };
   function renderChips(){      // suggested questions: only while the conversation is empty, and they follow the context
@@ -1368,12 +1368,12 @@ details.more summary:hover{color:var(--ink)}
   }
   async function ask(q){ openChat(false); say(roleLabel(role()),q,"q");
     const th=say("","Thinking…","t"), stop=document.createElement("button"); stop.type="button"; stop.className="stop"; stop.textContent="Stop"; th.appendChild(stop);
-    const ctl=new AbortController(); let stopped=false, a; askCtl=ctl; stop.onclick=()=>{ stopped=true; ctl.abort(); qEl.focus(); };
+    const ctl=new AbortController(); let stopped=false, a; askCtl=ctl; askCtls.add(ctl); const gen=chatGen; stop.onclick=()=>{ stopped=true; ctl.abort(); qEl.focus(); };
     if(LIVE){ try{ const body={question:q, role:role(), seen_made_at:seenMadeAt}; if(chatScope!==null) body.room=chatScope; const rs=await postJSON("/api/ask", body, 60000, ctl);
         a=str(rs.answer,4000)||(rs.ok===false && /^The board server answered/.test(rs.reason||"") ? "" : str(rs.reason,200))||CHAT_DOWN; if(typeof rs.made_at==="string") seenMadeAt=rs.made_at; }catch(e){ a=CHAT_DOWN; }
       schedulePoll(FAST?300:3000); }
     else { await new Promise(res=>{ const t=setTimeout(res, FAST?40:450); ctl.signal.addEventListener("abort",()=>{ clearTimeout(t); res(); }); }); a = stopped ? "" : await Promise.resolve(answer(q)); }
-    th.remove(); if(askCtl===ctl) askCtl=null;
+    th.remove(); askCtls.delete(ctl); if(askCtl===ctl) askCtl=null; if(gen!==chatGen) return;      // Close ended this conversation: drop its late answer
     if(stopped) say("","Stopped.","n"); else say("ICU Horizon",a,"a"); }
   const saveChat = v => { try{ localStorage.setItem("lookahead-chat",v); }catch(e){ /* storage blocked: the widget starts closed next time */ } };
   function grow(){ qEl.style.height="auto"; qEl.style.height=Math.min(qEl.scrollHeight+2, 104)+"px"; sendBtn.disabled=!qEl.value.trim(); }
@@ -1382,7 +1382,7 @@ details.more summary:hover{color:var(--ink)}
       chatSeen = FC && typeof FC.made_at==="string" ? FC.made_at : null; $("chatdot").hidden=true; $("chatdot-l").hidden=true; paintScope(); renderChips(); grow(); }
     if(focusInput) qEl.focus(); }
   function minChat(focus=true){ chatpanel.hidden=true; chatbtn.setAttribute("aria-expanded","false"); document.documentElement.dataset.chat="closed"; saveChat("closed"); if(focus) chatbtn.focus(); }      // the conversation and the draft stay
-  function closeChat(){ if(askCtl) askCtl.abort(); log.innerHTML=""; qEl.value=""; minChat(); }
+  function closeChat(){ chatGen++; for(const c of askCtls) c.abort(); askCtls.clear(); askCtl=null; log.innerHTML=""; qEl.value=""; minChat(); }
   chatbtn.onclick=()=>openChat();
   $("chatmin").onclick=()=>minChat();
   $("chatclose").onclick=closeChat;
diff --git a/mockups/command-center.html b/mockups/command-center.html
index b3ba59f..e19aa40 100644
--- a/mockups/command-center.html
+++ b/mockups/command-center.html
@@ -1304,7 +1304,7 @@ details.more summary:hover{color:var(--ink)}
   /* ---------- chat widget: a launcher at the bottom right and a non-modal panel. Open or closed is remembered; the draft and messages last for the session. ---------- */
   const log=$("log"), chatbtn=$("chatbtn"), chatpanel=$("chatpanel"), qEl=$("q"), sendBtn=$("send");
   const CHAT_DOWN = "Can't reach the chat right now. Try again.";
-  let chatScope=null, chatSeen=null, askCtl=null;      // chatScope: a room number, or null for the unit
+  let chatScope=null, chatSeen=null, askCtl=null, chatGen=0; const askCtls=new Set();      // chatScope: a room number, or null for the unit
   const UNIT_Q = ["Who should we worry about first?","How many ventilators will we need?","Who is likely to leave today?","Summarise the next 24 hours"];
   const roomQ = n => { const r=R(n); return [`Why is this room ${r?TRAJ[traj(r)][0]:"flagged"}?`,"What changed in the last 12 hours?","Chance of leaving the ICU?"]; };
   function renderChips(){      // suggested questions: only while the conversation is empty, and they follow the context
@@ -1368,12 +1368,12 @@ details.more summary:hover{color:var(--ink)}
   }
   async function ask(q){ openChat(false); say(roleLabel(role()),q,"q");
     const th=say("","Thinking…","t"), stop=document.createElement("button"); stop.type="button"; stop.className="stop"; stop.textContent="Stop"; th.appendChild(stop);
-    const ctl=new AbortController(); let stopped=false, a; askCtl=ctl; stop.onclick=()=>{ stopped=true; ctl.abort(); qEl.focus(); };
+    const ctl=new AbortController(); let stopped=false, a; askCtl=ctl; askCtls.add(ctl); const gen=chatGen; stop.onclick=()=>{ stopped=true; ctl.abort(); qEl.focus(); };
     if(LIVE){ try{ const body={question:q, role:role(), seen_made_at:seenMadeAt}; if(chatScope!==null) body.room=chatScope; const rs=await postJSON("/api/ask", body, 60000, ctl);
         a=str(rs.answer,4000)||(rs.ok===false && /^The board server answered/.test(rs.reason||"") ? "" : str(rs.reason,200))||CHAT_DOWN; if(typeof rs.made_at==="string") seenMadeAt=rs.made_at; }catch(e){ a=CHAT_DOWN; }
       schedulePoll(FAST?300:3000); }
     else { await new Promise(res=>{ const t=setTimeout(res, FAST?40:450); ctl.signal.addEventListener("abort",()=>{ clearTimeout(t); res(); }); }); a = stopped ? "" : await Promise.resolve(answer(q)); }
-    th.remove(); if(askCtl===ctl) askCtl=null;
+    th.remove(); askCtls.delete(ctl); if(askCtl===ctl) askCtl=null; if(gen!==chatGen) return;      // Close ended this conversation: drop its late answer
     if(stopped) say("","Stopped.","n"); else say("ICU Horizon",a,"a"); }
   const saveChat = v => { try{ localStorage.setItem("lookahead-chat",v); }catch(e){ /* storage blocked: the widget starts closed next time */ } };
   function grow(){ qEl.style.height="auto"; qEl.style.height=Math.min(qEl.scrollHeight+2, 104)+"px"; sendBtn.disabled=!qEl.value.trim(); }
@@ -1382,7 +1382,7 @@ details.more summary:hover{color:var(--ink)}
       chatSeen = FC && typeof FC.made_at==="string" ? FC.made_at : null; $("chatdot").hidden=true; $("chatdot-l").hidden=true; paintScope(); renderChips(); grow(); }
     if(focusInput) qEl.focus(); }
   function minChat(focus=true){ chatpanel.hidden=true; chatbtn.setAttribute("aria-expanded","false"); document.documentElement.dataset.chat="closed"; saveChat("closed"); if(focus) chatbtn.focus(); }      // the conversation and the draft stay
-  function closeChat(){ if(askCtl) askCtl.abort(); log.innerHTML=""; qEl.value=""; minChat(); }
+  function closeChat(){ chatGen++; for(const c of askCtls) c.abort(); askCtls.clear(); askCtl=null; log.innerHTML=""; qEl.value=""; minChat(); }
   chatbtn.onclick=()=>openChat();
   $("chatmin").onclick=()=>minChat();
   $("chatclose").onclick=closeChat;
```
