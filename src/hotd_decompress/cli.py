"""CLI for Tantalus PACK→BODY decompression and asset decode."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from hotd_decompress.audio import convert_sounds_to_wav
from hotd_decompress.camera import convert_cameras_to_json
from hotd_decompress.event import convert_events_to_json
from hotd_decompress.mesh import convert_meshes_to_obj
from hotd_decompress.piff import decompress_piff_file
from hotd_decompress.rbh import format_bytes, inspect_rbh
from hotd_decompress.sprite import convert_sprites_to_json
from hotd_decompress.texture import convert_textures_to_png

DEFAULT_OUT_ROOT = "decompressed_assets"

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

Flags:
  --usage, --help, -h
      Print this help and exit.

  (no flag) <file.rbh>
      Inspect an RBHF container (headers, BODY/PACK/RELC summary).
      Default file: assets/evt/allstage/evtALL.rbh

  -d, --decompress <file> [output]
      Expand PACK → BODY (Tantalus LZ) and write a decompressed PIFF.
      Default output: {DEFAULT_OUT_ROOT}/<name>.decomp.<ext>

  -p, --png <file.vmc|file.rbh> [outdir]
      Export VVTP RGB555 texture pages as PNGs (decompresses PACK if needed).
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_png/
      Note: spr.rbh is sprite metadata only — use .vmc texture banks.

  -w, --wav <file.rbh> [outdir]
      Export digital SFX as unsigned 8-bit mono PCM WAVs @ 11025 Hz.
      Accepts assets/sound/O_*.rbh or gamesnds.rbh (not CD audio).
      For gamesnds, sibling O_*.rbh files resolve external bank refs.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_wav/

  -m, --mesh <file.rbh> [outdir]
      Export world/CREAT mesh RBHs as Wavefront OBJ + ids.json.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_mesh/

  -s, --sprites <file.rbh> [outdir]
      Export sprite metadata bank (spr.rbh) as sprites.json.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_spr/

  -e, --evt <file.rbh> [outdir]
      Export event script bank as events.json.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_evt/

  -c, --cam <file.rbh> [outdir]
      Export camera rail bank as cameras.json.
      Default outdir: {DEFAULT_OUT_ROOT}/<stem>_cam/

Outputs default under {DEFAULT_OUT_ROOT}/ (assets/ is often read-only)."""


def print_usage(*, to_error: bool = False) -> None:
    out = sys.stderr if to_error else sys.stdout
    print(USAGE, file=out)


def default_out_path(input_path: str) -> str:
    # Write under decompressed_assets/, not beside the input — assets/ is often read-only.
    base = Path(input_path).name
    dot = base.rfind(".")
    name = f"{base}.decomp" if dot <= 0 else f"{base[:dot]}.decomp{base[dot:]}"
    return str(Path(DEFAULT_OUT_ROOT) / name)


