"""Stage ward rooms: per-room life-support forecast -> rooms.json (docs/CONTRACT.md).

Stage ward = the open MIMIC-IV Demo (docs/DECISIONS.md D6) by default: a room map
with a stay id outside clif_demo/clif_hospitalization.parquet is refused. Real
MIMIC-IV (J.C., 2026-11-14) is an explicit mode, `--real-ward`; its data stays on
the cluster volumes and rooms.json / forecast.json then carry
"ward": {"source": "mimic-iv", "label": "Real MIMIC-IV · local only"}.

Per room it writes what is on at the cut, the next-24 h
probability of IMV, vasopressor, CRRT, ICU departure and death, the chance of
any new life support, a level (high / medium / low), an "out" tag and a few
readable events from the last 12 h. Output holds room numbers, never stay ids.

Usage (after icutwin-winnow and icutwin-extract on the stage ward):
  python app/rooms.py <stage tokenized_output> --model <mdl-dir> \\
      --probes <probes dir> --stay-ids stage_ward.csv --out rooms.json
  ... --room 7 [--recount --forecast forecast.json]   # room scope
  ... --demo-clock-hours 6                              # recorded for --recount
  ... --real-ward [--demographics <real CLIF folder>]   # a real MIMIC-IV ward
  ... --clif-now <CLIF folder>   # on now (IMV, pressor, CRRT) from raw CLIF
  ... --names <names file> | --names fake   # made-up names on the tiles (default: none)

Room scope rewrites only that room in an existing rooms.json (run the whole ward
first) and recomputes nothing else, unless --recount (then forecast.json is rebuilt
from the whole ward too). Prints counts only, in both modes.
"""

import argparse
import datetime as dt
import json
import math
import pathlib

import numpy as np
import polars as pl
import yaml

try:  # imported as app.rooms (tests) or run as a script (the job)
    from app import aggregate, fake_names
except ImportError:  # pragma: no cover
    import aggregate
    import fake_names

HOSP = "hospitalization_id"
MAX_EVENTS = 8
LOOKBACK_S = 12 * 3600

# tokens that are structure, not events a nurse would read
SKIP = ("BOS", "EOS", "TIME", "CLCK", "HOSP_PREV_DX", "PATIENT", "HOSP")
NOTABLE = {  # token -> plain text
    "ADT//TRANSFER_IN//icu": "Arrived in the ICU",
    "ADT//TRANSFER_IN//ward": "Moved to a ward",
    "ADT//TRANSFER_IN//stepdown": "Moved to a step-down unit",
    "RESP//device_category//imv": "On a ventilator (invasive)",
    "RESP//device_category//nippv": "Non-invasive ventilation",
    "RESP//device_category//high_flow_nc": "High-flow oxygen",
    "RESP//device_category//nasal_cannula": "Oxygen by nasal cannula",
    "RESP//device_category//room_air": "Breathing room air",
    "CRRT//crrt_init": "Kidney replacement (CRRT) recorded",
}
NAMES = {
    "map": "Mean arterial pressure",
    "sbp": "Systolic blood pressure",
    "dbp": "Diastolic blood pressure",
    "heart_rate": "Heart rate",
    "spo2": "Oxygen saturation",
    "resp_rate": "Respiratory rate",
    "temp_c": "Temperature",
    "fio2_set": "FiO2 setting",
    "peep_set": "PEEP setting",
}
PRIORITY = {"ADT": 0, "RESP": 0, "CRRT": 0, "MED_CON": 1, "MED_INT": 2, "LAB_RES": 3}


def _words(s: str) -> str:
    return NAMES.get(s) or s.replace("_", " ").capitalize()


