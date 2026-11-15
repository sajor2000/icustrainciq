"""Publish one restricted, selected-25 replay context from precomputed probe scores.

The replay clock is a display clock. Each stay retains its own winnower cut;
publication does not claim that historical stays shared a calendar-time cut.
"""

import argparse
import contextlib
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import pathlib
import re
import sys
import tempfile
import uuid


class ContextUnavailable(ValueError):
    """A complete, consistent context cannot be read or published."""


def read_roster(path) -> dict[str, int]:
    """Validate the private CSV; errors contain counts/rules, never source IDs."""
    try:
        with pathlib.Path(path).open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if set(reader.fieldnames or []) != {"room", "hospitalization_id"}:
                raise ValueError
            rows = list(reader)
        slots = [int(r["room"]) for r in rows]
        ids = [r["hospitalization_id"] for r in rows]
        if (
            len(rows) != 25
            or set(slots) != set(range(1, 26))
            or len(set(ids)) != 25
            or any(not s or s != s.strip() for s in ids)
        ):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError, csv.Error):
        raise ContextUnavailable(
            "Private roster must contain exactly 25 unique hospitalization IDs "
            "and unique rooms 1 through 25, with only room,hospitalization_id columns"
        ) from None
    return dict(zip(ids, slots))


def _aware(value) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError
    return parsed


