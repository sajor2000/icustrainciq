#!/usr/bin/env python3

"""
the shared core of the tokenizer; each tables/<step>.py is its own pipeline (read ->
convert -> tokens -> table) built on these, assembly.py joins the tables

- keys and file names
- logger and run configuration (run.yaml <- your config file)
- the fixed token spec (tokens.yaml + tokens/<table>.yaml): schema, validation,
  token labels
- value tokenizers used by several tables: plausibility + bins, categories
- the vocabulary enumerated from the spec
- ClifData: the CLIF tables, read with clifpy io_polars; token_table (the stay
  checks every pipeline ends with); categorical codes
- match_category
"""

import collections
import datetime
import functools
import hashlib
import importlib.resources as resources
import logging
import math
import pathlib
import re
import zoneinfo

import polars as pl
import yaml
from omegaconf import OmegaConf
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from rich.logging import RichHandler

HOSP, PAT = "hospitalization_id", "patient_id"  # CLIF keys; one timeline per stay
SEX = "PATIENT//sex"  # only its mapped values keep a stay
SPLITS = ("train", "tuning", "held_out")
EVENTS = "_events.parquet"  # internal: collate -> tokenize, not an output
TABLES = "tables"  # one tokens file per intermediate table


# ------------------------------------------------------------ logger and config


class Logger(logging.Logger):
    def __init__(self, name: str = "icutwin", level: int = logging.INFO):
        super().__init__(name, level)
        if not self.handlers:
            self.addHandler(RichHandler(show_path=False, markup=False))

    def setLevel(self, level) -> None:
        """This logger is made directly, not through logging.getLogger, so the logging
        manager does not know it and does not clear its level cache: without this, a
        level set after the first message has no effect (a WARNING level meant to keep
        outcome rates out of a log would still let INFO through)."""
        super().setLevel(level)
        self._cache.clear()


class Configurable:
    """
    shipped run.yaml defaults <- optional user file <- non-None keyword args;
    a user file is merged over the defaults rather than replacing
    them, so it only needs the keys it changes
    """

    def __init__(self, config_file: pathlib.Path | str | None = None, **kwargs):
        self.config_file = config_file
        layers = [OmegaConf.load(resources.files("icutwin.config") / "run.yaml")]
        if config_file is not None:
            user = OmegaConf.load(pathlib.Path(config_file).expanduser().resolve())
            unknown = set(user) - set(layers[0])
            if unknown:
                raise ValueError(
                    f"unknown run option(s) {sorted(unknown)}; token definitions "
                    "are fixed and cannot be configured"
                )
            layers.append(user)
        layers.append({k: v for k, v in kwargs.items() if v is not None})
        self.cfg = OmegaConf.merge(*layers)
        if self.cfg.filetype not in ("parquet", "csv"):
            raise ValueError(f"filetype {self.cfg.filetype!r} must be parquet or csv")
        try:
            zoneinfo.ZoneInfo(self.cfg.timezone)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown timezone {self.cfg.timezone!r}")
        self.logger = Logger()


# ------------------------------------------------------------ token spec

SPEC_FILE = "tokens.yaml"
# ELF domain prefixes (github.com/Common-Longitudinal-ICU-data-Format/ELF)
ELF_DOMAINS = {
    "VITAL", "LAB_ORD", "LAB_RES", "MED_CON", "MED_INT", "CODE_STATUS",
    "RESP", "PA", "HOSP", "PATIENT", "ADT", "CRRT", "HOSP_PREV_DX",
}  # fmt: skip
# a level is one token-safe word: no spaces, no "/" (units live in a column)
ELF_TOKEN = re.compile(r"[A-Z_]+(//[A-Za-z0-9_.+-]+){0,4}")


def normalize_key(s) -> str:
    """case/punctuation-insensitive key for matching CLIF category strings"""
    return re.sub(r"[^a-z0-9.+-]", "", str(s).lower())


def snake(s) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Bin(_Strict):
    """one half-open interval (lo, hi]; the first bin also includes lo"""

    label: str
    lo: float
    hi: float


