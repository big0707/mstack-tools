from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Product = Literal["ga", "gtm", "gsc", "ads"]
Op = Literal["grant", "revoke", "set_role", "list"]
ActionStatus = Literal[
    "planned",
    "ok",
    "skipped",
    "blocked",
    "manual_required",
    "pending_acceptance",
    "partial",
    "unknown",
    "error",
]


@dataclass
class Action:
    product: Product
    op: Op
    email: str
    brand: str
    resource_id: str
    resource_name: str
    role: str | None = None
    method: Literal["api", "manual"] = "api"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Action":
        return cls(
            product=payload["product"],
            op=payload["op"],
            email=payload["email"],
            brand=payload["brand"],
            resource_id=payload["resource_id"],
            resource_name=payload["resource_name"],
            role=payload.get("role"),
            method=payload.get("method", "api"),
            details=dict(payload.get("details") or {}),
        )


@dataclass
class ActionResult:
    action: Action
    status: ActionStatus
    dry_run: bool
    message: str
    next_step: str | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "action": self.action.to_dict(),
            "status": self.status,
            "dry_run": self.dry_run,
            "message": self.message,
        }
        if self.next_step:
            payload["next_step"] = self.next_step
        if self.data:
            payload["data"] = self.data
        return payload


@dataclass
class ParsedTask:
    action: str
    emails: list[str]
    brands: list[str]
    products: list[Product]
    preset: str | None
    role: str | None
    all_resources: bool
    missing: list[str]
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
