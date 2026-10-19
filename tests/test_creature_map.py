"""Creature-map joins against retail assets and THOTD.exe."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hotd_decompress.creature_map import (
    CREATURE_PAGE_HI,
    CREATURE_PAGE_LO,
    TYPE_COUNT,
    VMC_REL,
    build_clusters,
    build_hp,
    build_map,
    build_more,
    find_exe,
    load_exe,
    resolve_asset,
    texture_page_ids,
    write_creature_map,
)
from tests.helpers import ASSETS, requires_assets

EXE = find_exe()
requires_exe = pytest.mark.skipif(EXE is None, reason="THOTD.exe not found")

pytestmark = [pytest.mark.assets, requires_assets, requires_exe]

_NAMED_PAGES = {
    1: {582, 585},
    6: {554},
    16: {556},
    # creatures.md lists 35/36 together as 547–549. The walk splits them:
    # type 35 also skins bone 4 with page 576; type 36 is 548–549 only.
    35: {547, 548, 549, 576},
    36: {548, 549},
    51: {569},
    64: {561, 562, 591},
    76: {557, 558},
    83: {574},
}
_EMPTY_PAGE_TYPES = (5, 10, 39, 44, 52, 66, 75)


@pytest.fixture(scope="module")
def report():
    assert ASSETS is not None and EXE is not None
    return build_map(ASSETS, EXE)


@pytest.fixture(scope="module")
def page_ids():
    assert ASSETS is not None
    return texture_page_ids(resolve_asset(ASSETS, VMC_REL))


def _pages(report, type_id: int) -> set[int]:
    return set(next(row.pages for row in report.types if row.type == type_id))


def test_table_counts(report) -> None:
    assert len(report.types) == 94
    assert len(report.motions) == 674
    assert len(report.spawnFns) == 256


def test_published_page_sets(report) -> None:
    for type_id, pages in _NAMED_PAGES.items():
        assert _pages(report, type_id) == pages
    for type_id in _EMPTY_PAGE_TYPES:
        assert _pages(report, type_id) == set()
    row64 = next(row for row in report.types if row.type == 64)
    assert row64.bones == 28
    row83 = next(row for row in report.types if row.type == 83)
    assert row83.defaultMotionName == "MO_dr_l_nage"


def test_spawn_immediates(report) -> None:
    by_slot = {fn.slot: fn for fn in report.spawnFns}
    assert 6 in by_slot[35].typeImm
    assert 6 in by_slot[36].typeImm
    assert 35 in by_slot[37].typeImm


def test_event_spawns(report) -> None:
    # Slot 37 writes creature type 35 and is spawned at HP 480.
    assert any(hit.typeId == 37 and hit.hp == 480 for hit in report.hits)
    assert any(
        hit.stage == "Stage 01" and hit.typeId == 128 and hit.spawnEventId == 1
        for hit in report.hits
    )


def test_b_red_creature_pages(page_ids) -> None:
    band = [page for page in page_ids if CREATURE_PAGE_LO <= page <= CREATURE_PAGE_HI]
    assert band
    named = {page for pages in _NAMED_PAGES.values() for page in pages}
    assert named <= set(page_ids)


def test_clusters_group_type_16(report, page_ids) -> None:
    assert EXE is not None
    clusters = build_clusters(load_exe(EXE), report, page_ids)
    row = next(cluster for cluster in clusters.clusters if 16 in cluster.types)
    assert row.pages == "556"
    none = next(cluster for cluster in clusters.clusters if cluster.pages == "(none)")
    assert set(_EMPTY_PAGE_TYPES) <= set(none.types)


def test_more_extra_rows() -> None:
    assert EXE is not None
    more = build_more(load_exe(EXE))
    assert len(more.extraRows) == 34
    assert more.extraRows[0].type == TYPE_COUNT
    assert more.extraRows[-1].type == 127
    assert more.slot128Calls


def test_hp_high_and_slot128(report) -> None:
    hp = build_hp(report.hits)
    assert any(row.typeId == 37 and row.hp == 480 for row in hp.high)
    assert any(row.spawnEventId == 1 and "Stage 01" in row.stages for row in hp.slot128)


def test_creature_map_json_round_trip(report, tmp_path: Path) -> None:
    path = tmp_path / "creature-map.json"
    write_creature_map(path, report)
    data = json.loads(path.read_text(encoding="utf-8"))
    type16 = next(row for row in data["types"] if row["type"] == 16)
    assert type16["pages"] == [556]