class Continuous(_Strict):
    code: str
    table: str
    value_column: str
    time_column: str
    category_column: str | None = None
    category: str | None = None
    unit: str | None = None
    unit_column: str | None = None
    convert_units: bool = False
    plausible: tuple[float, float]
    reference: tuple[float | None, float | None] | None = None
    edges: list[float]  # bins only, no exact-value tokens
    reviewed: bool
    panel: str | None = None  # mCIDE lab panel / MED_INT group (metadata only)
    where: dict[str, str] = {}  # row filter, e.g. given doses only

    @model_validator(mode="after")
    def _check(self):
        lo, hi = self.plausible
        e = self.edges
        name = self.code
        if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
            raise ValueError(f"{name}: plausible range {self.plausible} invalid")
        if len(e) < 2 or e[0] != lo or e[-1] != hi:
            raise ValueError(f"{name}: edges must start/end at plausible bounds")
        if name.startswith("MED_") and 2 < len(e) < 7:
            raise ValueError(f"{name}: a med is 1 bin (//given) or >= 6 bins")
        if any(b <= a for a, b in zip(e, e[1:])):
            raise ValueError(f"{name}: edges must be strictly increasing")
        if self.reference is not None:
            for b in self.reference:
                if b is not None and b not in e[1:-1]:
                    raise ValueError(
                        f"{name}: reference bound {b} must be an interior edge"
                    )
            rlo, rhi = self.reference
            if rlo is not None and rhi is not None and rlo >= rhi:
                raise ValueError(f"{name}: reference {self.reference} inverted")
        if (self.category is None) != (self.category_column is None):
            raise ValueError(f"{name}: category and category_column go together")
        if bool(self.unit_column) != self.convert_units:
            raise ValueError(f"{name}: unit_column only for converted units")
        return self

    @functools.cached_property
    def bins(self) -> list[Bin]:
        """
        derived labels: L1 just below normal .. Lk most extreme low,
        N1..Nk ascending within normal, H1 just above normal .. Hk most extreme;
        B1..Bk ascending when there is no reference range; one bin is one token,
        `given` for meds, the bare code otherwise
        """
        pairs = list(zip(self.edges, self.edges[1:]))
        if len(pairs) == 1:
            label = "given" if self.code.startswith("MED_") else ""
            return [Bin(label=label, lo=pairs[0][0], hi=pairs[0][1])]
        if self.reference is None:
            return [Bin(label=f"B{i}", lo=a, hi=b) for i, (a, b) in enumerate(pairs, 1)]
        rlo, rhi = self.reference
        below = [p for p in pairs if rlo is not None and p[1] <= rlo]
        above = [p for p in pairs if rhi is not None and p[0] >= rhi]
        normal = [p for p in pairs if p not in below and p not in above]
        return sorted(
            [Bin(label=f"L{i}", lo=a, hi=b) for i, (a, b) in enumerate(below[::-1], 1)]
            + [Bin(label=f"N{i}", lo=a, hi=b) for i, (a, b) in enumerate(normal, 1)]
            + [Bin(label=f"H{i}", lo=a, hi=b) for i, (a, b) in enumerate(above, 1)],
            key=lambda x: x.lo,
        )

    def bin_token(self, label: str) -> str:
        return f"{self.code}//{label}" if label else self.code

    def tokens(self) -> dict[str, str]:
        """token -> human readable interval"""
        lo0 = self.edges[0]
        out = {
            self.bin_token(b.label): (
                f"[{b.lo:g}, {b.hi:g}] {self.unit or ''}"
                if b.lo == lo0
                else f"({b.lo:g}, {b.hi:g}] {self.unit or ''}"
            ).strip()
            for b in self.bins
        }
        return out


class Ordinal(_Strict):
    code: str
    table: str
    category_column: str
    category: str
    value_column: str
    time_column: str
    values: list[int]

    def tokens(self) -> dict[str, str]:
        return {f"{self.code}//{v}": f"== {v}" for v in self.values}


class Categorical(_Strict):
    code: str
    table: str
    column: str
    time_column: str
    mapping: dict[str, str]
    other: bool = True
    ignore: list[str] = []
    flag: bool = (
        False  # presence code (RESP//tracheostomy_initiated): token is the code
    )
    where: dict[str, str] = {}  # row filter, values become trailing levels
    mapped_only: bool = False  # only rows whose value is in mapping (LAB_ORD)
    fallback: str | None = None  # null and unmapped values take this token

    @model_validator(mode="after")
    def _check_fallback(self):
        if self.fallback and (self.other or self.flag):
            raise ValueError(f"{self.code}: fallback needs other: false, no flag")
        return self

    @property
    def presence(self) -> bool:
        """flag + other: any charted row is the token (CRRT//crrt_init)"""
        return self.flag and self.other

    @field_validator("mapping")
    @classmethod
    def _unique_norm(cls, m):
        seen = {}
        for k, v in m.items():
            nk = normalize_key(k)
            if nk in seen and seen[nk] != v:
                raise ValueError(f"mapping keys collide after normalization: {k}")
            seen[nk] = v
        return m

    @functools.cached_property
    def normalized(self) -> dict[str, str]:
        return {normalize_key(k): snake(v) for k, v in self.mapping.items()}

    @property
    def suffix(self) -> str:
        return "".join(f"//{v}" for v in self.where.values())

    def token(self, value: str) -> str:
        return self.code if self.flag else f"{self.code}//{value}{self.suffix}"

    def tokens(self) -> dict[str, str]:
        if self.presence:
            return {self.code: "charted"}
        vals = sorted(
            set(self.normalized.values())
            | ({"other"} if self.other else set())
            | ({self.fallback} if self.fallback else set())
        )
        return {self.token(v): v for v in vals}