def _check_safe_json(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in {
                "hospitalization_id",
                "hospitalization_ids",
                "patient_id",
                "patient_ids",
                "stay_id",
                "stay_ids",
                "subject_id",
                "hadm_id",
                "mrn",
            }:
                raise ValueError
            _check_safe_json(child)
    elif isinstance(value, list):
        for child in value:
            _check_safe_json(child)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError
    elif isinstance(value, str) and re.search(r"(?<!\d)2[1-9]\d{2}-\d{2}-\d{2}", value):
        raise ValueError


def _validate_context(doc: dict) -> dict:
    _check_safe_json(doc)
    identity = (doc["snapshot_id"], doc["cohort_id"])
    if (
        type(doc["schema_version"]) is not int
        or doc["schema_version"] != 1
        or not isinstance(identity[0], str)
        or str(uuid.UUID(identity[0])) != identity[0]
        or not isinstance(identity[1], str)
        or not re.fullmatch(r"[0-9a-f]{64}", identity[1])
        or any(
            (doc[v]["snapshot_id"], doc[v]["cohort_id"]) != identity
            for v in ("forecast", "rooms")
        )
        or type(doc["roster_size"]) is not int
        or doc["roster_size"] != 25
        or type(doc["forecast"]["beds"]) is not int
        or not 0 <= doc["forecast"]["beds"] <= 25
        or doc["clock_mode"] != "research_replay"
    ):
        raise ValueError
    state = doc.get("forecast_state", "ready")
    if state not in ("ready", "pending-model") or any(
        doc[v].get("forecast_state", "ready") != state for v in ("forecast", "rooms")
    ):
        raise ValueError
    entries = doc["rooms"]["rooms"]
    if (
        not isinstance(entries, list)
        or len(entries) != 25
        or any(type(e["room"]) is not int for e in entries)
        or {e["room"] for e in entries} != set(range(1, 26))
    ):
        raise ValueError
    if any("present" in entry for entry in entries):
        if any(type(e.get("present")) is not bool for e in entries):
            raise ValueError
        present = sum(e["present"] for e in entries)
        if (
            doc["forecast"]["beds"] != present
            or doc["rooms"].get("dropped") != 25 - present
        ):
            raise ValueError
        for entry in entries:
            if not entry["present"] and (
                any(
                    entry.get(k) is not None
                    for k in (
                        "age",
                        "sex",
                        "any_life_support",
                        "level",
                        "on_life_support",
                    )
                )
                or any(v is not None for v in entry.get("on_now", {}).values())
                or any(v is not None for v in entry.get("p", {}).values())
                or entry.get("past_12h") != []
                or entry.get("out") is not False
            ):
                raise ValueError
    elif doc["forecast"]["beds"] != 25:
        raise ValueError
    for entry in entries:
        events = entry.get("past_12h", [])
        if not isinstance(events, list) or len(events) > 8:
            raise ValueError
        for event in events:
            if (
                not isinstance(event, dict)
                or not {"h", "text"}.issubset(event)
                or type(event["h"]) is not int
                or not 1 <= event["h"] <= 12
                or not isinstance(event["text"], str)
                or not event["text"].strip()
            ):
                raise ValueError
    source = doc["source"]
    if (
        source["kind"] not in ("mimic-iv", "open-demo")
        or not isinstance(source["label"], str)
        or not source["label"].strip()
        or not (
            source["dataset_version"] is None
            or isinstance(source["dataset_version"], str)
        )
    ):
        raise ValueError
    ward = {"source": source["kind"], "label": source["label"]}
    if any(doc[v]["ward"] != ward for v in ("forecast", "rooms")):
        raise ValueError
    for timestamp in (
        doc["published_at"],
        doc["forecast"]["made_at"],
        doc["rooms"]["made_at"],
    ):
        _aware(timestamp)
    cut = _aware(doc["forecast"]["cut_time"])
    window = doc["forecast"]["window"]
    if (
        _aware(window["start"]) != cut
        or _aware(window["end"]) != cut + dt.timedelta(hours=24)
        or any("cut_time" in e and _aware(e["cut_time"]) != cut for e in entries)
    ):
        raise ValueError
    provenance = doc["provenance"]
    if state == "pending-model":
        if (
            doc.get("forecast_state") != state
            or provenance.get("model") is not None
            or provenance.get("weights_sha256") is not None
            or provenance.get("scoring") != state
            or provenance.get("unit_counts") is not None
            or not isinstance(provenance.get("cut_semantics"), str)
            or doc["forecast"].get("yardstick") is not None
            or doc["forecast"].get("check_first") != []
        ):
            raise ValueError
        tasks = {"ventilator", "vasopressor", "crrt", "death", "icu_departure"}
        resources = doc["forecast"]["resources"]
        if set(resources) != tasks:
            raise ValueError
        future = [
            *resources.values(),
            doc["forecast"]["life_support"]["expected_new_patients"],
            *doc["forecast"]["life_support"]["expected_by"].values(),
        ]
        for horizon in doc["forecast"].get("horizons", {}).values():
            future.extend(horizon.get("resources", {}).values())
        if any(
            x.get("available") is not False
            or any(x.get(k) is not None for k in ("p10", "p50", "p90", "expected"))
            for x in future
        ):
            raise ValueError
        if any(
            any(v is not None for v in e.get("p", {}).values())
            or e.get("any_life_support") is not None
            or e.get("level") is not None
            for e in entries
        ):
            raise ValueError
        return doc
    if (
        any(
            not isinstance(provenance[k], str) or not provenance[k].strip()
            for k in ("model", "scoring", "unit_counts", "cut_semantics")
        )
        or not isinstance(provenance["weights_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", provenance["weights_sha256"])
    ):
        raise ValueError
    return doc


def load_context(path) -> dict:
    """Read one validated envelope, using only stdlib and no source data."""
    try:
        return _validate_context(
            json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise ContextUnavailable("Context is unavailable or inconsistent") from None


def verified_scores(root, model, ids, demo_clock_hours=0):
    """Verify selected scores, extracted features, winnower cuts and actual weights."""
    import polars as pl
    import yaml

    from app import aggregate, rooms
    from icutwin.scoring import rep_based

    root, model = pathlib.Path(root), pathlib.Path(model)
    scores = aggregate.scores_path(root, model.name)
    try:
        meta = json.loads(rep_based.scores_meta_path(scores).read_text())
        if meta.get("model") != model.name or not re.fullmatch(
            r"[0-9a-f]{64}", meta.get("weights_sha256") or ""
        ):
            raise ValueError
        rep_based.verify_scores(scores, model)
    except (OSError, ValueError, TypeError):
        raise ContextUnavailable(
            "Score/model provenance is missing or mismatched"
        ) from None
    df = pl.scan_parquet(scores).filter(pl.col(rooms.HOSP).is_in(ids)).collect()
    for column, dtype in df.schema.items():
        if column.endswith("_rep_score"):
            if (not dtype.is_numeric() and dtype != pl.Null) or any(
                x is not None
                and not math.isnan(x)
                and (not math.isfinite(x) or not 0 <= x <= 1)
                for x in df[column]
            ):
                raise ContextUnavailable(
                    "Probe probabilities must be numeric values in [0, 1] "
                    "or unavailable"
                )
    selected = {"scores": df}
    for artifact in ("labels", "features"):
        parts = []
        for split in rep_based.SPLITS:
            path = root / (
                f"{split}_for_inference.parquet"
                if artifact == "labels"
                else f"features-{split}-{model.name}.parquet"
            )
            if path.is_file():
                cols = pl.read_parquet_schema(path)
                want = [
                    c
                    for c in cols
                    if c == rooms.HOSP
                    or c in rep_based.CUT_COLS
                    or (
                        artifact == "labels"
                        and (c.endswith("_past") or c in aggregate.AT_CUT_COL.values())
                    )
                ]
                parts.append(
                    pl.scan_parquet(path)
                    .select(want)
                    .filter(pl.col(rooms.HOSP).is_in(ids))
                    .collect()
                )
        selected[artifact] = (
            pl.concat(parts, how="diagonal_relaxed")
            if parts
            else pl.DataFrame({rooms.HOSP: []})
        )
    for artifact, rows in selected.items():
        if (
            rows.height != len(ids)
            or rows[rooms.HOSP].n_unique() != len(ids)
            or set(rows[rooms.HOSP]) != set(ids)
        ):
            raise ContextUnavailable(
                f"Selected {artifact} are incomplete or duplicated; "
                "complete matching selected stays are required"
            )
    labels = selected["labels"].sort(rooms.HOSP)
    if any(
        c not in labels.columns
        or labels.schema[c] != pl.Boolean
        or labels[c].null_count()
        for c in aggregate.AT_CUT_COL.values()
    ):
        raise ContextUnavailable("Observed support at the cut is missing or invalid")
    for artifact in ("scores", "features"):
        rows = selected[artifact].sort(rooms.HOSP)
        compare = (
            [c for c in labels.columns if not isinstance(labels.schema[c], pl.List)]
            if artifact == "scores"
            else [rooms.HOSP, *rep_based.CUT_COLS]
        )
        if (
            not set(rep_based.CUT_COLS).issubset(labels.columns)
            or not set(compare).issubset(rows.columns)
            or not rows.select(compare).equals(labels.select(compare))
        ):
            raise ContextUnavailable(
                f"Selected {artifact} do not match the current winnower cut/labels; "
                "extract and score again"
            )
    rep_based.check_features_current(root, model.name, ids, model_home=model)
    vocab = yaml.safe_load((root / "vocab.yaml").read_text())["lookup"]
    words = {int(i): w for w, i in vocab.items()}
    icu = vocab.get("ADT//TRANSFER_IN//icu")
    try:
        for row in labels.iter_rows(named=True):
            tokens, seconds = row["tokens_past"], row["s_elapsed_past"]
            arrival = seconds[tokens.index(icu)]
            if (
                len(tokens) != len(seconds)
                or len(tokens) != row["last_valid"]
                or any(
                    not math.isfinite(s) or not 0 <= s < row["cut_s"] for s in seconds
                )
                or not math.isclose(
                    row["cut_s"] - arrival,
                    86400 + demo_clock_hours * 3600,
                    abs_tol=1e-6,
                )
            ):
                raise ValueError
    except (KeyError, ValueError, TypeError, IndexError):
        raise ContextUnavailable(
            "Stored winnower cuts must be 24 hours after ICU arrival plus "
            "the declared replay offset"
        ) from None
    provenance = {
        "model": model.name,
        "weights_sha256": meta["weights_sha256"],
        "scoring": "last-hidden-state logistic probes",
        "unit_counts": "exact Poisson-binomial",
        "cut_semantics": "per-stay winnower cut; shared research replay clock",
    }
    return df, provenance, words


def active_census(clif, room_of, demo_clock_hours=0):
    """(each roster stay's own cut, the ids still in the ICU at it). The roster keeps
    all 25 room slots; scores are verified and views built for the active ids only."""
    from app import clif_now

    try:
        cuts = clif_now.stay_cuts(clif, list(room_of), demo_clock_hours)
    except SystemExit:
        raise ContextUnavailable(
            "Selected CLIF hospitalizations or ICU arrivals are incomplete"
        ) from None
    here = clif_now.present_at_cut(clif, cuts)
    return cuts, [sid for sid in room_of if here[sid]]


def build_context(
    *,
    root,
    df,
    room_of,
    clif,
    cut_time,
    ward,
    forecast_state,
    provenance=None,
    demo_clock_hours=0,
    tz="America/Chicago",
    dataset_version=None,
    current=None,
    baseline=None,
    capacity=None,
    names=None,
    unit_name=None,
):
    """Build both views from this same selected frame and stable private room map.

    Callers must verify ready model artifacts before passing their provenance.
    This factory independently checks the CLIF census at the per-stay cuts.
    """
    import polars as pl
    import yaml

    from app import aggregate, clif_now, fake_names, rooms

    root, clif = pathlib.Path(root), pathlib.Path(clif)
    if (
        len(room_of) != 25
        or set(room_of.values()) != set(range(1, 26))
        or forecast_state not in (aggregate.READY, aggregate.PENDING)
        or not math.isfinite(demo_clock_hours)
        or demo_clock_hours < 0
    ):
        raise ContextUnavailable(
            "A stable 25-room roster and valid replay state are required"
        )
    cuts, ids = active_census(clif, room_of, demo_clock_hours)
    if (
        df.height != len(ids)
        or df[rooms.HOSP].n_unique() != len(ids)
        or set(df[rooms.HOSP]) != set(ids)
    ):
        raise ContextUnavailable(
            "Selected frame is incomplete or duplicated for the current CLIF census"
        )
    if current is None:
        current = clif_now.running_at_cut(clif, {sid: cuts[sid] for sid in ids})
    if set(current) != set(ids):
        raise ContextUnavailable(
            "Current CLIF observations do not match the selected census"
        )
    pending = forecast_state == aggregate.PENDING
    if pending:
        df = df.with_columns(
            pl.lit(float("nan")).alias(f"{t}_rep_score")
            for t in aggregate.probe_tokens()
        )
        provenance = {
            "model": None,
            "weights_sha256": None,
            "scoring": "pending-model",
            "unit_counts": None,
            "cut_semantics": "per-stay winnower cut; shared research replay clock",
        }
    if not provenance:
        raise ContextUnavailable("Ready context requires verified model provenance")
    model_name = provenance["model"]
    source = {
        "kind": ward["source"],
        "label": ward["label"],
        "dataset_version": dataset_version,
    }
    vocab = yaml.safe_load((root / "vocab.yaml").read_text())["lookup"]
    words = {int(i): w for w, i in vocab.items()}
    cut = aggregate.parse_cut(cut_time)
    published = aggregate.now_iso()
    # build_forecast emits a yardstick diagnostic; stdout is a JSON receipt only.
    with contextlib.redirect_stdout(io.StringIO()):
        forecast = aggregate.build_forecast(
            df,
            model_name,
            beds=df.height,
            cut_time=cut_time,
            tz=tz,
            ward=ward,
            demo_clock_hours=demo_clock_hours,
            clif=current,
            forecast_state=forecast_state,
            baseline=baseline,
            capacity=capacity,
            unit_name=unit_name,
        )
    demographics = rooms.demographics(clif, ids)
    if set(demographics) != set(ids):
        raise ContextUnavailable("Selected CLIF hospitalizations are incomplete")
    display_names, _ = fake_names.names_for(
        names, room_of, {sid: demo["sex"] for sid, demo in demographics.items()}
    )
    entries = rooms.room_entries(
        df,
        room_of,
        rooms.past_events(root, ids, words),
        cut,
        published,
        demographics,
        current,
        pending=pending,
        names=display_names,
    )
    # A missing probability is not a zero. Partial task coverage also leaves the
    # unit task unknown, and any missing support makes the combined forecast
    # unknown; observed support counts remain available.
    tab = aggregate.patient_table(df, clif=current)
    unknown = {
        "available": False,
        "p10": None,
        "p50": None,
        "p90": None,
        "expected": None,
    }
    for task, (team, _) in aggregate.RESOURCES_REP.items():
        if tab["skipped"][task].any():
            forecast["resources"][task] = {"team": team, **unknown}
    missing_support = False
    for support, task in aggregate.SUPPORT_RESOURCE.items():
        if tab["skipped"][task].any():
            forecast["life_support"]["expected_by"][support] = dict(unknown)
            missing_support = True
    if missing_support:
        forecast["life_support"]["expected_new_patients"] = dict(unknown)
        forecast["yardstick"] = None
    for entry in entries:
        if not pending and any(entry["skipped"][s] for s in aggregate.SUPPORTS):
            entry["any_life_support"] = None
            entry["level"] = "unavailable"
    forecast["check_first"] = [] if pending else aggregate.check_first(df, tab, room_of)
    unavailable_rooms = {e["room"] for e in entries if e["level"] == "unavailable"}
    forecast["check_first"] = [
        e for e in forecast["check_first"] if e["room"] not in unavailable_rooms
    ]
    for entry in entries:
        entry["present"] = True
    active = {entry["room"] for entry in entries}
    for slot in sorted(room_of.values()):
        if slot not in active:
            entries.append(
                {
                    "room": slot,
                    "present": False,
                    "age": None,
                    "sex": None,
                    "updated_at": published,
                    "cut_time": cut.isoformat(timespec="seconds"),
                    "window": aggregate.window_for(cut),
                    "scope": "room",
                    "on_now": {s: None for s in (*aggregate.SUPPORTS, "ecmo")},
                    "on_life_support": None,
                    "stopped_before_cut": {s: None for s in aggregate.SUPPORTS},
                    "skipped": {
                        s: True for s in (*aggregate.SUPPORTS, "icu_departure", "death")
                    },
                    "p": {
                        s: None for s in (*aggregate.SUPPORTS, "icu_departure", "death")
                    },
                    "any_life_support": None,
                    "level": None,
                    "out": False,
                    "past_12h": [],
                }
            )
    entries.sort(key=lambda entry: entry["room"])
    cohort_id = hashlib.sha256(
        json.dumps(
            {
                "source": source,
                "roster": sorted((r, sid) for sid, r in room_of.items()),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    identity = {"snapshot_id": str(uuid.uuid4()), "cohort_id": cohort_id}
    forecast.update(identity)
    context = {
        "schema_version": 1,
        **identity,
        "published_at": published,
        "source": source,
        "roster_size": 25,
        "clock_mode": "research_replay",
        "forecast_state": forecast_state,
        "forecast": forecast,
        "rooms": {
            "made_at": published,
            "ward": ward,
            "rooms": entries,
            "forecast_state": forecast_state,
            "on_now_source": "clif",
            "dropped": 25 - len(ids),
            **identity,
        },
        "provenance": provenance,
    }
    if any("name" in entry for entry in entries):
        context["rooms"]["names"] = "fictional"
    _validate_context(context)
    return context


def write_context(out, context):
    """Atomically replace a restricted snapshot; failure preserves the prior one."""
    out = pathlib.Path(out)
    _validate_context(context)
    raw = json.dumps(context, ensure_ascii=False, allow_nan=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=out.parent, prefix=".context-", delete=False
        ) as f:
            name = f.name
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, out)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return {
        "published": True,
        "roster_size": 25,
        "rooms_written": len(context["rooms"]["rooms"]),
    }


def publish_context(
    *,
    tokenized_output,
    model,
    roster,
    clif,
    out,
    cut_time,
    tz="America/Chicago",
    real_ward=False,
    dataset_version=None,
    demo_clock_hours=0,
    names=None,
    unit_name=None,
):
    """Strict trained-model publisher; no inference, training or fitting occurs."""
    from app import aggregate

    room_of = read_roster(roster)
    ward = aggregate.check_ward(room_of, real_ward)
    if (
        len(room_of) != 25
        or not math.isfinite(demo_clock_hours)
        or demo_clock_hours < 0
    ):
        raise ContextUnavailable(
            "A stable 25-room roster and valid replay state are required"
        )
    # a roster stay that has ended keeps its room slot but has no current scores
    _, ids = active_census(pathlib.Path(clif), room_of, demo_clock_hours)
    df, provenance, _ = verified_scores(tokenized_output, model, ids, demo_clock_hours)
    context = build_context(
        root=tokenized_output,
        df=df,
        room_of=room_of,
        clif=clif,
        cut_time=cut_time,
        ward=ward,
        forecast_state=aggregate.READY,
        provenance=provenance,
        demo_clock_hours=demo_clock_hours,
        tz=tz,
        dataset_version=dataset_version,
        names=names,
        unit_name=unit_name,
    )
    return write_context(out, context)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for name in ("tokenized-output", "model", "roster", "clif", "out"):
        ap.add_argument(f"--{name}", type=pathlib.Path, required=True)
    ap.add_argument("--cut-time", required=True, help="replay clock with UTC offset")
    ap.add_argument("--tz", default="America/Chicago")
    ap.add_argument("--real-ward", action="store_true")
    ap.add_argument("--dataset-version")
    ap.add_argument("--names", help="fictional names file or fake; default off")
    ap.add_argument("--unit-name", default=None)
    ap.add_argument("--demo-clock-hours", type=float, default=0)
    args = ap.parse_args(argv)
    try:
        receipt = publish_context(**vars(args))
    except ContextUnavailable as e:
        ap.exit(2, f"{e}\n")
    except (Exception, SystemExit):
        # Source parser/model errors may contain row values or private paths.
        ap.exit(2, "Context publication failed; check restricted source artifacts\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    main()
