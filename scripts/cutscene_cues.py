"""Join evtALL SNDON ops to the THOTD.exe sound-request table.

uv run python scripts/cutscene_cues.py
→ decompressed_assets/exe_tables/cutscene-cues.json
"""

from __future__ import annotations

import sys
from pathlib import Path

from hotd_decompress.creature_map import EVT_REL, load_exe, resolve_asset, resolve_inputs
from hotd_decompress.event import extract_events
from hotd_decompress.sound_table import parse_sound_request_table, write_cue_sheet

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "decompressed_assets" / "exe_tables" / "cutscene-cues.json"


def main() -> None:
    if len(sys.argv) > 2:
        print("Usage: uv run python scripts/cutscene_cues.py [out.json]", file=sys.stderr)
        raise SystemExit(2)
    out = Path(sys.argv[1]) if len(sys.argv) == 2 else DEFAULT_OUT
    try:
        assets, exe_path = resolve_inputs()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    exe = load_exe(exe_path)
    rows = parse_sound_request_table(exe.data)
    bank = extract_events(resolve_asset(assets, EVT_REL))
    written = write_cue_sheet(bank, rows, out)
    print(f"rows {len(rows)}  cues written {written}")


if __name__ == "__main__":
    main()
