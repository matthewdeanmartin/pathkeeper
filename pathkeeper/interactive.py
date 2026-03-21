from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import Mapping


MenuHandler = Callable[[Namespace], int]


def run_interactive(dispatch: Mapping[str, tuple[str, Namespace, MenuHandler]]) -> int:
    while True:
        print("pathkeeper v0.1.0")
        print("[1] Inspect")
        print("[2] Doctor")
        print("[3] Backup")
        print("[4] Restore")
        print("[5] Dedupe")
        print("[6] Populate")
        print("[7] Edit")
        print("[8] Schedule status")
        print("[q] Quit")
        choice = input("> ").strip().lower()
        if choice in {"q", "quit"}:
            return 0
        entry = dispatch.get(choice)
        if entry is None:
            print("Unknown selection.")
            continue
        label, namespace, handler = entry
        print(f"\n== {label} ==\n")
        return_code = handler(namespace)
        print(f"\n{label} finished with exit code {return_code}.\n")

