from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hotd_decompress.audio import extract_sound_clips
from hotd_decompress.camera import extract_cameras
from hotd_decompress.event import extract_events
from hotd_decompress.mesh import extract_meshes
from hotd_decompress.piff import decompress_piff_file
from hotd_decompress.rbh import inspect_rbh
from hotd_decompress.sprite import extract_sprites
from hotd_decompress.texture import extract_texture_pages, texture_page_to_rgba
from tests.helpers import (
    ASSETS,
    TS_ROOT,
    asset,
    decode_png_rgba,
    requires_assets,
    requires_bun,
)

pytestmark = pytest.mark.assets


@requires_assets
def test_decompress_b_red_page_count() -> None:
    result = decompress_piff_file(asset("art/stage1/creature/B_RED.VMC"))
    assert result.form == "VVTP"
    assert result.packedChunks > 0
    pages = extract_texture_pages(result.bytes)
    assert len(pages.pages) == 421


@requires_assets
@requires_bun
def test_decompress_b_red_byte_identical_to_bun(tmp_path: Path) -> None:
    src = asset("art/stage1/creature/B_RED.VMC")
    bun_out = tmp_path / "bun.decomp.VMC"
    py_out = tmp_path / "py.decomp.VMC"
    subprocess.run(
        ["bun", "run", "index.ts", "-d", str(src), str(bun_out)],
        cwd=TS_ROOT,
        check=True,
        capture_output=True,
    )
    py_out.write_bytes(decompress_piff_file(src).bytes)
    assert py_out.read_bytes() == bun_out.read_bytes()


@requires_assets
def test_discover_classifies_retail_tree() -> None:
    from hotd_decompress.discover import files_for_kinds

    assert ASSETS is not None
    grouped = files_for_kinds(ASSETS, ["png", "wav", "mesh", "sprites", "evt", "cam"])
    png_names = {p.name.lower() for p in grouped["png"]}
    assert png_names >= {"b_red.vmc", "bigger.vmc", "texture.vmc"}
    assert len(grouped["png"]) == 7
    assert any(p.name.lower() == "gamesnds.rbh" for p in grouped["wav"])
    assert any(p.name.lower() == "o_help.rbh" for p in grouped["wav"])
    mesh_stems = {p.stem.lower() for p in grouped["mesh"]}
    assert "world1" in mesh_stems
    assert "creat1" in mesh_stems
    assert len(grouped["mesh"]) == 8
    assert len(grouped["sprites"]) == 1
    assert len(grouped["evt"]) == 1
    assert len(grouped["cam"]) == 1


@requires_assets
def test_cli_evt_all(tmp_path: Path) -> None:
    from hotd_decompress.cli import main

    assert main(["-e", "--all", str(ASSETS), str(tmp_path)]) == 0
    assert (tmp_path / "evtALL_evt" / "events.json").is_file()


@requires_assets
def test_cli_type_directory(tmp_path: Path) -> None:
    from hotd_decompress.cli import main

    assert main(["-s", str(asset("sprite")), str(tmp_path)]) == 0
    assert (tmp_path / "spr_spr" / "sprites.json").is_file()


