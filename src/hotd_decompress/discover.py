"""Walk an assets tree and classify PIFF files by decode kind."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

type AssetKind = Literal["decompress", "png", "wav", "mesh", "sprites", "evt", "cam"]

TYPED_KINDS: tuple[AssetKind, ...] = ("png", "wav", "mesh", "sprites", "evt", "cam")
ALL_KINDS: tuple[AssetKind, ...] = ("decompress",) + TYPED_KINDS

ASSET_SUFFIXES = {".rbh", ".vmc"}
DEFAULT_ASSETS_ROOT = "assets"


def list_asset_files(root: Path) -> list[Path]:
    """Sorted `.rbh` / `.vmc` files under root (case-insensitive suffix)."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in ASSET_SUFFIXES:
            files.append(path)
    files.sort(key=lambda p: str(p).replace("\\", "/").lower())
    return files


def matches_kind(path: Path, kind: AssetKind) -> bool:
    suffix = path.suffix.lower()
    name = path.name.lower()
    stem = path.stem.lower()
    parent = path.parent.name.lower()

    if kind == "decompress":
        return suffix in ASSET_SUFFIXES
    if kind == "png":
        return suffix == ".vmc"
    if kind == "wav":
        if suffix != ".rbh":
            return False
        return parent == "sound" or name == "gamesnds.rbh" or name.startswith("o_")
    if kind == "mesh":
        return suffix == ".rbh" and (stem.startswith("world") or stem.startswith("creat"))
    if kind == "sprites":
        return name == "spr.rbh" or (suffix == ".rbh" and parent == "sprite")
    if kind == "evt":
        return suffix == ".rbh" and (stem.startswith("evt") or parent == "evt")
    if kind == "cam":
        return suffix == ".rbh" and (stem.startswith("cam") or parent == "cam")
    return False


def files_for_kinds(
    root: Path,
    kinds: tuple[AssetKind, ...] | list[AssetKind],
) -> dict[AssetKind, list[Path]]:
    """Map each requested kind to matching files (a file may appear in several kinds)."""
    files = list_asset_files(root)
    return {kind: [p for p in files if matches_kind(p, kind)] for kind in kinds}
