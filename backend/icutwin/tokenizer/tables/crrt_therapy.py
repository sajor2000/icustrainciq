#!/usr/bin/env python3

"""
crrt pipeline -> tables/crrt_therapy.parquet

1. read       clif_crrt_therapy through clifpy io_polars
2. convert    any charted row counts
3. tokens     CRRT//crrt_init at the stay's first charted recorded_dttm only
4. table      stay checks, fixed columns
"""

from icutwin.tokenizer.helpers import ClifData, first_only

TABLE = "crrt_therapy"
TABLES = (TABLE,)


def build(clif: ClifData) -> list:
    return [  # 1-4, then one token per stay
        t if t is None else first_only(t)
        for t in (clif.categorical(c) for c in clif.of("categorical", TABLE))
    ]