@requires_assets
def test_cli_decompress_all_skips_unpacked(tmp_path: Path, capsys) -> None:
    from hotd_decompress.cli import main

    evt_dir = asset("evt")
    assert main(["-d", "--all", str(evt_dir), str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "skipped" in out
    assert not any(tmp_path.glob("*.decomp.*"))
    evt = inspect_rbh(asset("evt/allstage/evtALL.rbh"))
    assert evt.bodyCount == 1
    assert "RBH:" in evt.description
    spr = inspect_rbh(asset("sprite/spr.rbh"))
    assert spr.bodyCount == 1


@requires_assets
def test_wav_oneshot_and_gamesnds() -> None:
    help_clips = extract_sound_clips(asset("sound/O_HELP.rbh"))
    assert len(help_clips.clips) == 1
    assert help_clips.clips[0].sampleRate == 0x2B11
    assert help_clips.clips[0].pcm

    bank = extract_sound_clips(asset("sound/gamesnds.rbh"))
    assert len(bank.clips) > 0
    embedded = [c for c in bank.clips if c.source == "gamesnds-embedded"]
    external = [c for c in bank.clips if c.source == "gamesnds-external"]
    assert embedded
    assert external


@requires_assets
@requires_bun
def test_wav_byte_identical_to_bun(tmp_path: Path) -> None:
    src = asset("sound/O_HELP.rbh")
    bun_dir = tmp_path / "bun"
    py_dir = tmp_path / "py"
    subprocess.run(
        ["bun", "run", "index.ts", "-w", str(src), str(bun_dir)],
        cwd=TS_ROOT,
        check=True,
        capture_output=True,
    )
    from hotd_decompress.audio import convert_sounds_to_wav

    convert_sounds_to_wav(src, str(py_dir))
    bun_files = sorted(p.name for p in bun_dir.iterdir())
    py_files = sorted(p.name for p in py_dir.iterdir())
    assert bun_files == py_files
    for name in bun_files:
        assert (bun_dir / name).read_bytes() == (py_dir / name).read_bytes()


@requires_assets
@requires_bun
def test_png_pixels_match_bun(tmp_path: Path) -> None:
    src = asset("art/stage1/creature/B_RED.VMC")
    bun_dir = tmp_path / "bun_png"
    subprocess.run(
        ["bun", "run", "index.ts", "-p", str(src), str(bun_dir)],
        cwd=TS_ROOT,
        check=True,
        capture_output=True,
    )
    pages = extract_texture_pages(src)
    assert len(pages.pages) == 421
    sample = pages.pages[0]
    bun_png = bun_dir / f"page_{sample.pageId:04d}.png"
    _w, _h, bun_rgba = decode_png_rgba(bun_png.read_bytes())
    assert bun_rgba == texture_page_to_rgba(sample)


@requires_assets
def test_mesh_world_and_creat() -> None:
    world = extract_meshes(asset("art/stage1/world/world1.rbh"))
    assert world.kind == "world"
    assert world.ids
    assert world.nodes
    creat = extract_meshes(asset("art/stage1/creature/CREAT1.RBH"))
    assert creat.kind == "creat"
    assert creat.ids
    assert creat.nodes


@requires_assets
def test_sprite_camera_event_counts() -> None:
    sprites = extract_sprites(asset("sprite/spr.rbh"))
    assert len(sprites.sprites) > 0

    cams = extract_cameras(asset("cam/allstage/camALL.rbh"))
    assert cams.groups
    assert any(g.tracks for g in cams.groups)

    events = extract_events(asset("evt/allstage/evtALL.rbh"))
    assert len(events.stages) >= 7
    scenes = sum(len(s.scenes) for s in events.stages)
    assert scenes > 0
    ops = sum(len(sec.ops) for st in events.stages for sc in st.scenes for sec in sc.sections)
    assert ops > 0


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _approx_equal(a: object, b: object) -> bool:
    if isinstance(a, float) and isinstance(b, (int, float)):
        return a == pytest.approx(b)
    if isinstance(b, float) and isinstance(a, (int, float)):
        return b == pytest.approx(a)
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(_approx_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_approx_equal(x, y) for x, y in zip(a, b, strict=True))
    return a == b


@requires_assets
@requires_bun
@pytest.mark.parametrize(
    ("flag", "rel", "json_name", "convert"),
    [
        ("-s", "sprite/spr.rbh", "sprites.json", "sprites"),
        ("-c", "cam/allstage/camALL.rbh", "cameras.json", "cameras"),
        ("-e", "evt/allstage/evtALL.rbh", "events.json", "events"),
    ],
)
def test_json_structure_matches_bun(
    tmp_path: Path,
    flag: str,
    rel: str,
    json_name: str,
    convert: str,
) -> None:
    src = asset(*rel.split("/"))
    bun_dir = tmp_path / "bun"
    py_dir = tmp_path / "py"
    subprocess.run(
        ["bun", "run", "index.ts", flag, str(src), str(bun_dir)],
        cwd=TS_ROOT,
        check=True,
        capture_output=True,
    )
    if convert == "sprites":
        from hotd_decompress.sprite import convert_sprites_to_json

        convert_sprites_to_json(src, str(py_dir))
    elif convert == "cameras":
        from hotd_decompress.camera import convert_cameras_to_json

        convert_cameras_to_json(src, str(py_dir))
    else:
        from hotd_decompress.event import convert_events_to_json

        convert_events_to_json(src, str(py_dir))

    bun_json = _load_json(bun_dir / json_name)
    py_json = _load_json(py_dir / json_name)
    # Absolute source paths differ across trees; compare the rest.
    if isinstance(bun_json, dict) and isinstance(py_json, dict):
        bun_json = {k: v for k, v in bun_json.items() if k != "source"}
        py_json = {k: v for k, v in py_json.items() if k != "source"}
    assert _approx_equal(py_json, bun_json)


@requires_assets
@requires_bun
def test_mesh_ids_structure_matches_bun(tmp_path: Path) -> None:
    src = asset("art/stage1/creature/CREAT1.RBH")
    bun_dir = tmp_path / "bun"
    py_dir = tmp_path / "py"
    subprocess.run(
        ["bun", "run", "index.ts", "-m", str(src), str(bun_dir)],
        cwd=TS_ROOT,
        check=True,
        capture_output=True,
    )
    from hotd_decompress.mesh import convert_meshes_to_obj

    convert_meshes_to_obj(src, str(py_dir))
    bun_ids = _load_json(bun_dir / "ids.json")
    py_ids = _load_json(py_dir / "ids.json")
    assert isinstance(bun_ids, dict) and isinstance(py_ids, dict)
    bun_ids.pop("source", None)
    py_ids.pop("source", None)
    assert bun_ids["kind"] == py_ids["kind"]
    assert bun_ids["idCount"] == py_ids["idCount"]
    assert bun_ids["nodeCount"] == py_ids["nodeCount"]
    assert _approx_equal(bun_ids["ids"], py_ids["ids"])
    assert len(bun_ids["nodes"]) == len(py_ids["nodes"])
