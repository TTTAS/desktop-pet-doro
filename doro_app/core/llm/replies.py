"""Reply schemas: what a model may answer for a character reply.

A character reply is forgiving: an unknown state or a malformed move is
dropped instead of failing the whole reply, so Doro still speaks. Only an
empty line where Doro should speak counts as a broken reply.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)

from .zh import to_traditional


class DirectionalMove(BaseModel):
    """往四個方向之一走一段。"""

    dir: Literal["left", "right", "up", "down"] = Field(description="走路方向")
    distance: float = Field(gt=0, le=600, description="走多遠（像素，1～600）")

    @property
    def vector(self) -> tuple[int, int]:
        return _VECTORS[self.dir]


_VECTORS = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}


def character_reply_model(
    state_keys: list[str], *, decide_worth_saying: bool = False
) -> type[BaseModel]:
    """Build the reply schema for one call; ``state`` is limited to ``state_keys``.

    With ``decide_worth_saying`` the model first decides whether the situation
    is worth speaking about (開口判斷); when it isn't, ``line`` may stay empty.
    """
    allowed = tuple(dict.fromkeys(k for k in state_keys if k))
    state_type: Any = Literal[allowed] if allowed else str  # type: ignore[valid-type]

    fields: dict[str, Any] = {}
    if decide_worth_saying:
        fields["worth_saying"] = (
            bool,
            Field(description="這個情境值不值得開口；不值得就 false，line 留空"),
        )
    fields["state"] = (
        state_type | None,
        Field(default=None, description="Doro 的狀態 key，只能從列舉挑；沒有適合的填 null"),
    )
    fields["line"] = (str, Field(default="", description="Doro 說的台詞，繁體中文"))
    fields["move"] = (
        DirectionalMove | None,
        Field(default=None, description="說話前先走一段；不需要走就填 null"),
    )

    def _known_state(cls, value: Any) -> Any:
        return value if value in allowed else None

    def _usable_move(cls, value: Any) -> Any:
        if value is None or isinstance(value, DirectionalMove):
            return value
        try:
            return DirectionalMove.model_validate(value)
        except ValidationError:
            return None

    def _clean_line(cls, value: str) -> str:
        return to_traditional(value.strip())

    def _speaks_with_line(self):
        if getattr(self, "worth_saying", True) and not self.line:
            raise ValueError("要開口時 line 不能是空的")
        return self

    validators: dict[str, Any] = {
        "_move": field_validator("move", mode="before")(_usable_move),
        "_line": field_validator("line", mode="after")(_clean_line),
        "_speaks": model_validator(mode="after")(_speaks_with_line),
    }
    if allowed:
        validators["_state"] = field_validator("state", mode="before")(_known_state)

    name = "PresenceReply" if decide_worth_saying else "CharacterReply"
    # 解析時缺欄位就用預設值（寬容），但給模型看的 schema 把每個欄位都列為必填，
    # 讓伺服器端的約束解碼一定會產生完整結構。
    config = ConfigDict(json_schema_serialization_defaults_required=True)
    return create_model(name, __config__=config, __validators__=validators, **fields)
