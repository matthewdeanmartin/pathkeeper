from __future__ import annotations

from dataclasses import dataclass
from argparse import Namespace
from collections.abc import Callable
from typing import Mapping

from pathkeeper.errors import PathkeeperError


MenuHandler = Callable[[Namespace], int]


@dataclass(frozen=True)
class MenuEntry:
    label: str
    description: str
    namespace: Namespace
    handler: MenuHandler


def _menu_sort_key(item: tuple[str, MenuEntry]) -> tuple[int, int | str]:
    key = item[0]
    if key.isdigit():
        return (0, int(key))
    return (1, key)


def run_interactive(dispatch: Mapping[str, MenuEntry]) -> int:
    while True:
        print("pathkeeper v0.1.0")
        for key, entry in sorted(dispatch.items(), key=_menu_sort_key):
            print(f"[{key}] {entry.label} - {entry.description}")
        print("[q] Quit")
        choice = input("> ").strip().lower()
        if choice in {"q", "quit"}:
            return 0
        selected_entry = dispatch.get(choice)
        if selected_entry is None:
            print("Unknown selection.")
            continue
        print(f"\n== {selected_entry.label} ==\n")
        try:
            return_code = selected_entry.handler(selected_entry.namespace)
        except PathkeeperError as error:
            print(error)
            print()
            continue
        if return_code != 0:
            print(f"\n{selected_entry.label} failed with exit code {return_code}.\n")
        else:
            print()

