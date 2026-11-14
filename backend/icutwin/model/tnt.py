"""
time-to-next-token (TNT) head: a point estimate of log1p(minutes to the next token)
read off the last hidden state, kept non-negative by a softplus so `expm1` never
gives fewer than 0 minutes. Saved beside the model as its own file, so the model
runs as plain Qwen3 on token ids and the head is attached only when a task needs it
"""

import pathlib

import safetensors.torch
import torch as t

FILE = "tnt_head.safetensors"


class TntHead(t.nn.Linear):
    """Linear(hidden, 1) + softplus; a Linear subclass, so the saved file is
    just weight/bias"""

    def __init__(self, hidden_size: int):
        super().__init__(hidden_size, 1)

    def forward(self, hidden: t.Tensor) -> t.Tensor:
        return t.nn.functional.softplus(super().forward(hidden)).squeeze(-1)


def save(head: TntHead, mdl_dir: pathlib.Path):
    safetensors.torch.save_file(
        {k: v.contiguous() for k, v in head.state_dict().items()}, mdl_dir / FILE
    )


def load(mdl_dir: pathlib.Path) -> TntHead:
    state = safetensors.torch.load_file(pathlib.Path(mdl_dir) / FILE)
    head = TntHead(state["weight"].shape[1])
    head.load_state_dict(state)
    return head


def minutes(head: TntHead, hidden: t.Tensor) -> t.Tensor:
    """predicted minutes from each position to the next token"""
    return head(hidden.to(head.weight.dtype)).float().expm1()
