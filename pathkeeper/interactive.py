from __future__ import annotations

from dataclasses import dataclass
from argparse import Namespace
from collections.abc import Callable
from typing import Mapping

from pathkeeper.errors import PathkeeperError
from pathkeeper.theme import t

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
        for key, entry in sorted(dispatch.items(), key=_menu_sort_key):
            key_str = t.label(f"[{key}]")
            label_str = t.bold(entry.label)
            desc_str = t.dim(entry.description)
            print(f"  {key_str}  {label_str}  {desc_str}")
        print(f"  {t.label('[q]')}  {t.bold('Quit')}")
        print()
        choice = input(t.prompt("  > ")).strip().lower()
        if choice in {"q", "quit"}:
            return 0
        selected_entry = dispatch.get(choice)
        if selected_entry is None:
            print(t.warn("  Unknown selection."))
            print()
            continue
        print()
        print(t.header(f"  {selected_entry.label}"))
        print(t.dim("  " + "-" * (len(selected_entry.label) + 2)))
        print()
        try:
            return_code = selected_entry.handler(selected_entry.namespace)
        except PathkeeperError as error:
            print(t.error(f"  Error: {error}"))
            print()
            continue
        if return_code != 0:
            print(t.error(f"\n  {selected_entry.label} failed (exit {return_code})."))
        print()