class Elixhauser(_Strict):
    """comorbidity flags from the previous stay's discharge codes"""

    code: str
    table: str
    flags: list[str]

    def tokens(self) -> dict[str, str]:
        out = {f"{self.code}//{f}": f"previous stay: {f}" for f in self.flags}
        return out | {f"{self.code}//none": "no previous stay or no comorbidity"}


class TimeCfg(_Strict):
    insert_spacers: bool
    spacers: dict[str, int]
    insert_clocks: bool
    clocks: list[str]

    @field_validator("clocks", mode="before")
    @classmethod
    def _two_digit(cls, v):
        return [f"{int(c):02d}" for c in v]

    @field_validator("spacers")
    @classmethod
    def _increasing(cls, v):
        vals = list(v.values())
        if any(b <= a for a, b in zip(vals, vals[1:])):
            raise ValueError("spacer minutes must be strictly increasing")
        return v


class Reference(_Strict):
    table: str
    start_time: str
    end_time: str


class Spec(_Strict):
    spec_version: int
    clif_version: str
    reference: Reference
    time: TimeCfg
    ordering: list[str]
    continuous: list[Continuous]
    ordinal: list[Ordinal]
    categorical: list[Categorical]
    elixhauser: Elixhauser | None = None

    @model_validator(mode="after")
    def _check(self):
        codes = [e.code for e in self.entries]
        dup = {c for c in codes if codes.count(c) > 1}
        if dup:
            raise ValueError(f"duplicate codes: {sorted(dup)}")
        if any(len(o.split("//")) > 2 for o in self.ordering):
            raise ValueError("ordering keys are one or two code levels")
        missing = {c for c in codes if self.ordering_key(c) is None}
        if missing:
            raise ValueError(f"codes missing from ordering: {sorted(missing)}")
        toks = [t for e in self.entries for t in e.tokens()]
        dup = {t for t in toks if toks.count(t) > 1}
        if dup:
            raise ValueError(f"duplicate tokens: {sorted(dup)[:10]}")
        bad = [t for t in toks if not ELF_TOKEN.fullmatch(t)]
        bad += [t for t in toks if t.split("//")[0] not in ELF_DOMAINS]
        if bad:
            raise ValueError(f"tokens not in ELF format: {sorted(set(bad))[:10]}")
        return self

    def ordering_key(self, code: str) -> str | None:
        """the longest `ordering` entry that is a level-prefix of `code`"""
        parts = code.split("//")
        for k in ("//".join(parts[:2]), parts[0]):
            if k in self.ordering:
                return k
        return None

    @property
    def entries(self):
        e = [*self.continuous, *self.ordinal, *self.categorical]
        return e + ([self.elixhauser] if self.elixhauser else [])

    def time_tokens(self) -> list[str]:
        t = self.time
        return [f"TIME//{k}" for k in t.spacers] + [f"CLCK//{c}" for c in t.clocks]

    def unk_tokens(self) -> list[str]:
        """one per med domain: dose not converted or no bin"""
        med = [e.code for e in self.continuous if e.code.startswith("MED_")]
        return sorted({c.split("//")[0] + "//unk" for c in med})


@functools.cache
def spec_text() -> str:
    """tokens.yaml (global keys) + tokens/<table>.yaml (that table's entries),
    as one yaml"""
    cfg = resources.files("icutwin.config")
    spec = yaml.safe_load((cfg / SPEC_FILE).read_text())
    for f in sorted((cfg / "tokens").iterdir(), key=lambda f: f.name):
        for k, v in yaml.safe_load(f.read_text()).items():
            spec[k] = spec.get(k, []) + v if isinstance(v, list) else v
    return yaml.safe_dump(spec, sort_keys=False)


