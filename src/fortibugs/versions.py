"""Helpers for FortiOS version strings."""
from typing import Tuple


def version_key(version: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def branch_of(version: str) -> str:
    return ".".join(version.split(".")[:2])