def token_text(word: str) -> str | None:
    """one model token -> a short plain sentence, or None for structure tokens"""
    if word in NOTABLE:
        return NOTABLE[word]
    parts = word.split("//")
    dom = parts[0]
    if dom in SKIP or word.startswith("HOSP//"):
        return None
    # bins are L# / N# / H# (below / inside / above the reference range) where one
    # exists, B# (ascending, no reference range) otherwise: say low / normal / high,
    # and leave the bin out when there is no reference to read it against
    lab = parts[-1] if len(parts) > 2 else ""
    band = {"L": ": low", "N": ": normal", "H": ": high"}.get(lab[:1], "")
    band = band if lab[1:].isdigit() else ""
    c = parts[1] if len(parts) > 1 else ""
    if dom == "MED_CON":
        return f"{_words(c)} infusion running"
    if dom == "MED_INT":
        return f"{_words(c)} dose given"
    if dom == "LAB_RES":
        return f"{_words(c)} result{band}"
    if dom == "LAB_ORD":
        return f"{_words(c)} ordered"
    if dom == "ADT":
        return f"Moved: {_words(parts[-1])}"
    if dom == "CRRT":
        return "Kidney replacement (CRRT) recorded"
    if dom == "CODE_STATUS":
        return "Code status updated"
    return f"{_words(c)}{band}"


def past_events(
    root: pathlib.Path, ids: list[str], words: dict[int, str]
) -> dict[str, list[dict]]:
    """readable events in the 12 h before each stay's cut: [{"h", "text"}], most
    recent first, at most MAX_EVENTS; h is hours before the cut, rounded up and at
    least 1 (an event 3601 s before the cut is in hour 2; 12 h exactly is hour 12;
    older events are left out). Reads the winnower's `tokens_past` / `s_elapsed_past`
    / `cut_s`."""
    out = {i: [] for i in ids}
    for f in sorted(root.glob("*_for_inference.parquet")):
        cols = pl.read_parquet_schema(f)
        if "tokens_past" not in cols:
            continue
        want = [HOSP, "tokens_past", "s_elapsed_past"] + (
            ["cut_s"] if "cut_s" in cols else []
        )
        df = pl.scan_parquet(f).select(want).filter(pl.col(HOSP).is_in(ids)).collect()
        for row in df.iter_rows(named=True):
            toks, secs = row["tokens_past"], row["s_elapsed_past"]
            cut = row.get("cut_s")
            cut = cut if cut is not None else (secs[-1] if secs else 0)
            seen, picked = set(), []
            for tid, s in zip(reversed(toks), reversed(secs)):
                age = cut - s
                if age < 0:  # later records are never recent history
                    continue
                if age > LOOKBACK_S:
                    break
                text = token_text(words.get(int(tid), ""))
                if text is None or text in seen:
                    continue
                seen.add(text)
                dom = words[int(tid)].split("//")[0]
                picked.append((PRIORITY.get(dom, 4), max(age, 0), text))
            picked.sort()
            out[row[HOSP]] = sorted(
                (
                    {"h": max(1, math.ceil(age / 3600)), "text": text}
                    for _, age, text in picked[:MAX_EVENTS]
                ),
                key=lambda e: e["h"],
            )
    return out


def _num(x: float) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), 4)


def demographics(clif: pathlib.Path | None, stay_ids: list[str]) -> dict[str, dict]:
    """age and sex for the room tile, from the CLIF tables of the ward (the open demo
    folder, or with --real-ward the real CLIF folder: stays on the cluster volume).
    Ages of 90 and over show as "90+"."""
    if clif is None:
        return {}
    h = (
        pl.scan_parquet(clif / "clif_hospitalization.parquet")
        .select("hospitalization_id", "patient_id", "age_at_admission")
        .filter(pl.col("hospitalization_id").is_in(stay_ids))
        .collect()
    )
    pt = (
        pl.scan_parquet(clif / "clif_patient.parquet")
        .select("patient_id", "sex_category")
        .filter(pl.col("patient_id").is_in(h["patient_id"].to_list()))
        .collect()
    )
    out = {}
    for sid, age, sex in (
        h.join(pt, on="patient_id", how="left")
        .select("hospitalization_id", "age_at_admission", "sex_category")
        .iter_rows()
    ):
        label = None if age is None else ("90+" if age >= 90 else str(int(age)))
        out[sid] = {
            "age": label,
            "sex": {"Female": "F", "Male": "M"}.get(sex or "", None),
        }
    return out


