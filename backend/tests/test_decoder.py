import numpy as np
import torch as t
from transformers import AutoModelForCausalLM, Gemma4ForCausalLM

from icutwin.model.decoder import Packed, build_model, layer_types, load_config

LOOKUP = {"UNK": 0, "BOS": 1, "EOS": 2, **{f"T{i}": i + 3 for i in range(1197)}}


def test_bolt_layers_every_size():
    for size, (lo, hi) in {
        "s": (9e6, 15e6),
        "m": (25e6, 45e6),
        "l": (55e6, 80e6),
    }.items():
        m = build_model(load_config(None, size=size), LOOKUP)
        types = m.config.layer_types
        assert types[-1] == "full_attention" and types[0] == "sliding_attention"
        assert types.count("full_attention") == -(-len(types) // 6)
        n = sum(p.numel() for k, p in m.named_parameters() if "tnt_head" not in k)
        assert lo < n < hi, (size, n)
    assert layer_types(12, 6)[5] == "full_attention"


def test_no_attention_across_stays():
    m = build_model(load_config(None, size="s"), LOOKUP).eval()
    a, b = t.randint(3, 1200, (1, 10)), t.randint(3, 1200, (1, 7))
    pos = t.cat([t.arange(10), t.arange(7)])[None]
    packed = m(input_ids=t.cat([a, b], 1), position_ids=pos).logits[0, 10:]
    alone = m(input_ids=b, position_ids=t.arange(7)[None]).logits[0]
    assert t.allclose(packed, alone, atol=1e-3)


def test_train_step_with_tnt_and_reload(tmp_path):
    m = build_model(load_config(None, size="s"), LOOKUP)
    ids = t.randint(3, 1200, (2, 32))
    out = m(input_ids=ids, labels=ids, dt=t.rand(2, 32))
    (out.loss + out.tnt_loss).backward()
    assert out.tnt_loss.isfinite()
    final = Gemma4ForCausalLM(m.config)
    final.save_pretrained(tmp_path)
    assert isinstance(AutoModelForCausalLM.from_pretrained(tmp_path), Gemma4ForCausalLM)


def test_each_pass_packed_apart():
    lens = np.random.default_rng(0).integers(1, 40, 200)
    n = int(lens.sum())
    d = Packed(np.arange(n), np.zeros(n, np.float32), lens, 64, seed=1, passes=3)
    one = len(Packed(np.arange(n), np.zeros(n), lens, 64, seed=1).rows)
    passes = [d.rows[i * one : (i + 1) * one] for i in range(3)]
    for p in passes:  # every pass holds every token exactly once
        assert sorted(i for r in p for a, b in r for i in range(a, b)) == list(range(n))
    assert passes[0] != passes[1]  # regrouped each epoch
