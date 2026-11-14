"""the representation probe sees the same 4096-token windows training saw"""

import numpy as np
import polars as pl

from icutwin.model.decoder import ExactPrefix, stay_offsets


def test_offsets_follow_the_stay_order(tmp_path):
    rows = []  # (stay, position, token)
    for stay, n in (("b", 3), ("a", 2)):
        rows += [(stay, p, 10 + p) for p in range(n)]
    pl.DataFrame(
        {
            "hospitalization_id": [r[0] for r in rows],
            "position_id": [r[1] for r in rows],
            "token_id": [r[2] for r in rows],
        }
    ).write_parquet(tmp_path / "tokens_train.parquet")
    res = stay_offsets(tmp_path, "train")
    # the file is read in hospital order: "a" (2 tokens) first, then "b"
    assert res["hospitalization_id"].to_list() == ["a", "b"]
    assert res["start"].to_list() == [0, 2]
    assert res["n"].to_list() == [2, 3]


def test_window_never_reaches_before_the_cut_side():
    ids = np.arange(100)  # token id == absolute offset, so a leak is visible
    stays = pl.DataFrame({"hospitalization_id": ["a"], "start": [0], "n": [100]})
    cuts = pl.DataFrame({"hospitalization_id": ["a"], "cut": [80]})
    ds = ExactPrefix(ids, stays, cuts, width=16)
    item = ds[0]
    assert item["input_ids"].tolist() == list(range(64, 80))
    assert item["position_ids"].tolist() == list(range(16))
    # a cut before the window fills: take from the stay start, no negative index
    cut5 = pl.DataFrame({"hospitalization_id": ["a"], "cut": [5]})
    short = ExactPrefix(ids, stays, cut5, 16)
    assert short[0]["input_ids"].tolist() == list(range(0, 5))