@functools.cache
def spec_hash() -> str:
    return hashlib.sha256(spec_text().encode()).hexdigest()


@functools.cache
def load_spec() -> Spec:
    """the shipped spec; there is deliberately no way to pass another one (D5)"""
    return Spec.model_validate(yaml.safe_load(spec_text()))


# ------------------------------------------------------------ value tokenizers

# values, edges and bounds all go through float32 and are rounded before
# comparison, so float32 storage (0.3 -> 0.30000001, 35.9444 -> 35.94440079)
# cannot push a value that sits exactly on an edge into the next bin
DECIMALS = 6


def _r(e: pl.Expr) -> pl.Expr:
    return e.cast(pl.Float32).cast(pl.Float64).round(DECIMALS)


# reasons a row produces no token; counted in the QC report (D7)
DROP_REASONS = (
    "null_value",
    "nonfinite",
    "implausible_low",
    "implausible_high",
    "non_integer",
    "not_in_scale",
    "unit_conversion_failed",
    "unknown_category",
    "ignored",
    "unknown_hospitalization",
    "invalid_stay",
    "null_time",
    "after_discharge",
)
# kept rows that are still worth counting
FLAGS = (
    "mapped_to_other",
    "null_to_fallback",
    "clipped_high",
    "clipped_low",
    "value_to_unk",
)
# a med row whose dose has no bin is kept as <DOMAIN>//unk, not dropped
UNK_REASONS = ("null_value", "nonfinite", "implausible_low")
# domains whose values above the plausible max get the top bin, not a drop
CLIP = ("MED_CON//",)
# domains whose values outside the plausible range get the edge bin, not a drop
CLIP_BOTH = ("VITAL//", "LAB_RES//")


def _key_norm(e: pl.Expr) -> pl.Expr:
    """polars twin of spec.normalize_key"""
    return e.cast(pl.String).str.to_lowercase().str.replace_all(r"[^a-z0-9.+-]", "")


def continuous_frames(entries: list[Continuous]):
    """small lookup frames describing every continuous variable's bins"""
    bounds = pl.DataFrame(
        {
            "code": [c.code for c in entries],
            "p_lo": [c.plausible[0] for c in entries],
            "p_hi": [c.plausible[1] for c in entries],
            "unit": [c.unit for c in entries],
        },
        schema={
            "code": pl.String,
            "p_lo": pl.Float64,
            "p_hi": pl.Float64,
            "unit": pl.String,
        },
    ).with_columns(_r(pl.col("p_lo")), _r(pl.col("p_hi")))
    bins = (
        pl.DataFrame(
            [(c.code, b.hi, c.bin_token(b.label)) for c in entries for b in c.bins],
            schema={"code": pl.String, "upper": pl.Float64, "bin_token": pl.String},
            orient="row",
        )
        .with_columns(_r(pl.col("upper")))
        .sort("upper")
    )
    return bounds, bins


