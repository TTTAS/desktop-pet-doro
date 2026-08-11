"""Pure decision for what Doro does when she speaks on her own.

Extracted from ``IdleBehaviorManager._do_speak`` so the canned-vs-LLM choice
is a real, Qt-free seam. The manager stays a thin adapter that gathers the
inputs (a random roll, the mood-picked line, whether an LLM seed exists) and
carries out the returned action.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class IdleAction(Enum):
    SAY_CANNED = auto()   # show the pre-written line in the bubble (no LLM)
    ASK_LLM = auto()      # let the LLM improvise
    MOVE = auto()         # nothing to say — do a small move instead


@dataclass(frozen=True)
class IdleUtterance:
    action: IdleAction
    line: Optional[str] = None


def choose_idle_utterance(
    *,
    roll: float,
    llm_chance: float,
    canned_line: Optional[str],
    has_llm_seed: bool,
) -> IdleUtterance:
    if canned_line is not None and roll >= llm_chance:
        return IdleUtterance(IdleAction.SAY_CANNED, canned_line)
    if has_llm_seed:
        return IdleUtterance(IdleAction.ASK_LLM)
    if canned_line is not None:
        return IdleUtterance(IdleAction.SAY_CANNED, canned_line)
    return IdleUtterance(IdleAction.MOVE)
