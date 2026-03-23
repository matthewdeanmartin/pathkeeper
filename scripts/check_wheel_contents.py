"""Verify that expected files are present in the built wheel and sdist."""

import sys
import tarfile
import zipfile
from pathlib import Path

REQUIRED_WHEEL_PATHS = [
    "pathkeeper/py.typed",
    "pathkeeper/catalog/known_tools.toml",
]

# In sdist, files live under pathkeeper-<version>/
REQUIRED_SDIST_SUFFIXES = [
    "pathkeeper/py.typed",
    "pathkeeper/catalog/known_tools.toml",
]


def check_wheel(path: Path) -> list[str]:
    errors = []
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        for required in REQUIRED_WHEEL_PATHS:
            if required not in names:
                errors.append(f"  MISSING from wheel: {required}")
    return errors


def check_sdist(path: Path) -> list[str]:
    errors = []
    with tarfile.open(path, "r:gz") as tf:
        names = set(tf.getnames())
        for suffix in REQUIRED_SDIST_SUFFIXES:
            if not any(n.endswith(suffix) for n in names):
                errors.append(f"  MISSING from sdist: {suffix}")
    return errors


def main() -> None:
    dist = Path("dist")
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))

    if not wheels and not sdists:
        print("ERROR: no built artifacts found in dist/ — run `uv build` first")
        sys.exit(1)

    errors = []
    for whl in wheels:
        print(f"Checking wheel: {whl.name}")
        errors.extend(check_wheel(whl))

    for sdist in sdists:
        print(f"Checking sdist: {sdist.name}")
        errors.extend(check_sdist(sdist))

    if errors:
        print("\nFAILED:")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("All required files present.")


if __name__ == "__main__":
    main()
