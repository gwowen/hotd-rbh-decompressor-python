"""Dump THOTD.exe creature tables joined to assets/ CREAT pages and evtALL spawns.

uv run python scripts/creature_map.py
uv run python scripts/creature_map.py clusters
uv run python scripts/creature_map.py more
uv run python scripts/creature_map.py hp
"""

from __future__ import annotations

import sys

from hotd_decompress.creature_map import (
    DEFAULT_OUT_DIR,
    VMC_REL,
    ClusterReport,
    CreatureMap,
    HpReport,
    MoreReport,
    build_clusters,
    build_hp,
    build_map,
    build_more,
    load_exe,
    resolve_asset,
    resolve_inputs,
    texture_page_ids,
    write_clusters,
    write_creature_map,
)

USAGE = """Usage:
  uv run python scripts/creature_map.py [map|clusters|more|hp]

  map       94 type rows, spawn fns, CREAT pages, evtALL usage
            → decompressed_assets/exe_tables/creature-map.json
  clusters  page clusters, spawnEventId histogram, `ApplyCreatureTypeStats` (`FUN_00483ad0`) callers
            → decompressed_assets/exe_tables/creature-clusters.json
  more      type rows 94–127 and the slot-128 prolog
  hp        high-HP spawns and Stage 03/04 slot usage

Exe: HOTD_EXE, else hotd-exe/THOTD.exe, else the sibling TypeScript tree.
Assets: HOTD_ASSETS or assets/."""

MODES = ("map", "clusters", "more", "hp")


def print_map(report: CreatureMap) -> None:
    print("=== TYPES ===")
    for row in report.types:
        pages = ",".join(str(page) for page in row.pages)
        print(
            f"{row.type:2d}  model={row.modelId}  r={row.hitRadius}  s={row.scale}"
            f"  y={row.yOffset}  b={row.bones}  mot={row.defaultMotion}:{row.defaultMotionName}"
            f"  pages={pages}  meshes={len(row.meshIds)}  u40={row.u40}  u48={row.u48}"
        )
    print("\n=== SPAWN FNS ===")
    for fn in report.spawnFns:
        use = report.spawnUsage.get(fn.slot)
        if use is None:
            usage = "UNUSED"
        else:
            usage = f"n={use.count} stages={use.stages} ev={','.join(str(i) for i in use.eventIds)}"
        print(
            f"{fn.slot:3d}  {fn.va}  imm={','.join(str(i) for i in fn.typeImm)}"
            f"  83ad0={fn.calls83ad0}  a5180={fn.callsA5180}  {usage}"
        )


def print_clusters(report: CreatureMap, clusters: ClusterReport) -> None:
    by_type = {row.type: row for row in report.types}
    print("=== PAGE CLUSTERS ===")
    for cluster in clusters.clusters:
        sample = by_type[cluster.types[0]]
        bones = "/".join(str(by_type[type_id].bones) for type_id in cluster.types)
        scales = "/".join(str(by_type[type_id].scale) for type_id in cluster.types)
        radii = "/".join(str(by_type[type_id].hitRadius) for type_id in cluster.types)
        ids = ",".join(str(type_id) for type_id in cluster.types)
        print(
            f"pages [{cluster.pages}]  types {ids}  bones={bones}"
            f"  scale={scales}  r={radii}  mot={sample.defaultMotionName}"
        )

    print("\n=== spawnEventId histogram (id < 94 could be creature type) ===")
    for row in clusters.spawnEventIds:
        mark = "TYPE" if 0 <= row.ev < 94 else "    "
        print(f"{mark} ev={row.ev:3d} n={row.n:4d} slots={row.slots}  {row.stages}")

    print("\n=== call sites of `ApplyCreatureTypeStats` (`FUN_00483ad0`) ===")
    print("\n".join(clusters.callSites83ad0))

    print("\n=== spawn fns that reach 0x483ad0 (direct or 1-hop) ===")
    for row in clusters.spawnFnsReaching:
        print(f"slot {row.slot} va={row.va} n={row.n} direct={row.direct}")

    print("\n=== creature PNG pages ===")
    print(", ".join(str(page) for page in clusters.creaturePages))

    print("\n=== motion prefixes (full) ===")
    for group in clusters.motionPrefixes:
        sample = " | ".join(group.samples)
        tail = " ..." if group.count > len(group.samples) else ""
        print(f"{group.prefix} ({group.count})  {sample}{tail}")


