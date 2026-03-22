# Who is this for?

`pathkeeper` is for people who depend on command-line tools being available and do not want a broken `PATH` to derail their machine.

## Good fits

- developers who install lots of SDKs, CLIs, databases, and shell tooling
- Windows users who have been burned by truncated or clobbered PATH values
- macOS and Linux users who want a single tool to manage a dedicated PATH block safely
- anyone who wants a quick `doctor` command before editing environment settings by hand

## Typical moments to use it

- before installing a large toolchain
- after PATH suddenly stops resolving commands you know are installed
- when your PATH contains duplicates, stale entries, or dead directories
- during machine setup, so you can keep a clean baseline backup

## What it is not

`pathkeeper` is not a general-purpose configuration manager or package manager.

It is focused on one problem: keeping PATH understandable, recoverable, and healthy.
