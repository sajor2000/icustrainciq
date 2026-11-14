"""Made-up patient names for the bed board (docs/CONTRACT.md "names").

MIMIC-IV has no names. The demo attaches an invented one to each room so the board
reads like a ward. Two sources, both fictional:

  load(path)             a names file made for one ward (parquet or csv): columns
                         hospitalization_id, first_name, last_name, display_name,
                         name_source ("fictional"). It holds real stay ids, so it
                         stays beside the ward's data and never enters git.
  for_ward(room_of, sex) a seeded generator keyed by ROOM NUMBER (no id needed),
                         sex-aware: the open demo ward and the tests use it
                         (`--names fake`).

Both return {stay id: {"display", "first", "last", "fictional": True}}. A name is
letters, spaces and . , ' - only, at most 40 characters; anything else stops the
run with a count (the value is never printed). Names never go to stdout or a log.
A real deployment would take names from the hospital's ADT feed, not from here.
"""

import hashlib
import pathlib
import re

import polars as pl

HOSP = "hospitalization_id"
SEED = 20261114
MAX_LEN = 40
OK = re.compile(r"[^\W\d_](?:[^\W\d_]|[ .,'-])*", re.UNICODE)
FAKE = "fake"  # `--names fake`: the generator
FIRST_F = (
    "Ana", "Beatriz", "Carmen", "Dalia", "Elena", "Farah", "Grace", "Hana",
    "Ines", "Joan", "Keiko", "Lucia", "Mara", "Nadia", "Olga", "Priya",
    "Rosa", "Sofia", "Tessa", "Uma", "Vera", "Wanda", "Yara", "Zora",
)  # fmt: skip
FIRST_M = (
    "Abel", "Bruno", "Carlos", "Dmitri", "Emil", "Felix", "Gus", "Hugo",
    "Ivan", "Jonas", "Kofi", "Luis", "Marco", "Nils", "Omar", "Pavel",
    "Rafael", "Samir", "Tomas", "Ugo", "Victor", "Walt", "Yusuf", "Zane",
)  # fmt: skip
LAST = (
    "Abara", "Bellweather", "Castellan", "Dunmore", "Eskildsen", "Fairbrook",
    "Galloway", "Hartwell", "Ibarra", "Jennison", "Kessler", "Lindqvist",
    "Marchetti", "Novak", "Okafor", "Pemberton", "Quintero", "Rivera",
    "Sandoval", "Thackeray", "Underhill", "Vasquez", "Whitlock", "Yamada",
    "Zielinski", "Ashcombe", "Brightwater", "Calloway", "Delacroix", "Everhart",
    "Fontaine", "Greenhalgh", "Holloway", "Iverson", "Jaramillo", "Kowalski",
    "Lachance", "Montrose", "Nakamura", "Oyelaran", "Prescott", "Quimby",
    "Rosenthal", "Stavros", "Tennyson", "Uribe", "Valdez", "Winterbourne",
    "Yilmaz", "Zamora",
)  # fmt: skip


def valid(s) -> bool:
    """a string that may be shown as (part of) a name"""
    return isinstance(s, str) and 0 < len(s) <= MAX_LEN and OK.fullmatch(s) is not None


def entry(first: str, last: str, display: str | None = None) -> dict:
    return {
        "display": display or f"{last}, {first[:1]}.",
        "first": first,
        "last": last,
        "fictional": True,
    }


def _pick(seed: int, room: int, salt: str, n: int) -> int:
    h = hashlib.sha256(f"{seed}:{room}:{salt}".encode()).digest()
    return int.from_bytes(h[:8], "big") % n


def fake_name(room: int, sex: str | None = None, seed: int = SEED) -> dict:
    """the generator's name for one room: the same every run, different last names
    for rooms 1 to 50, a first name that fits the sex ("F" | "M"; else either)"""
    pool = (
        FIRST_F
        if sex == "F"
        else FIRST_M
        if sex == "M"
        else (FIRST_F, FIRST_M)[_pick(seed, room, "sex", 2)]
    )
    shift = _pick(seed, 0, "last", len(LAST))  # one rotation per seed
    last = LAST[(shift + 7 * (int(room) - 1)) % len(LAST)]  # 7 and 50 are coprime
    return entry(pool[_pick(seed, room, "first", len(pool))], last)


def for_ward(
    room_of: dict[str, int], sex_of: dict[str, str | None] | None = None, seed=SEED
) -> dict[str, dict]:
    """generated names for every stay of a room map, keyed by stay id"""
    return {
        sid: fake_name(room, (sex_of or {}).get(sid), seed)
        for sid, room in room_of.items()
    }


def load(path: pathlib.Path) -> dict[str, dict]:
    """a ward's names file -> {stay id: name entry}. Refuses a file whose
    name_source is not "fictional" (real names do not come this way) or that holds a
    string outside the allowed characters: the message has counts only."""
    path = pathlib.Path(path)
    if not path.is_file():
        raise SystemExit(f"--names: {path.name} not found")
    df = (
        pl.read_parquet(path)
        if path.suffix.lower() == ".parquet"
        else pl.read_csv(path, infer_schema=False)
    )
    need = [HOSP, "first_name", "last_name", "display_name", "name_source"]
    lost = [c for c in need if c not in df.columns]
    if lost:
        raise SystemExit(f"--names: {path.name} lacks column(s) {', '.join(lost)}")
    real = df.filter(pl.col("name_source").fill_null("") != "fictional").height
    if real:
        raise SystemExit(
            f'--names: {real} of {df.height} rows are not name_source "fictional": '
            "only invented names are shown"
        )
    out, bad = {}, 0
    for sid, first, last, display in df.select(need[:4]).iter_rows():
        if sid is None or not all(valid(x) for x in (first, last, display)):
            bad += 1
            continue
        out[str(sid)] = entry(first, last, display)
    if bad:
        raise SystemExit(
            f"--names: {bad} of {df.height} rows hold a name that is empty, longer "
            f"than {MAX_LEN} characters or has characters other than letters, "
            "spaces and . , ' -"
        )
    return out


def names_for(
    arg, room_of: dict[str, int], sex_of: dict[str, str | None] | None = None
) -> tuple[dict[str, dict] | None, dict]:
    """the --names argument -> (names by stay id or None, counts for the log):
    nothing given -> no names; "fake" -> the generator; else a names file, where a
    ward stay without a row simply has no name (counted, never listed)"""
    if not arg:
        return None, {"names": "off"}
    if str(arg) == FAKE:
        names = for_ward(room_of, sex_of)
        return names, {"names": "fictional", "named": len(names), "unnamed": 0}
    names = {k: v for k, v in load(pathlib.Path(arg)).items() if k in room_of}
    return names, {
        "names": "fictional",
        "named": len(names),
        "unnamed": len(room_of) - len(names),
    }
