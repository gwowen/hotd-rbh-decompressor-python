"""CLI for Tantalus PACK→BODY decompression and asset decode."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from hotd_decompress.audio import convert_sounds_to_wav
from hotd_decompress.camera import convert_cameras_to_json
from hotd_decompress.discover import (
    ALL_KINDS,
    DEFAULT_ASSETS_ROOT,
    TYPED_KINDS,
    AssetKind,
    files_for_kinds,
)
from hotd_decompress.event import convert_events_to_json
from hotd_decompress.mesh import convert_meshes_to_obj
from hotd_decompress.piff import decompress_piff, load_piff
from hotd_decompress.rbh import format_bytes, inspect_rbh
from hotd_decompress.sprite import convert_sprites_to_json
from hotd_decompress.texture import convert_textures_to_png

DEFAULT_OUT_ROOT = "decompressed_assets"

FLAG_TO_KIND: dict[str, AssetKind] = {
    "-d": "decompress",
    "--decompress": "decompress",
    "-p": "png",
    "--png": "png",
    "-w": "wav",
    "--wav": "wav",
    "-m": "mesh",
    "--mesh": "mesh",
    "-s": "sprites",
    "--sprites": "sprites",
    "-e": "evt",
    "--evt": "evt",
    "-c": "cam",
    "--cam": "cam",
}

USAGE = f"""Usage:
  uv run hotd-decompress --usage|--help|-h
  uv run hotd-decompress <file.rbh>
  uv run hotd-decompress --decompress|-d <file> [output]
  uv run hotd-decompress --png|-p <file.vmc|file.rbh> [outdir]
  uv run hotd-decompress --wav|-w <file.rbh> [outdir]
  uv run hotd-decompress --mesh|-m <file.rbh> [outdir]
  uv run hotd-decompress --sprites|-s <file.rbh> [outdir]
  uv run hotd-decompress --evt|-e <file.rbh> [outdir]
  uv run hotd-decompress --cam|-c <file.rbh> [outdir]
  uv run hotd-decompress --all|-a [assets_dir] [out_root]
  uv run hotd-decompress --png|-p --all [assets_dir] [out_root]
  uv run hotd-decompress --wav|-w --all [assets_dir] [out_root]
  (same --all form for -d / -m / -s / -e / -c)

Flags:
  --usage, --help, -h
      Print this help and exit.

  (no flag) <file.rbh>
      Inspect an RBHF container (headers, BODY/PACK/RELC summary).
      Default file: assets/evt/allstage/evtALL.rbh

  -d, --decompress <file> [output]
      Expand PACK → BODY (Tantalus LZ) and write a decompressed PIFF.
      Default output: {DEFAULT_OUT_ROOT}/<name>.decomp.<ext>
      With --all (or a directory): packed files under the tree.

  -p, --png <file.vmc|file.rbh> [outdir]
      Export VVTP RGB555 texture pages as PNGs (decompresses PACK if needed).
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_png/
      Note: spr.rbh is sprite metadata only — use .vmc texture banks.
      With --all (or a directory): every .vmc under the tree.

  -w, --wav <file.rbh> [outdir]
      Export digital SFX as unsigned 8-bit mono PCM WAVs @ 11025 Hz.
      Accepts assets/sound/O_*.rbh or gamesnds.rbh (not CD audio).
      For gamesnds, sibling O_*.rbh files resolve external bank refs.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_wav/
      With --all (or a directory): every sound RBH under the tree.

  -m, --mesh <file.rbh> [outdir]
      Export world/CREAT mesh RBHs as Wavefront OBJ + ids.json.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_mesh/
      With --all (or a directory): every world/CREAT RBH under the tree.

  -s, --sprites <file.rbh> [outdir]
      Export sprite metadata bank (spr.rbh) as sprites.json.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_spr/
      With --all (or a directory): every sprite bank under the tree.

  -e, --evt <file.rbh> [outdir]
      Export event script bank as events.json.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_evt/
      With --all (or a directory): every event bank under the tree.

  -c, --cam <file.rbh> [outdir]
      Export camera rail bank as cameras.json.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_cam/
      With --all (or a directory): every camera bank under the tree.

  -a, --all [assets_dir] [out_root]
      Decode every typed asset under assets_dir (default: {DEFAULT_ASSETS_ROOT}/).
      Writes under out_root (default: {DEFAULT_OUT_ROOT}/) using the same
      per-file names as the single-file flags. Combine with a type flag
      (`-p --all`, `--all -w`, …) to limit to that kind. -d --all expands
      packed PIFF only (skips already-unpacked BODY files).