def tokenize_continuous(df: pl.LazyFrame, entries: list[Continuous]) -> pl.LazyFrame:
    """
    df needs `code`, `value`; adds `token`, `qc_reason`, `qc_flag` and `unit`
    (the spec unit; values are assumed to be in it); keeps `value` (Float64)
    """
    bounds, bins = continuous_frames(entries)
    df = df.with_columns(
        pl.col("value").cast(pl.Float64, strict=False),
        pl.lit(None, pl.String).alias("qc_flag"),
    ).join(bounds.lazy(), on="code", how="left")

    v = pl.col("value")
    both = pl.any_horizontal(pl.col("code").str.starts_with(d) for d in CLIP_BOTH)
    clip = both | pl.any_horizontal(pl.col("code").str.starts_with(d) for d in CLIP)
    high = clip & v.is_finite() & (_r(v) > pl.col("p_hi"))
    low = both & v.is_finite() & (_r(v) < pl.col("p_lo"))
    df = df.with_columns(
        value_r=pl.when(high)
        .then(pl.col("p_hi"))
        .when(low)
        .then(pl.col("p_lo"))
        .otherwise(_r(v)),
        qc_flag=pl.when(high)
        .then(pl.lit("clipped_high"))
        .when(low)
        .then(pl.lit("clipped_low"))
        .otherwise("qc_flag"),
        qc_reason=pl.when(v.is_null())
        .then(pl.lit("null_value"))
        .when(~v.is_finite())
        .then(pl.lit("nonfinite")),
    ).with_columns(
        qc_reason=pl.when(pl.col("qc_reason").is_not_null())
        .then(pl.col("qc_reason"))
        .when(pl.col("value_r") < pl.col("p_lo"))
        .then(pl.lit("implausible_low"))
        .when(pl.col("value_r") > pl.col("p_hi"))
        .then(pl.lit("implausible_high"))
        .otherwise(None)
    )
    med = pl.col("code").str.starts_with("MED_")
    unk = med & pl.col("qc_reason").is_in(UNK_REASONS)
    df = df.with_columns(
        qc_flag=pl.when(unk).then(pl.lit("value_to_unk")).otherwise("qc_flag"),
        qc_reason=pl.when(unk).then(pl.lit(None, pl.String)).otherwise("qc_reason"),
    )
    is_unk = pl.col("qc_flag") == "value_to_unk"

    ok = (
        df.filter(pl.col("qc_reason").is_null() & ~is_unk.fill_null(False))
        .sort("value_r")
        .join_asof(
            bins.lazy(),
            left_on="value_r",
            right_on="upper",
            by="code",
            strategy="forward",  # smallest upper edge >= value: (lo, hi]
            check_sortedness=False,  # both sides sorted on the key just above
        )
        .rename({"bin_token": "token"})
        .drop("upper")
    )
    unks = df.filter(is_unk).with_columns(  # MED_ only
        token=pl.col("code").str.extract(r"^([A-Z_]+)//") + "//unk"
    )
    bad = df.filter(pl.col("qc_reason").is_not_null()).with_columns(
        token=pl.lit(None, pl.String)
    )
    return pl.concat([ok, unks, bad], how="diagonal_relaxed").drop(
        "p_lo", "p_hi", "value_r"
    )


def tokenize_categorical(df: pl.LazyFrame, cat: Categorical) -> pl.LazyFrame:
    """
    df needs `raw` (the value matched against the spec) and `category_value`
    (the raw CLIF string, kept for audit); adds code/token/qc columns
    """
    mapping = pl.DataFrame(
        {"key": list(cat.normalized), "mapped": list(cat.normalized.values())},
        schema={"key": pl.String, "mapped": pl.String},
    )
    ignore = [normalize_key(k) for k in cat.ignore]
    fb = cat.fallback is not None  # null/unmapped -> fallback token, no drop
    null = pl.col("raw").is_null() | (pl.col("key") == "")
    return (
        df.with_columns(
            key=_key_norm(pl.col("raw")),
            code=pl.lit(cat.code),
            value=pl.lit(None, pl.Float64),
        )
        .join(mapping.lazy(), on="key", how="left")
        .with_columns(
            qc_reason=pl.when(pl.lit(not cat.presence and not fb) & null)
            .then(pl.lit("null_value"))
            .when(pl.col("key").is_in(ignore))
            .then(pl.lit("ignored"))
            .when(pl.col("mapped").is_null() & pl.lit(not cat.other and not fb))
            .then(pl.lit("unknown_category"))
            .otherwise(None),
            qc_flag=pl.when(pl.lit(fb) & null)
            .then(pl.lit("null_to_fallback"))
            .when(
                pl.col("mapped").is_null()
                & pl.lit((cat.other or fb) and not cat.presence)
            )
            .then(pl.lit("mapped_to_other"))
            .otherwise(pl.lit(None, pl.String)),
        )
        .with_columns(
            token=pl.when(pl.col("qc_reason").is_not_null())
            .then(None)
            .otherwise(
                pl.lit(cat.code)
                if cat.flag
                else pl.concat_str(
                    pl.lit(cat.code + "//"),
                    pl.coalesce("mapped", pl.lit(cat.fallback or "other")),
                    pl.lit(cat.suffix),
                )
            )
        )
        .with_columns(
            qc_flag=pl.when(pl.col("qc_reason").is_null()).then(pl.col("qc_flag"))
        )
        .drop("key", "mapped", "raw")
    )


# ------------------------------------------------------------ vocabulary

UNK = "UNK"
SPECIAL = ("BOS", "EOS")


class SpecMismatchError(RuntimeError):
    """a saved vocabulary was built from a different token spec"""


