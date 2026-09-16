from __future__ import annotations

from typing import Any

from ..config import Settings
from ..errors import GmpError
from ..models import Action, ActionResult


class Provider:
    name = ""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def doctor(self) -> dict[str, Any]:
        raise NotImplementedError

    def who(self, email: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def apply(self, action: Action, *, execute: bool) -> ActionResult:
        raise NotImplementedError

    def apply_many(self, actions: list[Action], *, execute: bool) -> list[ActionResult]:
        return [self.apply(action, execute=execute) for action in actions]

    def blocked(self, action: Action, message: str, next_step: str, *, execute: bool) -> ActionResult:
        return ActionResult(
            action=action,
            status="blocked",
            dry_run=not execute,
            message=message,
            next_step=next_step,
        )

    def planned(self, action: Action, message: str, next_step: str | None = None) -> ActionResult:
        return ActionResult(
            action=action,
            status="planned",
            dry_run=True,
            message=message,
            next_step=next_step,
        )

    def wrap_error(self, exc: Exception, fallback: str) -> GmpError:
        text = str(exc)
        if isinstance(exc, GmpError):
            return exc
        return GmpError(f"{self.name} 失败：{text}", fallback)
