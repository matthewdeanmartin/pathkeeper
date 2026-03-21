from __future__ import annotations

from pathkeeper.core.diff import compute_diff
from pathkeeper.models import EditSessionState, PathDiff


class EditSession:
    def __init__(self, entries: list[str], os_name: str) -> None:
        self._state = EditSessionState(original=list(entries), current=list(entries))
        self._os_name = os_name

    @property
    def entries(self) -> list[str]:
        return list(self._state.current)

    def _checkpoint(self) -> None:
        self._state.history.append(list(self._state.current))

    def add(self, value: str, position: int | None = None) -> None:
        self._checkpoint()
        if position is None:
            self._state.current.append(value)
            return
        index = max(0, min(position, len(self._state.current)))
        self._state.current.insert(index, value)

    def delete(self, index: int) -> None:
        self._checkpoint()
        del self._state.current[index]

    def move(self, index: int, new_position: int) -> None:
        self._checkpoint()
        item = self._state.current.pop(index)
        target = max(0, min(new_position, len(self._state.current)))
        self._state.current.insert(target, item)

    def replace(self, index: int, value: str) -> None:
        self._checkpoint()
        self._state.current[index] = value

    def swap(self, left: int, right: int) -> None:
        self._checkpoint()
        self._state.current[left], self._state.current[right] = self._state.current[right], self._state.current[left]

    def undo(self) -> bool:
        if not self._state.history:
            return False
        self._state.current = self._state.history.pop()
        return True

    def reset(self) -> None:
        self._checkpoint()
        self._state.current = list(self._state.original)

    def diff(self) -> PathDiff:
        return compute_diff(self._state.original, self._state.current, self._os_name)