class Vocabulary:
    """UNK is 0; every other word is numbered alphabetically from 1"""

    def __init__(self, spec: Spec | None = None):
        self.spec = spec or load_spec()
        self.descriptions: dict[str, str] = {w: "special" for w in SPECIAL}
        self.descriptions |= {w: "time" for w in self.spec.time_tokens()}
        self.descriptions |= {w: "med dose, no bin" for w in self.spec.unk_tokens()}
        for e in self.spec.entries:
            self.descriptions |= e.tokens()
        words = sorted(w for w in self.descriptions if w != UNK)
        self.lookup: dict[str, int] = {UNK: 0} | {w: i for i, w in enumerate(words, 1)}

    def __len__(self) -> int:
        return len(self.lookup)

    def __contains__(self, word: str) -> bool:
        return word in self.lookup and word != UNK

    def __call__(self, word: str) -> int:
        return self.lookup.get(word, 0)

    def decode(self, ids) -> list[str]:
        inv = {i: w for w, i in self.lookup.items()}
        return [inv.get(int(i), UNK) for i in ids]

    def frame(self) -> pl.DataFrame:
        return pl.DataFrame(
            {"word": list(self.lookup), "token": list(self.lookup.values())},
            schema={"word": pl.String, "token": pl.UInt32},
        )

    def to_yaml(self) -> str:
        return yaml.safe_dump(
            {
                "spec_version": self.spec.spec_version,
                "spec_sha256": spec_hash(),
                "created_dttm": datetime.datetime.now(datetime.UTC)
                .replace(microsecond=0)
                .isoformat(),
                "lookup": self.lookup,
                "descriptions": {
                    w: self.descriptions.get(w, "unknown") for w in self.lookup
                },
            },
            sort_keys=False,
        )

    def save(self, path: pathlib.Path | str):
        path = pathlib.Path(path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_yaml())

    @classmethod
    def load(cls, path: pathlib.Path | str) -> "Vocabulary":
        """reload a saved vocabulary; refuses one built from another spec"""
        data = yaml.safe_load(pathlib.Path(path).expanduser().read_text())
        if data.get("spec_sha256") != spec_hash():
            raise SpecMismatchError(
                f"{path} was built from spec {data.get('spec_sha256', '?')[:12]} "
                f"(v{data.get('spec_version')}); installed spec is "
                f"{spec_hash()[:12]} (v{load_spec().spec_version})"
            )
        vocab = cls()
        if vocab.lookup != data["lookup"]:  # pragma: no cover - same hash
            raise SpecMismatchError(f"{path}: lookup differs from installed spec")
        return vocab


# ------------------------------------------------------------ CLIF data