Outputs default under {DEFAULT_OUT_ROOT}/ (assets/ is often read-only)."""


def print_usage(*, to_error: bool = False) -> None:
    out = sys.stderr if to_error else sys.stdout
    print(USAGE, file=out)


def default_out_path(input_path: str, out_root: str = DEFAULT_OUT_ROOT) -> str:
    # Write under decompressed_assets/, not beside the input — assets/ is often read-only.
    base = Path(input_path).name
    dot = base.rfind(".")
    name = f"{base}.decomp" if dot <= 0 else f"{base[:dot]}.decomp{base[dot:]}"
    return str(Path(out_root) / name)


def default_stem_dir(input_path: str, suffix: str, out_root: str = DEFAULT_OUT_ROOT) -> str:
    stem = Path(input_path).stem
    return str(Path(out_root) / f"{stem}_{suffix}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hotd-decompress", add_help=False)
    parser.add_argument("-h", "--help", "--usage", dest="show_usage", action="store_true")
    parser.add_argument("-a", "--all", action="store_true")
    parser.add_argument("-d", "--decompress", action="store_true")
    parser.add_argument("-p", "--png", action="store_true")
    parser.add_argument("-w", "--wav", action="store_true")
    parser.add_argument("-m", "--mesh", action="store_true")
    parser.add_argument("-s", "--sprites", action="store_true")
    parser.add_argument("-e", "--evt", action="store_true")
    parser.add_argument("-c", "--cam", action="store_true")
    parser.add_argument("paths", nargs="*")
    return parser


def _split_rest(rest: list[str]) -> tuple[set[AssetKind], list[str], bool]:
    kinds: set[AssetKind] = set()
    paths: list[str] = []
    batch = False
    for token in rest:
        if token in ("--all", "-a"):
            batch = True
        elif token in FLAG_TO_KIND:
            kinds.add(FLAG_TO_KIND[token])
        elif token.startswith("-"):
            raise ValueError(token)
        else:
            paths.append(token)
    return kinds, paths, batch


def _print_png(input_path: str, out_dir: str, result) -> None:
    print(f"PNG export: {input_path}")
    print(f"  pages: {len(result.pages)}")
    print(f"  size: {result.pages[0].width}x{result.pages[0].height} RGB555")
    print(f"  skipped non-texture chunks: {result.skippedChunks}")
    print(f"  wrote: {Path(out_dir) / 'page_XXXX.png'} ({len(result.written)} files)")


def _print_wav(input_path: str, out_dir: str, result) -> None:
    rate = result.clips[0].sampleRate
    print(f"WAV export: {input_path}")
    print(f"  clips: {len(result.clips)}")
    print(f"  format: 8-bit mono PCM @ {rate} Hz")
    if result.skippedExternal > 0:
        print(f"  skipped external refs (missing sibling O_*.rbh): {result.skippedExternal}")
    print(f"  wrote: {Path(out_dir) / '*.wav'} ({len(result.written)} files)")


def _print_mesh(input_path: str, out_dir: str, result) -> None:
    print(f"Mesh export: {input_path}")
    print(f"  kind: {result.bank.kind}")
    print(f"  ids: {len(result.bank.ids)}")
    print(f"  nodes: {len(result.bank.nodes)}")
    print(f"  wrote: {Path(out_dir) / 'ids.json'} + node_XXXXXX.obj ({len(result.written)} files)")


def _print_sprites(input_path: str, result) -> None:
    print(f"Sprite export: {input_path}")
    print(f"  sprites: {len(result.bank.sprites)}")
    if result.bank.skipped > 0:
        print(f"  skipped null slots: {result.bank.skipped}")
    print(f"  wrote: {result.written[0]}")


def _print_evt(input_path: str, result) -> None:
    scenes = sum(len(s.scenes) for s in result.bank.stages)
    print(f"Event export: {input_path}")
    print(f"  stages: {len(result.bank.stages)}")
    print(f"  scenes: {scenes}")
    print(f"  ops: {result.opCount}")
    print(f"  spawns: {result.spawnCount}")
    print(f"  camALL binds: {result.railBindCount}")
    if result.undecodedWords > 0:
        print(f"  undecoded words: {result.undecodedWords}")
    print(f"  wrote: {result.written[0]}")


def _print_cam(input_path: str, result) -> None:
    tracks = sum(len(g.tracks) for g in result.bank.groups)
    print(f"Camera export: {input_path}")
    print(f"  groups: {len(result.bank.groups)}")
    print(f"  tracks: {tracks}")
    print(f"  wrote: {result.written[0]}")


def _print_decompress(input_path: str, output: str, result) -> None:
    print(f"Decompressed: {input_path}")
    print(f"  form: {result.form}")
    print(
        f"  PACK chunks expanded: {result.packedChunks} → "
        f"{format_bytes(result.unpackedBytes)} BODY data"
    )
    tag_counts = Counter(chunk.tag for chunk in result.chunks)
    chunks = ", ".join(f"{n}×{tag}" for tag, n in tag_counts.items())
    print(f"  chunks: {chunks}")
    print(f"  wrote: {output} ({format_bytes(len(result.bytes))})")


def _run_png(input_path: str, out_dir: str, *, empty_ok: bool) -> int:
    result = convert_textures_to_png(input_path, out_dir)
    if not result.pages:
        if empty_ok:
            print(f"PNG skip (no pages): {input_path}")
        else:
            print(
                f"No RGB555 texture pages found in {input_path}.\n"
                "Note: spr.rbh is sprite metadata only — convert .vmc texture banks instead.",
                file=sys.stderr,
            )
        return 1
    _print_png(input_path, out_dir, result)
    return 0


def _run_wav(input_path: str, out_dir: str, *, empty_ok: bool) -> int:
    result = convert_sounds_to_wav(input_path, out_dir)
    if not result.clips:
        if empty_ok:
            print(f"WAV skip (no clips): {input_path}")
        else:
            print(
                f"No sound clips found in {input_path}.\n"
                "Note: use assets/sound/O_*.rbh or gamesnds.rbh (digital SFX, not CD audio).",
                file=sys.stderr,
            )
        return 1
    _print_wav(input_path, out_dir, result)
    return 0


def _run_mesh(input_path: str, out_dir: str) -> int:
    result = convert_meshes_to_obj(input_path, out_dir)
    _print_mesh(input_path, out_dir, result)
    return 0


def _run_sprites(input_path: str, out_dir: str) -> int:
    result = convert_sprites_to_json(input_path, out_dir)
    _print_sprites(input_path, result)
    return 0


def _run_evt(input_path: str, out_dir: str) -> int:
    result = convert_events_to_json(input_path, out_dir)
    _print_evt(input_path, result)
    return 0


def _run_cam(input_path: str, out_dir: str) -> int:
    result = convert_cameras_to_json(input_path, out_dir)
    _print_cam(input_path, result)
    return 0


def _run_decompress(input_path: str, output: str, *, skip_unpacked: bool) -> int:
    piff = load_piff(input_path)
    if skip_unpacked and not any(chunk.tag == "PACK" for chunk in piff.chunks):
        return 1
    result = decompress_piff(piff)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_bytes(result.bytes)
    _print_decompress(input_path, output, result)
    return 0


def _kind_out_path(kind: AssetKind, input_path: str, out_root: str) -> str:
    if kind == "decompress":
        return default_out_path(input_path, out_root)
    suffix = {
        "png": "png",
        "wav": "wav",
        "mesh": "mesh",
        "sprites": "spr",
        "evt": "evt",
        "cam": "cam",
    }[kind]
    return default_stem_dir(input_path, suffix, out_root)


def _run_one(
    kind: AssetKind,
    input_path: str,
    dest: str,
    *,
    batch: bool,
) -> int:
    if kind == "png":
        return _run_png(input_path, dest, empty_ok=batch)
    if kind == "wav":
        return _run_wav(input_path, dest, empty_ok=batch)
    if kind == "mesh":
        return _run_mesh(input_path, dest)
    if kind == "sprites":
        return _run_sprites(input_path, dest)
    if kind == "evt":
        return _run_evt(input_path, dest)
    if kind == "cam":
        return _run_cam(input_path, dest)
    return _run_decompress(input_path, dest, skip_unpacked=batch)


@dataclass
class _BatchCounts:
    ok: int = 0
    skipped: int = 0
    failed: int = 0


def _run_batch(kinds: list[AssetKind], assets_root: str, out_root: str) -> int:
    root = Path(assets_root)
    if not root.is_dir():
        print(f"assets directory not found: {assets_root}", file=sys.stderr)
        return 1

    grouped = files_for_kinds(root, kinds)
    total = sum(len(paths) for paths in grouped.values())
    if total == 0:
        wanted = ", ".join(kinds)
        print(f"No matching assets for {wanted} under {assets_root}", file=sys.stderr)
        return 1

    print(f"Batch: {', '.join(kinds)}")
    print(f"  root: {assets_root}")
    print(f"  out:  {out_root}")

    counts = _BatchCounts()
    for kind in kinds:
        for path in grouped[kind]:
            dest = _kind_out_path(kind, str(path), out_root)
            try:
                rc = _run_one(kind, str(path), dest, batch=True)
            except ValueError as exc:
                print(f"{kind} skip: {path}: {exc}", file=sys.stderr)
                counts.skipped += 1
                continue
            except Exception as exc:
                print(f"{kind} fail: {path}: {exc}", file=sys.stderr)
                counts.failed += 1
                continue
            if rc == 0:
                counts.ok += 1
            else:
                counts.skipped += 1

    print(f"Batch done: {counts.ok} ok, {counts.skipped} skipped, {counts.failed} failed")
    return 1 if counts.failed else 0


def main(argv: list[str] | None = None) -> int:
    # First argv token selects the mode (matches the TypeScript CLI).
    # --all / a directory path turns a type flag into a tree walk.
    args = list(sys.argv[1:] if argv is None else argv)
    mode = args[0] if args else None
    show_usage = mode in ("--usage", "--help", "-h")
    all_mode = mode in ("--all", "-a")
    kind = FLAG_TO_KIND.get(mode) if mode else None

    if show_usage:
        print_usage()
        return 0

    if all_mode:
        try:
            extra_kinds, paths, _batch = _split_rest(args[1:])
        except ValueError as token:
            print(f"Unknown flag: {token}", file=sys.stderr)
            print_usage(to_error=True)
            return 1
        if len(paths) > 2:
            print_usage(to_error=True)
            return 1
        kinds: list[AssetKind] = list(extra_kinds) if extra_kinds else list(TYPED_KINDS)
        kinds = [k for k in ALL_KINDS if k in kinds]
        assets_root = paths[0] if paths else DEFAULT_ASSETS_ROOT
        out_root = paths[1] if len(paths) > 1 else DEFAULT_OUT_ROOT
        return _run_batch(kinds, assets_root, out_root)

    if kind is not None:
        try:
            extra_kinds, paths, batch = _split_rest(args[1:])
        except ValueError as token:
            print(f"Unknown flag: {token}", file=sys.stderr)
            print_usage(to_error=True)
            return 1
        if batch:
            if len(paths) > 2:
                print_usage(to_error=True)
                return 1
            kinds = [k for k in ALL_KINDS if k == kind or k in extra_kinds]
            assets_root = paths[0] if paths else DEFAULT_ASSETS_ROOT
            out_root = paths[1] if len(paths) > 1 else DEFAULT_OUT_ROOT
            return _run_batch(kinds, assets_root, out_root)

        if len(paths) == 0:
            print_usage(to_error=True)
            return 1

        input_path = paths[0]
        if Path(input_path).is_dir():
            if len(paths) > 2:
                print_usage(to_error=True)
                return 1
            out_root = paths[1] if len(paths) > 1 else DEFAULT_OUT_ROOT
            return _run_batch([kind], input_path, out_root)

        dest = paths[1] if len(paths) > 1 else _kind_out_path(kind, input_path, DEFAULT_OUT_ROOT)
        return _run_one(kind, input_path, dest, batch=False)

    path_args = args
    if len(path_args) == 0:
        path_args = ["assets/evt/allstage/evtALL.rbh"]

    summary = inspect_rbh(path_args[0])
    print(summary.description)
    return 0


# argparse is available for tests / embedding; the live CLI matches the TS argv contract.
_PARSER = build_parser()