def default_stem_dir(input_path: str, suffix: str) -> str:
    stem = Path(input_path).stem
    return str(Path(DEFAULT_OUT_ROOT) / f"{stem}_{suffix}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hotd-decompress", add_help=False)
    parser.add_argument("-h", "--help", "--usage", dest="show_usage", action="store_true")
    parser.add_argument("-d", "--decompress", action="store_true")
    parser.add_argument("-p", "--png", action="store_true")
    parser.add_argument("-w", "--wav", action="store_true")
    parser.add_argument("-m", "--mesh", action="store_true")
    parser.add_argument("-s", "--sprites", action="store_true")
    parser.add_argument("-e", "--evt", action="store_true")
    parser.add_argument("-c", "--cam", action="store_true")
    parser.add_argument("paths", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Match the TypeScript CLI: the first argv token selects the mode.
    args = list(sys.argv[1:] if argv is None else argv)
    mode = args[0] if args else None
    show_usage = mode in ("--usage", "--help", "-h")
    decompress = mode in ("--decompress", "-d")
    png = mode in ("--png", "-p")
    wav = mode in ("--wav", "-w")
    mesh = mode in ("--mesh", "-m")
    sprites = mode in ("--sprites", "-s")
    evt = mode in ("--evt", "-e")
    cam = mode in ("--cam", "-c")

    if show_usage:
        print_usage()
        return 0

    export_mode = decompress or png or wav or mesh or sprites or evt or cam
    path_args = args[1:] if export_mode else args

    if len(path_args) == 0:
        if export_mode:
            print_usage(to_error=True)
            return 1
        path_args = ["assets/evt/allstage/evtALL.rbh"]

    input_path = path_args[0]

    if png:
        out_dir = path_args[1] if len(path_args) > 1 else default_stem_dir(input_path, "png")
        result = convert_textures_to_png(input_path, out_dir)
        if not result.pages:
            print(
                f"No RGB555 texture pages found in {input_path}.\n"
                "Note: spr.rbh is sprite metadata only — convert .vmc texture banks instead.",
                file=sys.stderr,
            )
            return 1
        print(f"PNG export: {input_path}")
        print(f"  pages: {len(result.pages)}")
        print(f"  size: {result.pages[0].width}x{result.pages[0].height} RGB555")
        print(f"  skipped non-texture chunks: {result.skippedChunks}")
        print(f"  wrote: {Path(out_dir) / 'page_XXXX.png'} ({len(result.written)} files)")
        return 0

    if wav:
        out_dir = path_args[1] if len(path_args) > 1 else default_stem_dir(input_path, "wav")
        result = convert_sounds_to_wav(input_path, out_dir)
        if not result.clips:
            print(
                f"No sound clips found in {input_path}.\n"
                "Note: use assets/sound/O_*.rbh or gamesnds.rbh (digital SFX, not CD audio).",
                file=sys.stderr,
            )
            return 1
        rate = result.clips[0].sampleRate
        print(f"WAV export: {input_path}")
        print(f"  clips: {len(result.clips)}")
        print(f"  format: 8-bit mono PCM @ {rate} Hz")
        if result.skippedExternal > 0:
            print(
                f"  skipped external refs (missing sibling O_*.rbh): {result.skippedExternal}"
            )
        print(f"  wrote: {Path(out_dir) / '*.wav'} ({len(result.written)} files)")
        return 0

    if mesh:
        out_dir = path_args[1] if len(path_args) > 1 else default_stem_dir(input_path, "mesh")
        result = convert_meshes_to_obj(input_path, out_dir)
        print(f"Mesh export: {input_path}")
        print(f"  kind: {result.bank.kind}")
        print(f"  ids: {len(result.bank.ids)}")
        print(f"  nodes: {len(result.bank.nodes)}")
        print(
            f"  wrote: {Path(out_dir) / 'ids.json'} + node_XXXXXX.obj "
            f"({len(result.written)} files)"
        )
        return 0

    if sprites:
        out_dir = path_args[1] if len(path_args) > 1 else default_stem_dir(input_path, "spr")
        result = convert_sprites_to_json(input_path, out_dir)
        print(f"Sprite export: {input_path}")
        print(f"  sprites: {len(result.bank.sprites)}")
        if result.bank.skipped > 0:
            print(f"  skipped null slots: {result.bank.skipped}")
        print(f"  wrote: {result.written[0]}")
        return 0

    if evt:
        out_dir = path_args[1] if len(path_args) > 1 else default_stem_dir(input_path, "evt")
        result = convert_events_to_json(input_path, out_dir)
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
        return 0

    if cam:
        out_dir = path_args[1] if len(path_args) > 1 else default_stem_dir(input_path, "cam")
        result = convert_cameras_to_json(input_path, out_dir)
        tracks = sum(len(g.tracks) for g in result.bank.groups)
        print(f"Camera export: {input_path}")
        print(f"  groups: {len(result.bank.groups)}")
        print(f"  tracks: {tracks}")
        print(f"  wrote: {result.written[0]}")
        return 0

    if decompress:
        output = path_args[1] if len(path_args) > 1 else default_out_path(input_path)
        result = decompress_piff_file(input_path)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(result.bytes)
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
        return 0

    summary = inspect_rbh(input_path)
    print(summary.description)
    return 0


# argparse is available for tests / embedding; the live CLI matches the TS argv contract.
_PARSER = build_parser()