class ClifData(Configurable):
    """
    the CLIF tables read through clifpy: their folder and timezone, the
    tables and columns that are missing; what every table pipeline shares
    """

    def __init__(self, config_file: pathlib.Path | str | None = None, **kwargs):
        super().__init__(config_file, **kwargs)
        if not self.cfg.clif_path:
            raise ValueError("clif_path is required (folder of clif_<table> files)")
        self.raw_data_home = pathlib.Path(self.cfg.clif_path).expanduser().resolve()
        self.spec = load_spec()
        self.tz = self.cfg.timezone
        self.time_unit = self.cfg.time_unit or "us"
        if self.time_unit not in ("ms", "us", "ns"):
            raise ValueError(f"time_unit={self.time_unit!r} must be ms, us or ns")
        self.reference_frame: pl.LazyFrame | None = None
        self.stays: pl.LazyFrame | None = None  # every stay: end time, valid flag
        self.missing_tables: list[str] = []
        self.missing_columns: dict[str, list[str]] = collections.defaultdict(list)
        self.elix_counts: dict[str, int] = {}  # set by tables/cohort.py

    def of(self, kind: str, table: str) -> list:
        """the spec's continuous / ordinal / categorical entries of one table"""
        return [e for e in getattr(self.spec, kind) if e.table == table]

    # ------------------------------------------------------------ loading

    def read(self, table: str, columns: list[str] | None = None):
        """
        clifpy io_polars reads the table (lazy) and does all timezone work
        (tz-aware -> configured tz, naive -> localized to it); we only drop the
        tz label. With `columns`: only those, or None if one is missing.
        A missing table or column is reported once and its tokens skipped
        """
        from clifpy.utils.io_polars import load_data_polars

        ft = self.cfg.filetype
        if not (self.raw_data_home / f"clif_{table}.{ft}").exists():
            if table not in self.missing_tables:
                self.missing_tables.append(table)
                self.logger.warning(
                    f"table {table!r} not found; its tokens are skipped"
                )
            return None
        df = load_data_polars(table, self.raw_data_home, ft, site_tz=self.tz)
        schema = df.collect_schema()
        bad = [c for c, t in schema.items() if "dttm" in c and t != pl.Datetime]
        if bad:  # e.g. csv strings: we never parse times ourselves
            raise TypeError(f"{table}: clifpy did not read {bad} as datetimes")
        df = df.with_columns(
            pl.col(c).dt.replace_time_zone(None).dt.cast_time_unit(self.time_unit)
            for c, t in schema.items()
            if isinstance(t, pl.Datetime)
        )
        if columns is None:
            return df
        return df.select(columns) if self.has_columns(df, table, columns) else None

    def has_columns(self, df: pl.LazyFrame, table: str, cols) -> bool:
        names = df.collect_schema().names()
        missing = [c for c in cols if c not in names]
        for c in missing:
            if c not in self.missing_columns[table]:
                self.missing_columns[table].append(c)
                self.logger.warning(f"{table}.{c} missing; dependent tokens skipped")
        return not missing

    # ------------------------------------------------------------ reference

    def get_reference_frame(self) -> pl.LazyFrame:
        if self.reference_frame is None:
            ref = self.spec.reference
            df = self.read(ref.table)
            if df is None:
                raise FileNotFoundError(f"required table {ref.table!r} not found")
            df = df.with_columns(pl.col(HOSP).cast(pl.String)).unique(
                subset=[HOSP], keep="first"
            )
            # discharge before admission: the whole stay is removed
            valid = ~(pl.col(ref.end_time) < pl.col(ref.start_time)).fill_null(False)
            # sex not male/female: all of the patient's stays are removed
            sex = next(
                (c for c in self.of("categorical", "patient") if c.code == SEX), None
            )
            pat = sex and self.read("patient", [PAT, sex.column])
            if pat is not None:
                ok = pat.filter(
                    _key_norm(pl.col(sex.column)).is_in(list(sex.normalized))
                ).select(PAT, _sex_ok=pl.lit(True))
                df = df.join(ok.unique(PAT), on=PAT, how="left")
                n = df.filter(valid & pl.col("_sex_ok").is_null()).select(pl.len())
                self.logger.info(
                    f"{n.collect().item()} stays dropped: sex not male/female"
                )
                valid = valid & pl.col("_sex_ok").fill_null(False)
            self.stays = df.select(HOSP, _end=ref.end_time, _valid=valid)
            self.reference_frame = df.filter(valid).drop("_sex_ok", strict=False)
        return self.reference_frame

    def token_table(self, df: pl.LazyFrame, time: str) -> pl.LazyFrame:
        """
        last step of every table pipeline: the fixed columns of
        tables/<step>.parquet; rows of unknown or invalid stays and rows after
        discharge get a qc_reason (no future info past the outcome)
        """
        names = df.collect_schema().names()
        df = df.with_columns(
            pl.lit(None, pl.String).alias(c)
            for c in ("unit", "category_value")
            if c not in names
        )
        self.get_reference_frame()
        return (
            df.with_columns(pl.col(HOSP).cast(pl.String))
            .rename({time: "time"} if time != "time" else {})
            .join(self.stays, on=HOSP, how="left")
            .with_columns(
                qc_reason=pl.when(pl.col("_valid").is_null())
                .then(pl.lit("unknown_hospitalization"))
                .when(~pl.col("_valid"))
                .then(pl.lit("invalid_stay"))
                .when(pl.col("qc_reason").is_not_null())
                .then(pl.col("qc_reason"))
                .when(pl.col("time").is_null())
                .then(pl.lit("null_time"))
                .when(pl.col("time") > pl.col("_end"))
                .then(pl.lit("after_discharge"))
            )
            .with_columns(
                token=pl.when(pl.col("qc_reason").is_null()).then(pl.col("token"))
            )
            .select(
                HOSP,
                pl.col("time").cast(pl.Datetime(self.time_unit)),
                "code",
                "token",
                pl.col("value").cast(pl.Float64),
                pl.col("unit").cast(pl.String),
                pl.col("category_value").cast(pl.String),
                "qc_reason",
                "qc_flag",
            )
        )

    def categorical(self, cat, df: pl.LazyFrame | None = None):
        """
        one categorical code: read (unless a pipeline passes its prepared
        rows), spec values -> tokens (mapping, other / fallback, ignore)
        """
        ref = self.spec.reference
        cols = [HOSP, cat.time_column, cat.column, *cat.where]
        if df is None:
            df = (
                self.get_reference_frame()
                if cat.table == ref.table
                else self.read(cat.table, cols)
            )
        if df is None or not self.has_columns(df, cat.table, cols):
            return None
        for k, v in cat.where.items():  # e.g. given doses only
            df = df.filter(_key_norm(pl.col(k)) == normalize_key(v))
        if cat.mapped_only:  # out-of-spec values are out of scope, not drops
            keys = [normalize_key(k) for k in cat.mapping]
            df = df.filter(_key_norm(pl.col(cat.column)).is_in(keys))
        raw = pl.col(cat.column)
        dtype = df.collect_schema()[cat.column]
        if dtype == pl.Boolean or dtype.is_numeric():
            # booleans / 1.0 floats -> "1"/"0" so they meet the spec's keys
            raw = raw.cast(pl.Float64, strict=False).round(0).cast(pl.Int64)
        df = df.select(
            HOSP,
            cat.time_column,
            raw.alias("raw"),
            pl.col(cat.column).cast(pl.String).alias("category_value"),
        )
        if cat.table not in (ref.table, "patient") and not cat.presence:
            df = df.filter(pl.col("raw").is_not_null())
        return self.token_table(tokenize_categorical(df, cat), cat.time_column)