def room_entries(
    df: pl.DataFrame,
    room_of: dict[str, int],
    events: dict[str, list[dict]],
    cut: dt.datetime,
    now: str,
    demo: dict[str, dict] | None = None,
    clif: dict | None = None,
    pending: bool = False,
    names: dict[str, dict] | None = None,
) -> list[dict]:
    """one rooms.json entry per scored stay that has a room; clif = what is on at the
    cut from raw CLIF (app/clif_now.py), else the tokenized at-cut flags. pending
    (forecast_state "pending-model", scores from aggregate.pending_scores): `p` is
    null everywhere, and `any_life_support` and `level` are null, not 0 and "low"."""
    tab = aggregate.patient_table(df, clif=clif)
    p, on, stopped, sk = tab["p"], tab["on"], tab["stopped"], tab["skipped"]
    any_p = aggregate.p_any_life_support(p)
    ids = df[HOSP].to_list()
    # A support without a score (its probe was skipped, or what runs now is unknown)
    # leaves the combined forecast unknown: never 0 and "low" from the other two.
    no_any = np.any(
        [sk[aggregate.SUPPORT_RESOURCE[s]] for s in aggregate.SUPPORTS], axis=0
    )
    entries = []
    for i, sid in enumerate(ids):
        if sid not in room_of:
            continue
        dep = None if pending else _num(p["icu_departure"][i])
        known_supports = sum(on[k][i] for k in aggregate.SUPPORTS)
        unknown_supports = sum(tab["unknown"][k][i] for k in aggregate.SUPPORTS)
        entries.append(
            {
                "room": room_of[sid],
                **({"name": names[sid]} if names and sid in names else {}),
                "age": (demo or {}).get(sid, {}).get("age"),
                "sex": (demo or {}).get(sid, {}).get("sex"),
                "updated_at": now,
                "cut_time": cut.isoformat(timespec="seconds"),
                "window": aggregate.window_for(cut),
                "scope": "room",
                "on_now": {
                    **{
                        s: None if tab["unknown"][s][i] else bool(on[s][i])
                        for s in aggregate.SUPPORTS
                    },
                    "ecmo": None,  # no ecmo/mcs token: not available
                },
                "on_life_support": (
                    None
                    if known_supports < 2 <= known_supports + unknown_supports
                    else bool(known_supports >= 2)
                ),
                "stopped_before_cut": {
                    "imv": bool(stopped["imv"][i]),
                    "vasopressor": bool(stopped["vasopressor"][i]),
                    "crrt": bool(stopped["crrt"][i]),
                },
                "skipped": {
                    "imv": bool(sk["ventilator"][i]),
                    "vasopressor": bool(sk["vasopressor"][i]),
                    "crrt": bool(sk["crrt"][i]),
                    "icu_departure": bool(sk["icu_departure"][i]),
                    "death": bool(sk["death"][i]),
                },
                "p": {
                    "imv": None if pending else _num(p["ventilator"][i]),
                    "vasopressor": None if pending else _num(p["vasopressor"][i]),
                    "crrt": None if pending else _num(p["crrt"][i]),
                    "icu_departure": dep,
                    "death": None if pending else _num(p["death"][i]),
                },
                "any_life_support": None if pending or no_any[i] else _num(any_p[i]),
                "level": None
                if pending
                else "unavailable"
                if no_any[i]
                else aggregate.level_of(float(any_p[i])),
                "out": dep is not None and dep >= aggregate.OUT_TAG,
                "past_12h": events.get(sid, []),
            }
        )
    return sorted(entries, key=lambda e: e["room"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tokenized_output", type=pathlib.Path, help="stage ward folder")
    ap.add_argument("--model", type=pathlib.Path, required=True, help="mdl-<run>/")
    ap.add_argument("--probes", type=pathlib.Path, help="folder from --save-probes")
    ap.add_argument(
        "--stay-ids", type=pathlib.Path, required=True, help="stage_ward.csv"
    )
    ap.add_argument("--out", type=pathlib.Path, required=True, help="rooms.json")
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--room", type=int, help="room scope: rewrite this room only")
    scope.add_argument("--stay", help="room scope by hospitalization id")
    ap.add_argument(
        "--no-apply",
        action="store_true",
        help="use the existing scores-rep-based file (icutwin-rep-score "
        "--apply-probes already ran)",
    )
    ap.add_argument(
        "--cut-time",
        type=aggregate.cut_arg,
        help="ISO time WITH a UTC offset, taken as given (default: the 07:00 "
        "nearest to now; with --demo-clock-hours, the last 07:00 plus those hours)",
    )
    ap.add_argument(
        "--tz",
        default=aggregate.DEFAULT_TZ,
        help="site time zone for the default 07:00 cut (default America/Chicago: "
        "the event and t7-twin's TZ); pass it explicitly when the site differs",
    )
    ap.add_argument(
        "--demo-clock-hours",
        type=float,
        default=0,
        help="the offset given to icutwin-winnow; recorded in forecast.json and "
        "added to the default cut_time",
    )
    ap.add_argument(
        "--real-ward",
        action="store_true",
        help="the room map is a real MIMIC-IV ward (stay ids outside the open demo "
        "CLIF): refused without this flag. Everything stays on the cluster volumes; "
        "rooms.json says 'Real MIMIC-IV · local only'",
    )
    ap.add_argument(
        "--recount",
        action="store_true",
        help="also rebuild forecast.json from the whole ward (needs --forecast)",
    )
    ap.add_argument("--forecast", type=pathlib.Path, help="forecast.json for --recount")
    ap.add_argument("--baseline", type=pathlib.Path)
    ap.add_argument("--capacity", type=pathlib.Path)
    ap.add_argument("--beds", type=int, default=25)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--clif-now",
        type=pathlib.Path,
        help="CLIF folder: IMV, vasopressor and CRRT running at each stay's cut are "
        "read from it, not from the tokenized at-cut flags (on_now_source 'clif'); "
        "the open-demo guard applies as for --real-ward",
    )
    ap.add_argument(
        "--demographics",
        type=pathlib.Path,
        help="CLIF folder for age and sex on the tile: the open demo's, or with "
        "--real-ward the real one",
    )
    ap.add_argument(
        "--names",
        help="made-up names for the room tiles: a names file (hospitalization_id, "
        "first_name, last_name, display_name, name_source 'fictional'; it stays "
        "beside the ward's data) or 'fake' for the seeded generator. Default: none",
    )
    ap.add_argument(
        "--unit-name",
        default=aggregate.UNIT_NAME,
        help="the unit's name in forecast.json (--recount)",
    )
    a = ap.parse_args()

    root = a.tokenized_output.resolve()
    room_of = aggregate.read_room_map(a.stay_ids)
    if not room_of:
        raise SystemExit(f"no rooms in {a.stay_ids}")
    ward = aggregate.check_ward(room_of, a.real_ward)  # refuses a real ward by default
    stay_of = {r: s for s, r in room_of.items()}
    room = a.room if a.stay is None else room_of.get(a.stay)
    if a.stay is not None and room is None:
        raise SystemExit("that stay is not in the ward")
    if room is not None and room not in stay_of:
        raise SystemExit(f"room {room} is not in the ward")
    ids = list(room_of) if room is None else [stay_of[room]]
    source = "clif" if a.clif_now else "tokens"
    prior = None
    if room is not None:  # room scope edits a whole-ward file; it never starts one
        if not a.out.is_file():
            raise SystemExit(f"{a.out.name} not found: run the whole ward first")
        prior = json.loads(a.out.read_text())
        if prior.get("ward") != ward:
            was = (prior.get("ward") or {}).get("source")
            raise SystemExit(
                f"{a.out.name} is for another ward ({was}, not {ward['source']}): "
                "run the whole ward first"
            )
        if prior.get("on_now_source", "tokens") != source:
            raise SystemExit(
                f"{a.out.name} was made with on-now from "
                f"{prior.get('on_now_source', 'tokens')}, not {source}: "
                "run the whole ward first"
            )

    from icutwin.scoring import rep_based  # lazy: sklearn / joblib

    model_name = a.model.name
    try:
        if a.no_apply:  # this model's scores, made with these weights
            scores = aggregate.scores_path(root, model_name)
            rep_based.verify_scores(scores, a.model)
            df = pl.read_parquet(scores).filter(pl.col(HOSP).is_in(ids))
        else:
            if not a.probes:
                raise SystemExit("--probes is required unless --no-apply")
            rep_based.check_features_current(root, model_name, ids)
            side = None if room is None else f"scores-rep-room-{room}.parquet"
            df = pl.read_parquet(
                rep_based.apply_probes(root, a.model, a.probes, ids, out_name=side)
            )
    except ValueError as e:  # stale features, other weights: say what to rerun
        raise SystemExit(str(e)) from None
    vocab = yaml.safe_load((root / "vocab.yaml").read_text())["lookup"]
    words = {int(i): w for w, i in vocab.items()}
    now = aggregate.now_iso()
    cut = aggregate.cut_time_for(
        dt.datetime.fromisoformat(now), a.tz, a.cut_time, a.demo_clock_hours
    )
    clif = (
        aggregate.clif_now_mod.running_for_stays(
            a.clif_now, df[HOSP].to_list(), a.demo_clock_hours
        )
        if a.clif_now
        else None
    )
    demo = demographics(a.demographics, df[HOSP].to_list())
    names, name_counts = fake_names.names_for(
        a.names, room_of, {s: d["sex"] for s, d in demo.items()}
    )
    entries = room_entries(
        df,
        room_of,
        past_events(root, df[HOSP].to_list(), words),
        cut,
        now,
        demo,
        clif,
        names=names,
    )

    if room is None:
        doc = {
            "made_at": now,
            "ward": ward,
            "forecast_state": aggregate.READY,
            "rooms": entries,
        }
    else:
        doc = prior
        if doc.get("forecast_state", aggregate.READY) != aggregate.READY:
            raise SystemExit(
                f"{a.out.name} has no forecast yet ({doc['forecast_state']}): "
                "run the whole ward first"
            )
        doc["ward"] = ward
        doc["rooms"] = sorted(
            [r for r in doc["rooms"] if r["room"] != room] + entries,
            key=lambda r: r["room"],
        )
    doc["on_now_source"] = source
    doc.pop("names", None)
    if any("name" in r for r in doc["rooms"]):
        doc["names"] = "fictional"  # invented for the demo, never a real name
    # ward rooms with no entry (their record ends before a moved cut): never negative
    doc["dropped"] = len(set(room_of.values()) - {r["room"] for r in doc["rooms"]})
    aggregate.write_json(a.out, doc)

    if a.recount:
        if not a.forecast:
            raise SystemExit("--recount needs --forecast")
        if room is not None and not a.no_apply:
            try:
                rep_based.apply_probes(root, a.model, a.probes, list(room_of))
            except ValueError as e:
                raise SystemExit(str(e)) from None
        full = pl.read_parquet(aggregate.scores_path(root, model_name))
        fc = aggregate.build_forecast(
            full,
            model_name,
            beds=a.beds,
            seed=a.seed,
            baseline=a.baseline,
            capacity=a.capacity,
            cut_time=a.cut_time,
            tz=a.tz,
            demo_clock_hours=a.demo_clock_hours,
            stage_csv=a.stay_ids,
            ward=ward,
            clif_now=a.clif_now,
            unit_name=a.unit_name,
        )
        aggregate.write_json(a.forecast, fc)
    print(  # counts only
        json.dumps(
            {
                "scope": "unit" if room is None else "room",
                "rooms_written": len(entries),
                "rooms_in_file": len(doc["rooms"]),
                "dropped": doc["dropped"],
                "recount": bool(a.recount),
                "on_now_source": source,
                **name_counts,  # counts only: a name never reaches stdout
                "high": sum(e["level"] == "high" for e in entries),
            }
        )
    )


if __name__ == "__main__":
    main()
