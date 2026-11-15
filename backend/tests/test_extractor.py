"""--shard parts merge back into the {split}_for_inference row order"""

import polars as pl

from icutwin.scoring.extractor import SPLITS, merge_shards


def test_merge_shards_restores_row_order(tmp_path):
    for split in SPLITS:
        rows = list(range(7))
        for k in range(2):  # GPU k took rows k, k+2, ...
            mine = rows[k::2]
            pl.DataFrame(
                {
                    "row": mine,
                    "hospitalization_id": [f"h{r}" for r in mine],
                    "features": [[float(r)] for r in mine],
                }
            ).write_parquet(tmp_path / f"features-{split}-final-{k}of2.parquet")
    merge_shards(tmp_path, "final", 2)
    for split in SPLITS:
        df = pl.read_parquet(tmp_path / f"features-{split}-final.parquet")
        assert df.columns == ["hospitalization_id", "features"]
        assert df["hospitalization_id"].to_list() == [f"h{r}" for r in range(7)]
    assert not list(tmp_path.glob("*of2.parquet"))  # parts removed
