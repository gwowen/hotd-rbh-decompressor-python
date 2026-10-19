"""
Exe creature tables joined to CREAT skins and evtALL spawns.

PE: image base 0x400000. DGROUP VA 0x5A0000 (file 0x187400).
.text VA 0x410000 (file 0x400).

Not a CLI decode flag. Runner: scripts/creature_map.py.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from hotd_decompress.binary import f32, s32, u16, u32
from hotd_decompress.event import EventBank, extract_events
from hotd_decompress.jsonutil import write_json
from hotd_decompress.mesh import extract_meshes
from hotd_decompress.piff import decompress_piff, load_piff
from hotd_decompress.texture import is_texture_page

REPO_ROOT = Path(__file__).resolve().parents[2]
TS_ROOT = REPO_ROOT.parent.parent / "typescript" / "hotd-decompress"
DEFAULT_OUT_DIR = REPO_ROOT / "decompressed_assets" / "exe_tables"

IMAGE_BASE = 0x400000
DGROUP_VA = 0x5A0000
DGROUP_FILE = 0x187400
BEGTEXT_VA = 0x410000
BEGTEXT_FILE = 0x400

TYPE_VA = 0x005D46AC
TYPE_STRIDE = 0x4C
TYPE_COUNT = 94
EXTRA_TYPE_COUNT = 128
BONE_VA = 0x005EFA58
SKEL_VA = 0x005EF8E0
MOTION_VA = 0x005F1258
MOTION_COUNT = 674
SPAWN_VA = 0x005D8118
SPAWN_COUNT = 256

FUN_TYPE_TO_MODEL = 0x483AD0
FUN_A5180 = 0x4A5180
SLOT128_FN = 0x47B2C4
DAT_005F1DF4 = 0x005F1DF4

CREATURE_PAGE_LO = 547
CREATURE_PAGE_HI = 595

CREAT_REL = (
    ("art", "stage1", "creature", "CREAT1.RBH"),
    ("art", "stage1", "creature", "CREAT2.rbh"),
)
EVT_REL = ("evt", "allstage", "evtALL.rbh")
VMC_REL = ("art", "stage1", "creature", "B_RED.VMC")

_STRING_NEEDLES = (
    "ENGuard",
    "zonbiman",
    "Chariot",
    "Hanged",
    "Hermit",
    "Magician",
    "Ebitan",
    "Kageo",
    "Kenji",
    "Devilon",
    "Cyril",
    "Goldman",
    "Bouere",
    "Bourere",
    "Mofish",
    "Saruzou",
    "Ishii",
    "Harris",
    "Rubin",
    "Drake",
    "Bueel",
    "Gilmore",
    "Simon",
    "Nail",
    "CREAT",
    "yoroi",
    "tojo",
    "gman",
    "ebitb",
    "onozonbia",
    "taraba",
    "tekk",
    "hiru",
    "kyuri",
)

_SELECTED_TYPES = (1, 2, 3, 11, 16, 18, 35, 36, 51, 64, 76, 83, 84)


@dataclass
class ExeImage:
    path: str
    data: bytes

    def va_to_file(self, va: int) -> int:
        if va >= DGROUP_VA:
            return DGROUP_FILE + (va - DGROUP_VA)
        if va >= BEGTEXT_VA:
            return BEGTEXT_FILE + (va - BEGTEXT_VA)
        raise ValueError(f"va {va:x} not in known section")

    def u32(self, offset: int) -> int:
        return u32(self.data, offset)

    def s32(self, offset: int) -> int:
        return s32(self.data, offset)

    def u16(self, offset: int) -> int:
        return u16(self.data, offset)

    def f32(self, offset: int) -> float:
        return f32(self.data, offset)

    def cstr(self, va: int) -> str:
        if va < IMAGE_BASE:
            return ""
        off = self.va_to_file(va)
        chars: list[str] = []
        while off < len(self.data) and self.data[off] != 0:
            chars.append(chr(self.data[off]))
            off += 1
            if len(chars) > 200:
                break
        return "".join(chars)


@dataclass
class CreatureType:
    type: int
    modelId: int
    hitRadius: float
    scale: float
    yOffset: float
    field30: float
    defaultMotion: int
    bones: int
    skelPtr: str
    meshIds: list[int]
    rawHex: list[str]
    floats: dict[str, float]
    u32_04: int
    u32_08: int
    u32_0c: int
    u32_10: int
    f18: float
    f1c: float
    f20: float
    f24: float
    f34: float
    f38: float
    f3c: float
    u40: int
    u48: int
    defaultMotionName: str | None = None
    pages: list[int] = field(default_factory=list)


@dataclass
class SpawnFn:
    slot: int
    va: str
    typeImm: list[int]
    calls: list[str]
    calls83ad0: bool
    callsA5180: bool
    prolog: str


@dataclass
class ExeString:
    off: int
    va: str
    s: str


@dataclass
class SpawnHit:
    typeId: int
    spawnEventId: int
    hp: int
    stage: str
    scene: str
    op: str


@dataclass
class SpawnUsage:
    count: int
    stages: dict[str, int]
    eventIds: list[int]
    hp: list[int]


@dataclass
class CreatureMap:
    types: list[CreatureType]
    motions: list[str]
    spawnFns: list[SpawnFn]
    spawnUsage: dict[int, SpawnUsage]
    strings: list[ExeString]
    hits: list[SpawnHit]


@dataclass
class PageCluster:
    pages: str
    types: list[int]


@dataclass
class SpawnEventHist:
    ev: int
    n: int
    slots: list[int]
    stages: list[str]


@dataclass
class SpawnReach:
    slot: int
    va: str
    n: int
    direct: bool


@dataclass
class MotionPrefix:
    prefix: str
    count: int
    samples: list[str]


@dataclass
class ClusterReport:
    clusters: list[PageCluster]
    spawnEventIds: list[SpawnEventHist]
    callSites83ad0: list[str]
    spawnFnsReaching: list[SpawnReach]
    creaturePages: list[int]
    motionPrefixes: list[MotionPrefix]


@dataclass
class ExtraTypeRow:
    type: int
    model: int
    hitRadius: float
    scale: float
    motion: int
    bones: int


@dataclass
class MoreReport:
    extraRows: list[ExtraTypeRow]
    slot128Hex: str
    slot128Calls: list[str]
    fieldSamples: list[dict[str, float | int | str]]
    osm01Offset: int | None
    osm01Va: str | None
    selected: list[str]


@dataclass
class HighHpRow:
    hp: int
    typeId: int
    spawnEventId: int
    stage: str
    count: int
    scene: str


@dataclass
class StageSlotUsage:
    slot: int
    count: int
    eventIds: list[int]
    hps: list[int]
    scenes: list[str]


@dataclass
class Slot128Usage:
    spawnEventId: int
    count: int
    hps: list[int]
    stages: dict[str, int]


@dataclass
class HpReport:
    high: list[HighHpRow]
    stage04: list[StageSlotUsage]
    stage03: list[StageSlotUsage]
    slot128: list[Slot128Usage]


def find_exe() -> Path | None:
    env = os.environ.get("HOTD_EXE")
    if env:
        path = Path(env)
        if path.is_file():
            return path
    for candidate in (
        REPO_ROOT / "hotd-exe" / "THOTD.exe",
        TS_ROOT / "hotd-exe" / "THOTD.exe",
    ):
        if candidate.is_file():
            return candidate
    return None


def find_assets() -> Path | None:
    env = os.environ.get("HOTD_ASSETS")
    if env:
        path = Path(env)
        if path.is_dir():
            return path
    for candidate in (REPO_ROOT / "assets", TS_ROOT / "assets"):
        if candidate.is_dir():
            return candidate
    return None


def resolve_inputs(
    assets: Path | None = None,
    exe: Path | None = None,
) -> tuple[Path, Path]:
    assets_root = assets if assets is not None else find_assets()
    exe_path = exe if exe is not None else find_exe()
    if assets_root is None or not Path(assets_root).is_dir():
        raise FileNotFoundError("assets directory not found (set HOTD_ASSETS or add assets/)")
    if exe_path is None or not Path(exe_path).is_file():
        raise FileNotFoundError("THOTD.exe not found (set HOTD_EXE or add hotd-exe/THOTD.exe)")
    return Path(assets_root), Path(exe_path)


def resolve_asset(root: Path, parts: tuple[str, ...]) -> Path:
    current = root
    for part in parts:
        if not current.is_dir():
            raise FileNotFoundError(root.joinpath(*parts))
        found = next((p for p in current.iterdir() if p.name.lower() == part.lower()), None)
        if found is None:
            raise FileNotFoundError(root.joinpath(*parts))
        current = found
    if not current.is_file():
        raise FileNotFoundError(current)
    return current


def load_exe(path: Path) -> ExeImage:
    return ExeImage(path=str(path), data=path.read_bytes())


def walk_skeleton(exe: ExeImage, va: int, seen: set[int] | None = None) -> list[int]:
    """Mesh id at +0x00 (skip 0); up to 8 child pointers at +0x1C."""
    if seen is None:
        seen = set()
    if not va or va < IMAGE_BASE or va in seen:
        return []
    seen.add(va)
    off = exe.va_to_file(va)
    mesh_id = exe.u32(off)
    child_count = exe.u32(off + 0x18)
    ids = [mesh_id] if mesh_id != 0 else []
    for i in range(min(child_count, 8)):
        child = exe.u32(off + 0x1C + i * 4)
        ids.extend(walk_skeleton(exe, child, seen))
    return ids


def parse_motions(exe: ExeImage) -> list[str]:
    names: list[str] = []
    base = exe.va_to_file(MOTION_VA)
    for i in range(MOTION_COUNT):
        ptr = exe.u32(base + i * 4)
        names.append(exe.cstr(ptr))
    return names


def _type_row(exe: ExeImage, index: int, motions: list[str]) -> CreatureType:
    off = exe.va_to_file(TYPE_VA) + index * TYPE_STRIDE
    raw = [exe.u32(off + b) for b in range(0, TYPE_STRIDE, 4)]
    floats: dict[str, float] = {}
    for b in range(0, TYPE_STRIDE, 4):
        value = exe.f32(off + b)
        if math.isfinite(value) and abs(value) < 1e6:
            floats[f"+0x{b:x}"] = value
    default_motion = exe.u32(off + 0x44)
    skel_ptr = exe.u32(exe.va_to_file(SKEL_VA) + index * 4)
    motion_name = None
    if 0 <= default_motion < len(motions):
        motion_name = motions[default_motion]
    return CreatureType(
        type=index,
        modelId=exe.u32(off),
        hitRadius=exe.f32(off + 0x14),
        scale=exe.f32(off + 0x28),
        yOffset=exe.f32(off + 0x2C),
        field30=exe.f32(off + 0x30),
        defaultMotion=default_motion,
        bones=s32(exe.data, exe.va_to_file(BONE_VA) + index * 4),
        skelPtr=f"0x{skel_ptr:x}",
        meshIds=walk_skeleton(exe, skel_ptr),
        rawHex=[f"{word:08x}" for word in raw],
        floats=floats,
        u32_04=exe.u32(off + 4),
        u32_08=exe.u32(off + 8),
        u32_0c=exe.u32(off + 0x0C),
        u32_10=exe.u32(off + 0x10),
        f18=exe.f32(off + 0x18),
        f1c=exe.f32(off + 0x1C),
        f20=exe.f32(off + 0x20),
        f24=exe.f32(off + 0x24),
        f34=exe.f32(off + 0x34),
        f38=exe.f32(off + 0x38),
        f3c=exe.f32(off + 0x3C),
        u40=exe.u32(off + 0x40),
        u48=exe.u32(off + 0x48),
        defaultMotionName=motion_name,
    )


def parse_types(exe: ExeImage, motions: list[str]) -> list[CreatureType]:
    return [_type_row(exe, i, motions) for i in range(TYPE_COUNT)]


def _scan_type_writes(exe: ExeImage, fn_va: int) -> tuple[list[int], list[int]]:
    """Immediate stores to entity+0xd4 and rel32 calls in the first 512 bytes."""
    if fn_va < IMAGE_BASE:
        return [], []
    try:
        off = exe.va_to_file(fn_va)
    except ValueError:
        return [], []
    imm16: list[int] = []
    calls: list[int] = []
    end = min(off + 512, len(exe.data) - 10)
    p = off
    while p < end:
        opcode = exe.data[p]
        if opcode == 0xC3 and p > off + 8:
            break
        if opcode == 0xE8:
            rel = exe.s32(p + 1)
            next_va = fn_va + (p - off) + 5
            calls.append((next_va + rel) & 0xFFFFFFFF)
            p += 5
            continue
        if opcode == 0x66 and exe.data[p + 1] == 0xC7:
            modrm = exe.data[p + 2]
            mod = modrm >> 6
            if mod == 1 and exe.data[p + 3] == 0xD4:
                imm16.append(exe.u16(p + 4))
            elif mod == 2 and exe.u32(p + 3) == 0xD4:
                imm16.append(exe.u16(p + 7))
        if opcode == 0xC7:
            modrm = exe.data[p + 1]
            mod = modrm >> 6
            if mod == 1 and exe.data[p + 2] == 0xD4:
                value = exe.u32(p + 3)
                if value <= 0xFFFF:
                    imm16.append(value)
            elif mod == 2 and exe.u32(p + 2) == 0xD4:
                value = exe.u32(p + 6)
                if value <= 0xFFFF:
                    imm16.append(value)
        p += 1
    return list(dict.fromkeys(imm16)), list(dict.fromkeys(calls))


def parse_spawn_fns(exe: ExeImage) -> list[SpawnFn]:
    """256 spawn slots at DAT_005d8118, including null pointers."""
    base = exe.va_to_file(SPAWN_VA)
    fns: list[SpawnFn] = []
    for slot in range(SPAWN_COUNT):
        ptr = exe.u32(base + slot * 4)
        if ptr == 0:
            fns.append(
                SpawnFn(
                    slot=slot,
                    va="0x0",
                    typeImm=[],
                    calls=[],
                    calls83ad0=False,
                    callsA5180=False,
                    prolog="",
                )
            )
            continue
        imm, calls = _scan_type_writes(exe, ptr)
        off = exe.va_to_file(ptr)
        prolog = exe.data[off : off + 48].hex()
        fns.append(
            SpawnFn(
                slot=slot,
                va=f"0x{ptr:x}",
                typeImm=imm,
                calls=[f"0x{call:x}" for call in calls],
                calls83ad0=FUN_TYPE_TO_MODEL in calls,
                callsA5180=FUN_A5180 in calls,
                prolog=prolog,
            )
        )
    return fns


def creat_page_index(paths: list[Path]) -> dict[int, set[int]]:
    """CREAT id → textured prim page ids (OBJ usemtl page_N)."""
    pages: dict[int, set[int]] = {}
    for path in paths:
        bank = extract_meshes(path)
        nodes = {node.offset: node for node in bank.nodes}
        for entry in bank.ids:
            found = pages.setdefault(entry.id, set())
            for off in entry.nodeOffsets:
                node = nodes.get(off)
                if node is None:
                    continue
                for batch in node.batches:
                    for prim in batch.prims:
                        if prim.textured and prim.texPageId is not None:
                            found.add(prim.texPageId)
    return pages


def apply_pages(types: list[CreatureType], pages_by_mesh: dict[int, set[int]]) -> None:
    for row in types:
        pages: set[int] = set()
        for mesh_id in row.meshIds:
            pages.update(pages_by_mesh.get(mesh_id, ()))
        row.pages = sorted(pages)


def event_hits(bank: EventBank) -> list[SpawnHit]:
    hits: list[SpawnHit] = []
    for stage in bank.stages:
        stage_name = stage.name if stage.name is not None else f"slot{stage.index}"
        for scene in stage.scenes:
            scene_name = scene.name if scene.name is not None else str(scene.index)
            for section in scene.sections:
                for op in section.ops:
                    if op.spawns is None:
                        continue
                    for spawn in op.spawns:
                        hits.append(
                            SpawnHit(
                                typeId=spawn.typeId,
                                spawnEventId=(
                                    spawn.spawnEventId if spawn.spawnEventId is not None else -1
                                ),
                                hp=spawn.unk22 if spawn.unk22 is not None else -1,
                                stage=stage_name,
                                scene=scene_name,
                                op=op.name,
                            )
                        )
    return hits


def spawn_usage(hits: list[SpawnHit]) -> dict[int, SpawnUsage]:
    usage: dict[int, SpawnUsage] = {}
    for hit in hits:
        row = usage.get(hit.typeId)
        if row is None:
            row = SpawnUsage(count=0, stages={}, eventIds=[], hp=[])
            usage[hit.typeId] = row
        row.count += 1
        row.stages[hit.stage] = row.stages.get(hit.stage, 0) + 1
        if hit.spawnEventId >= 0:
            row.eventIds.append(hit.spawnEventId)
        if hit.hp >= 0:
            row.hp.append(hit.hp)
    for row in usage.values():
        row.eventIds = sorted(set(row.eventIds))
        row.hp = sorted(set(row.hp))
    return usage


def find_strings(exe: ExeImage) -> list[ExeString]:
    found: list[ExeString] = []
    hay = exe.data
    for needle in _STRING_NEEDLES:
        raw = needle.encode("ascii")
        start_at = 0
        while start_at < len(hay):
            at = hay.find(raw, start_at)
            if at < 0:
                break
            start = at
            while start > 0 and 32 <= hay[start - 1] < 127:
                start -= 1
            end = at
            while end < len(hay) and 32 <= hay[end] < 127:
                end += 1
            text = hay[start:end].decode("ascii")
            if start >= DGROUP_FILE:
                va = DGROUP_VA + (start - DGROUP_FILE)
            elif start >= BEGTEXT_FILE:
                va = BEGTEXT_VA + (start - BEGTEXT_FILE)
            else:
                va = start
            found.append(ExeString(off=start, va=f"0x{va:x}", s=text))
            start_at = at + len(raw)
    unique: dict[str, ExeString] = {}
    for item in found:
        unique.setdefault(item.s, item)
    return list(unique.values())


def build_map(assets: Path, exe_path: Path) -> CreatureMap:
    exe = load_exe(exe_path)
    motions = parse_motions(exe)
    types = parse_types(exe, motions)
    creat_paths = [resolve_asset(assets, parts) for parts in CREAT_REL]
    apply_pages(types, creat_page_index(creat_paths))
    bank = extract_events(resolve_asset(assets, EVT_REL))
    hits = event_hits(bank)
    return CreatureMap(
        types=types,
        motions=motions,
        spawnFns=parse_spawn_fns(exe),
        spawnUsage=spawn_usage(hits),
        strings=find_strings(exe),
        hits=hits,
    )


def texture_page_ids(source: Path) -> list[int]:
    """VVTP pageId fields. Does not expand RGB555 pixels."""
    decompressed = decompress_piff(load_piff(source))
    ids: list[int] = []
    for chunk in decompressed.chunks:
        if chunk.tag != "BODY" or not is_texture_page(chunk.data):
            continue
        ids.append(u32(chunk.data, 4))
    return ids


def creature_page_ids(page_ids: list[int]) -> list[int]:
    return sorted({page for page in page_ids if CREATURE_PAGE_LO <= page <= CREATURE_PAGE_HI})


def _calls_in_fn(
    exe: ExeImage,
    fn_va: int,
    nbytes: int,
    cache: dict[tuple[int, int], list[int]],
) -> list[int]:
    key = (fn_va, nbytes)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        off = exe.va_to_file(fn_va)
    except ValueError:
        cache[key] = []
        return []
    calls: list[int] = []
    end = min(off + nbytes, len(exe.data) - 5)
    p = off
    while p < end:
        if exe.data[p] == 0xC3 and p > off + 16:
            break
        if exe.data[p] == 0xE8:
            rel = exe.s32(p + 1)
            va = fn_va + (p - off)
            calls.append((va + 5 + rel) & 0xFFFFFFFF)
            p += 5
            continue
        p += 1
    cache[key] = calls
    return calls


def _call_sites(exe: ExeImage, target: int) -> list[int]:
    sites: list[int] = []
    text_end = min(DGROUP_FILE, len(exe.data))
    for p in range(BEGTEXT_FILE, text_end - 5):
        if exe.data[p] != 0xE8:
            continue
        rel = exe.s32(p + 1)
        va = BEGTEXT_VA + (p - BEGTEXT_FILE)
        if ((va + 5 + rel) & 0xFFFFFFFF) == target:
            sites.append(va)
    return sites


def motion_prefix(name: str) -> str:
    match = re.match(r"^MO_([a-z0-9]+)", name, re.IGNORECASE)
    return match.group(1) if match else name


def build_clusters(
    exe: ExeImage,
    report: CreatureMap,
    page_ids: list[int],
) -> ClusterReport:
    grouped: dict[str, list[int]] = {}
    for row in report.types:
        key = ",".join(str(page) for page in row.pages) or "(none)"
        grouped.setdefault(key, []).append(row.type)
    clusters = [PageCluster(pages=pages, types=types) for pages, types in grouped.items()]
    clusters.sort(key=lambda cluster: cluster.types[0])

    by_ev: dict[int, list[SpawnHit]] = {}
    for hit in report.hits:
        by_ev.setdefault(hit.spawnEventId, []).append(hit)
    spawn_events = []
    for ev, hits in sorted(by_ev.items()):
        slots = sorted({hit.typeId for hit in hits})
        stages = sorted({hit.stage for hit in hits})
        spawn_events.append(SpawnEventHist(ev=ev, n=len(hits), slots=slots, stages=stages))

    call_sites = _call_sites(exe, FUN_TYPE_TO_MODEL)
    cache: dict[tuple[int, int], list[int]] = {}
    reaching: list[SpawnReach] = []
    spawn_base = exe.va_to_file(SPAWN_VA)
    for slot in range(SPAWN_COUNT):
        ptr = exe.u32(spawn_base + slot * 4)
        if ptr == 0:
            continue
        direct_calls = _calls_in_fn(exe, ptr, 2048, cache)
        direct = FUN_TYPE_TO_MODEL in direct_calls
        hop = direct or any(
            FUN_TYPE_TO_MODEL in _calls_in_fn(exe, call, 512, cache) for call in direct_calls
        )
        if hop:
            count = sum(1 for hit in report.hits if hit.typeId == slot)
            reaching.append(SpawnReach(slot=slot, va=f"0x{ptr:x}", n=count, direct=direct))

    prefixes: dict[str, list[str]] = {}
    for index, name in enumerate(report.motions):
        prefixes.setdefault(motion_prefix(name), []).append(f"{index}:{name}")
    motion_prefixes = [
        MotionPrefix(prefix=prefix, count=len(names), samples=names[:8])
        for prefix, names in sorted(prefixes.items(), key=lambda item: -len(item[1]))
    ]

    return ClusterReport(
        clusters=clusters,
        spawnEventIds=spawn_events,
        callSites83ad0=[f"0x{va:x}" for va in call_sites],
        spawnFnsReaching=reaching,
        creaturePages=creature_page_ids(page_ids),
        motionPrefixes=motion_prefixes,
    )


def build_more(exe: ExeImage) -> MoreReport:
    rows: list[ExtraTypeRow] = []
    type_base = exe.va_to_file(TYPE_VA)
    bone_base = exe.va_to_file(BONE_VA)
    for index in range(TYPE_COUNT, EXTRA_TYPE_COUNT):
        off = type_base + index * TYPE_STRIDE
        rows.append(
            ExtraTypeRow(
                type=index,
                model=exe.u32(off),
                hitRadius=exe.f32(off + 0x14),
                scale=exe.f32(off + 0x28),
                motion=exe.u32(off + 0x44),
                bones=exe.s32(bone_base + index * 4),
            )
        )

    fn_off = exe.va_to_file(SLOT128_FN)
    slot_hex = " ".join(f"{exe.data[fn_off + i]:02x}" for i in range(160))
    calls: list[str] = []
    for p in range(fn_off, min(fn_off + 400, len(exe.data) - 5)):
        if exe.data[p] != 0xE8:
            continue
        rel = exe.s32(p + 1)
        va = SLOT128_FN + (p - fn_off)
        target = (va + 5 + rel) & 0xFFFFFFFF
        calls.append(f"0x{va:x}->0x{target:x}")

    sample_off = exe.va_to_file(DAT_005F1DF4)
    samples: list[dict[str, float | int | str]] = []
    for i in range(20):
        samples.append(
            {
                "index": i,
                "f32": exe.f32(sample_off + i * 4),
                "u32": f"0x{exe.u32(sample_off + i * 4):x}",
            }
        )

    osm = exe.data.find(b"OSM01")
    osm_va = None
    osm_off = None
    if osm >= 0:
        osm_off = osm
        osm_va = f"0x{DGROUP_VA + (osm - DGROUP_FILE):x}"

    selected: list[str] = []
    for index in _SELECTED_TYPES:
        off = type_base + index * TYPE_STRIDE
        words: list[str] = []
        for b in range(0, TYPE_STRIDE, 4):
            raw = exe.u32(off + b)
            value = exe.f32(off + b)
            if math.isfinite(value) and 0.001 < abs(value) < 1000 and (raw & 0x7F800000) != 0:
                show = f"{value:.3f}"
            else:
                show = f"0x{raw:x}"
            words.append(f"+{b:x}={show}")
        selected.append(f"type {index}: " + " ".join(words))

    return MoreReport(
        extraRows=rows,
        slot128Hex=slot_hex,
        slot128Calls=calls,
        fieldSamples=samples,
        osm01Offset=osm_off,
        osm01Va=osm_va,
        selected=selected,
    )


def _stage_slots(hits: list[SpawnHit], stage: str, *, with_scenes: bool) -> list[StageSlotUsage]:
    grouped: dict[int, list[SpawnHit]] = {}
    for hit in hits:
        if hit.stage == stage:
            grouped.setdefault(hit.typeId, []).append(hit)
    rows: list[StageSlotUsage] = []
    for slot, group in sorted(grouped.items(), key=lambda item: -len(item[1])):
        rows.append(
            StageSlotUsage(
                slot=slot,
                count=len(group),
                eventIds=sorted({hit.spawnEventId for hit in group}),
                hps=sorted({hit.hp for hit in group}),
                scenes=sorted({hit.scene for hit in group}) if with_scenes else [],
            )
        )
    return rows


def build_hp(hits: list[SpawnHit]) -> HpReport:
    high_hits = sorted((hit for hit in hits if hit.hp >= 10), key=lambda hit: -hit.hp)
    seen: set[tuple[int, int, int, str]] = set()
    high: list[HighHpRow] = []
    for hit in high_hits:
        key = (hit.hp, hit.typeId, hit.spawnEventId, hit.stage)
        if key in seen:
            continue
        seen.add(key)
        count = sum(
            1
            for other in high_hits
            if other.hp == hit.hp
            and other.typeId == hit.typeId
            and other.spawnEventId == hit.spawnEventId
            and other.stage == hit.stage
        )
        high.append(
            HighHpRow(
                hp=hit.hp,
                typeId=hit.typeId,
                spawnEventId=hit.spawnEventId,
                stage=hit.stage,
                count=count,
                scene=hit.scene,
            )
        )

    slot128_hits = [hit for hit in hits if hit.typeId == 128 and 0 <= hit.spawnEventId < TYPE_COUNT]
    by_ev: dict[int, list[SpawnHit]] = {}
    for hit in slot128_hits:
        by_ev.setdefault(hit.spawnEventId, []).append(hit)
    slot128: list[Slot128Usage] = []
    for ev, group in sorted(by_ev.items()):
        stages: dict[str, int] = {}
        for hit in group:
            stages[hit.stage] = stages.get(hit.stage, 0) + 1
        slot128.append(
            Slot128Usage(
                spawnEventId=ev,
                count=len(group),
                hps=sorted({hit.hp for hit in group}),
                stages=stages,
            )
        )

    return HpReport(
        high=high,
        stage04=_stage_slots(hits, "Stage 04", with_scenes=True),
        stage03=_stage_slots(hits, "Stage 03", with_scenes=False),
        slot128=slot128,
    )


def write_creature_map(path: Path, report: CreatureMap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        path,
        {
            "types": report.types,
            "spawnFns": report.spawnFns,
            "spawnUsage": report.spawnUsage,
            "motions": report.motions,
            "strings": report.strings,
        },
    )


def write_clusters(path: Path, report: ClusterReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, report)
