"""generative scorer: one config per outcome, so each outcome's samples are its
own (synthetic config only; generation itself needs SGLang on a GPU)"""

from icutwin.scoring.generative import outcome_configs
from icutwin.scoring.quick_sco_re import GenerationConfig


def base(**over):
    return GenerationConfig(
        max_len=100,
        n_samp=2,
        target_event_id=5,
        end_token_ids={9},
        tracked_ids=[5, 6],
        tracked_names=["a", "b"],
        **over,
    )


def test_one_config_per_outcome_tracks_only_that_outcome():
    b = base()
    cfgs = outcome_configs(b, [5, 6])
    assert [c.tracked_ids for c in cfgs] == [[5], [6]]
    assert [c.target_event_id for c in cfgs] == [5, 6]
    assert [c.tracked_names for c in cfgs] == [["a"], ["b"]]
    assert all(c.end_token_ids == {9} for c in cfgs)
    assert all(c.n_samp == 2 and c.max_len == 100 for c in cfgs)
    assert b.tracked_ids == [5, 6]  # the shared config is untouched
