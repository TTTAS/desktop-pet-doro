"""Parse `[mouse:...]` brackets emitted by the LLM.

Phase 1c contract — **only** `[mouse:click]` with no parameters is accepted.

Any form carrying a coordinate (`x=`, `y=`), an alternative button
(`button=`), or a non-`click` action (`double_click`, `drag`, `scroll`, ...)
is rejected. This is a permanent invariant of Phase 1c, not a configuration
choice: the click coordinate is the position Doro stands on at the moment
the wind-up timer expires, so any LLM-provided coordinate is meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MouseBracketParse:
    """Result of `parse_mouse_bracket` — either accepted or rejected with reason."""

    accepted: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> MouseBracketParse:
        return cls(accepted=True, reason="")

    @classmethod
    def reject(cls, reason: str) -> MouseBracketParse:
        return cls(accepted=False, reason=reason)


def parse_mouse_bracket(token: str) -> MouseBracketParse | None:
    """Parse a `[mouse:...]` bracket payload.

    Args:
        token: The inside of the bracket (without the surrounding `[ ]`),
            e.g. ``"mouse:click"`` or ``"mouse:click;x=1;y=1"``.

    Returns:
        ``None`` if the token is not a mouse bracket at all (caller should
        try other parsers). Otherwise a :class:`MouseBracketParse` indicating
        whether the bracket is the one accepted form (`mouse:click` with no
        parameters), or rejected with a human-readable reason.
    """
    raw = (token or "").strip()
    if not raw:
        return None

    parts = [p.strip() for p in raw.split(";") if p.strip()]
    if not parts:
        return None

    header = parts[0]
    if ":" not in header:
        # Tokens like "mouse" alone — still claim it (it's a mouse bracket
        # without an action) so caller doesn't fall through to other parsers.
        if header.lower() == "mouse":
            return MouseBracketParse.reject("missing action; expected mouse:click")
        return None

    prefix, action = header.split(":", 1)
    if prefix.strip().lower() != "mouse":
        return None

    action_norm = action.strip().lower()
    if action_norm != "click":
        return MouseBracketParse.reject(
            f"unsupported mouse action '{action_norm}'; only 'click' is allowed"
        )

    # Reject any parameter form: x=, y=, button=, count=, anything.
    extra_params = parts[1:]
    if extra_params:
        return MouseBracketParse.reject(
            f"mouse:click does not accept parameters; got {extra_params!r}"
        )

    return MouseBracketParse.ok()
