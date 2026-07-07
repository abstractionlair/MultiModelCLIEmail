from __future__ import annotations

import copy
import itertools
from typing import Callable

from core_types import Candidate, Context


def mutate_prompt_suffix(suffix: str) -> Callable[[Candidate], Candidate]:
    def _mut(c: Candidate) -> Candidate:
        nc = copy.deepcopy(c)
        if nc.context.prompt:
            nc.context.prompt = nc.context.prompt + " " + suffix
        else:
            nc.context.prompt = suffix
        nc.id = f"{c.id}+suf"
        return nc
    return _mut


def toggle_param(key: str, values: list) -> Callable[[Candidate], Candidate]:
    def _mut(c: Candidate) -> Candidate:
        nc = copy.deepcopy(c)
        cur = nc.context.params.get(key)
        try:
            idx = values.index(cur)
            nxt = values[(idx + 1) % len(values)]
        except ValueError:
            nxt = values[0]
        nc.context.params[key] = nxt
        nc.id = f"{c.id}+{key}={nxt}"
        return nc
    return _mut
