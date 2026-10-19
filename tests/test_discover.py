from __future__ import annotations

from pathlib import Path

from hotd_decompress.discover import files_for_kinds, list_asset_files, matches_kind


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def test_list_and_classify(tmp_path: Path) -> None:
    red = _touch(tmp_path / "art/stage1/creature/B_RED.VMC")
    creat = _touch(tmp_path / "art/stage1/creature/CREAT1.RBH")
    world = _touch(tmp_path / "art/stage2/world/world2.rbh")
    world5 = _touch(tmp_path / "art/stage5/world/WORLD5.RBH")
    help_snd = _touch(tmp_path / "sound/O_HELP.rbh")
    bank = _touch(tmp_path / "sound/gamesnds.rbh")
    spr = _touch(tmp_path / "sprite/spr.rbh")
    evt = _touch(tmp_path / "evt/allstage/evtALL.rbh")
    cam = _touch(tmp_path / "cam/allstage/camALL.rbh")
    _touch(tmp_path / "readme.txt")

    files = list_asset_files(tmp_path)
    assert files == sorted(
        [red, creat, world, world5, help_snd, bank, spr, evt, cam],
        key=lambda p: str(p).replace("\\", "/").lower(),
    )

    grouped = files_for_kinds(
        tmp_path, ["decompress", "png", "wav", "mesh", "sprites", "evt", "cam"]
    )
    assert grouped["png"] == [red]
    assert set(grouped["wav"]) == {bank, help_snd}
    assert set(grouped["mesh"]) == {creat, world, world5}
    assert grouped["sprites"] == [spr]
    assert grouped["evt"] == [evt]
    assert grouped["cam"] == [cam]
    assert red in grouped["decompress"]
    assert help_snd in grouped["decompress"]


def test_matches_kind_sound_by_name(tmp_path: Path) -> None:
    stray = _touch(tmp_path / "misc/O_FOO.rbh")
    assert matches_kind(stray, "wav")
    assert not matches_kind(stray, "mesh")
    assert not matches_kind(_touch(tmp_path / "misc/notes.rbh"), "wav")