# ------------------------------------------------------------ shared by table pipelines


def first_only(df: pl.LazyFrame) -> pl.LazyFrame:
    """one token per stay: later token rows become `ignored`"""
    ok = pl.col("token").is_not_null()
    first = ok & (ok.cast(pl.Int32).cum_sum().over(HOSP, order_by="time") == 1)
    return df.with_columns(
        qc_reason=pl.when(ok & ~first).then(pl.lit("ignored")).otherwise("qc_reason"),
        token=pl.when(first).then("token"),
    )


def match_category(df: pl.LazyFrame, entries: list, column: str) -> pl.LazyFrame:
    """
    keep the rows whose `column` is a spec category and add its `code`;
    matching ignores case and punctuation (normalize_key)
    """
    codes = pl.LazyFrame(
        {
            "_key": [normalize_key(e.category) for e in entries],
            "code": [e.code for e in entries],
        }
    )
    return (
        df.with_columns(_key=_key_norm(pl.col(column)))
        .join(codes, on="_key", how="inner")
        .drop("_key")
    )


def convert_doses(
    clif: "ClifData", df: pl.LazyFrame, entries: list
) -> pl.LazyFrame | None:
    """
    used by both med pipelines: the spec meds of `df`, doses converted by
    clifpy to each med's spec unit; adds `code`, med_dose_converted and
    `converted_ok` (raw med_dose_unit kept), or None without spec meds
    """
    from clifpy.utils.unit_converter import convert_dose_units_by_med_category

    e0 = entries[0]
    cat = e0.category_column
    # spec meds only, spelled as in the spec (clifpy's preferred_units keys)
    cat_of = {normalize_key(e.category): e.category for e in entries}
    meds = (
        df.select(HOSP, e0.time_column, cat, e0.value_column, e0.unit_column)
        .with_columns(_key=_key_norm(pl.col(cat)))
        .filter(pl.col("_key").is_in(list(cat_of)))
        .with_columns(
            pl.col("_key").replace_strict(cat_of).alias(cat),
            pl.col(e0.value_column).cast(pl.Float64),
            pl.col(e0.unit_column).cast(pl.String),
            pl.col(HOSP).cast(pl.String),
        )
        .drop("_key")
        .collect()
    )
    if meds.height == 0:
        return None
    present = set(meds[cat].unique())
    preferred = {e.category: e.unit for e in entries if e.category in present}
    weights = clif.read(
        "vitals", [HOSP, "recorded_dttm", "vital_category", "vital_value"]
    )
    if weights is not None:
        weights = (
            weights.filter(pl.col("vital_category") == "weight_kg")
            .with_columns(
                pl.col(HOSP).cast(pl.String), pl.col("vital_value").cast(pl.Float64)
            )
            .collect()
            .to_pandas()
        )
    converted, _ = convert_dose_units_by_med_category(
        meds.to_pandas(),
        vitals_df=weights,
        preferred_units=preferred,
        override=True,
        id_name=HOSP,
    )
    code_of = {e.category: e.code for e in entries}
    unit_of = {e.category: e.unit for e in entries}
    conv = (
        pl.from_pandas(converted)
        .lazy()
        .with_columns(
            code=pl.col(cat).replace_strict(code_of, default=None),
            _want=pl.col(cat).replace_strict(unit_of, default=None),
        )
    )
    ok = (pl.col("_convert_status") == "success") & (
        pl.col("med_dose_unit_converted") == pl.col("_want")
    )
    return conv.with_columns(converted_ok=ok.fill_null(False))
