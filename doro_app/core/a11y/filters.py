"""Filtering and redaction for sampled a11y elements (Phase 1d).

Two privacy/noise gates applied before serialization:

- ``is_blacklisted`` — suppress the entire tree for sensitive apps
  (password managers, mail clients, banking) by foreground-window class.
- ``filter_elements`` — drop non-interactable nodes and mask the value of
  any password field, even for non-blacklisted apps.
"""

from __future__ import annotations

from .models import A11yElement

# Roles the LLM can act on. Everything else (panes, groups, static text,
# decorative containers) is dropped to keep the block compact.
INTERACTABLE_ROLES = frozenset(
    {"button", "link", "input", "menuitem", "combobox", "checkbox", "radiobutton", "tab"}
)

REDACTED_VALUE = "[redacted-password]"


def is_blacklisted(window_class: str | None, blacklist: tuple[str, ...]) -> bool:
    """Return True if ``window_class`` matches any blacklist entry.

    Case-insensitive substring match: a blacklist of ``("KeePass",)`` blocks
    both ``KeePassXC`` and ``Qt.KeePass.Window``. We err toward over-blocking
    sensitive apps rather than risk leaking their contents.
    """
    if not window_class:
        return False
    lowered = window_class.strip().lower()
    if not lowered:
        return False
    return any(entry.strip().lower() in lowered for entry in blacklist if entry.strip())


def filter_elements(
    elements: list[A11yElement],
    *,
    share_input_values: bool = False,
) -> list[A11yElement]:
    """Keep only interactable elements; mask password-field values.

    When ``share_input_values`` is False (the default), drop the
    ``value`` of every non-password input too. The LLM still sees that
    an editable field exists, where it is, and what it's named — but
    not what the user typed (URL bar contents, search query, half-
    drafted message). Users who knowingly want the assistant to act on
    input contents opt in via the settings dialog.
    """
    result: list[A11yElement] = []
    for el in elements:
        if el.role not in INTERACTABLE_ROLES:
            continue
        if el.is_password:
            el = A11yElement(
                role=el.role,
                name=el.name,
                x=el.x,
                y=el.y,
                width=el.width,
                height=el.height,
                value=REDACTED_VALUE,
                is_password=True,
            )
        elif el.value is not None and not share_input_values:
            el = A11yElement(
                role=el.role,
                name=el.name,
                x=el.x,
                y=el.y,
                width=el.width,
                height=el.height,
                value=None,
                is_password=False,
            )
        result.append(el)
    return result