def print_more(report: MoreReport) -> None:
    print("=== extra type rows 94-127 ===")
    for row in report.extraRows:
        print(
            f"t{row.type} model={row.model} r={row.hitRadius}"
            f" s={row.scale} mot={row.motion} bones={row.bones}"
        )
    print("\n=== slot 128 prolog ===")
    print(report.slot128Hex)
    print("\ncalls:")
    for call in report.slot128Calls:
        print(f"  {call}")
    print("\n=== DAT_005f1df4 first 94 floats? or xyz ===")
    for sample in report.fieldSamples:
        print(sample["index"], sample["f32"], sample["u32"])
    if report.osm01Offset is None:
        print("\nOSM01 at", -1, "")
    else:
        print("\nOSM01 at", report.osm01Offset, f"va={report.osm01Va}")
    print("\n=== selected type raw ===")
    for line in report.selected:
        print(line)


def print_hp(report: HpReport) -> None:
    print("=== high HP (>=10) ===")
    for row in report.high:
        print(
            f"hp={row.hp} slot={row.typeId} ev={row.spawnEventId}"
            f" {row.stage} n={row.count} e.g. {row.scene}"
        )
    print("\n=== Stage 04 slots ===")
    for row in report.stage04:
        scenes = ";".join(row.scenes)
        print(
            f"slot {row.slot} n={row.count} ev={','.join(str(i) for i in row.eventIds)}"
            f" hp={','.join(str(i) for i in row.hps)} scenes={scenes}"
        )
    print("\n=== Stage 03 slots ===")
    for row in report.stage03:
        print(
            f"slot {row.slot} n={row.count} ev={','.join(str(i) for i in row.eventIds)}"
            f" hp={','.join(str(i) for i in row.hps)}"
        )
    print("\n=== slot 128 ev by stage (type candidates) ===")
    for row in report.slot128:
        stages = ",".join(f"{name}:{count}" for name, count in row.stages.items())
        hps = ",".join(str(hp) for hp in row.hps)
        print(f"type {row.spawnEventId:2d} n={row.count:3d} hp={hps}  {stages}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "--usage"):
        print(USAGE)
        return 0
    mode = args[0] if args else "map"
    if mode not in MODES:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 1
    if len(args) > 1:
        print(USAGE, file=sys.stderr)
        return 1

    try:
        assets, exe_path = resolve_inputs()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if mode == "more":
        report = build_more(load_exe(exe_path))
        print_more(report)
        return 0

    creature_map = build_map(assets, exe_path)
    if mode == "map":
        out = DEFAULT_OUT_DIR / "creature-map.json"
        write_creature_map(out, creature_map)
        print(f"wrote {out}")
        print(
            f"types {len(creature_map.types)} spawnFns {len(creature_map.spawnFns)}"
            f" used spawn slots {len(creature_map.spawnUsage)} strings {len(creature_map.strings)}"
        )
        print_map(creature_map)
        return 0
    if mode == "hp":
        print_hp(build_hp(creature_map.hits))
        return 0

    pages = texture_page_ids(resolve_asset(assets, VMC_REL))
    clusters = build_clusters(load_exe(exe_path), creature_map, pages)
    out = DEFAULT_OUT_DIR / "creature-clusters.json"
    write_clusters(out, clusters)
    print(f"wrote {out}")
    print_clusters(creature_map, clusters)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
