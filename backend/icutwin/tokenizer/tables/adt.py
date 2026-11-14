#!/usr/bin/env python3

"""
adt pipeline -> tables/adt.parquet

1. read       clif_adt through clifpy io_polars
2. convert    location_category as charted, at in_dttm
3. tokens     ADT//TRANSFER_IN//<location> (mapped, unknown -> other)
4. table      stay checks, fixed columns
"""

from icutwin.tokenizer.helpers import ClifData

TABLE = "adt"
TABLES = (TABLE,)


def build(clif: ClifData) -> list:
    return [clif.categorical(c) for c in clif.of("categorical", TABLE)]  # 1-4
