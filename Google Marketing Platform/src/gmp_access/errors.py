from __future__ import annotations


class GmpError(RuntimeError):
    def __init__(self, message: str, next_step: str | None = None, status: int | None = None):
        super().__init__(message)
        self.next_step = next_step
        self.status = status

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"error": str(self)}
        if self.next_step:
            payload["next_step"] = self.next_step
        if self.status is not None:
            payload["status"] = self.status
        return payload


class MutationStateUnknownError(RuntimeError):
    """A remote mutation started, but its final state could not be verified."""
