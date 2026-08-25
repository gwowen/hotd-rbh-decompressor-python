"""
Event script bank (assets/evt/allstage/evtALL.rbh).

BODY0 (DAT_00d5a5d0):
  stagePtrs[]  — length = firstPtr/4; NULL slots allowed
    → scenePtrs[] terminated by 0xFFFFFFFF
      → sectionPtrs[] terminated by 0xFFFFFFFF
        section = opcode stream; 0xFFFFFFFF ends ENTB-style lists
        and (as the last word) the event itself.

VM: DAT_00da0ab8 is the PC. Tick at 0x4c0db0 dispatches
handlers[opcode] at 0x005eeac0. Names from exe strings at 0x5a3a00.

CCTB (0x3c) queues a camera job; job 0x40 binds camALL group + frames
(FUN_00460fd0). ENTB* operands are BODY offsets of spawn records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hotd_decompress.binary import NULL, f32, u16, u32
from hotd_decompress.jsonutil import write_json
from hotd_decompress.piff import Source
from hotd_decompress.rbh import RbhFile, load_rbh, read_pointer_table

"""Exe debug UI names (s_Stage_01_005ce918). Slot 7 is unused; 8 is extra."""
STAGE_NAMES: list[str | None] = [
    "Stage 01",
    "Stage 02",
    "Stage 03",
    "Stage 04",
    "Stage tt",
    "Stage adv",
    "Stage end",
    None,
    None,
]

"""Scene labels from PTR_s_Scene_000_005ceba4, truncated to retail scene counts."""
SCENE_NAMES: list[list[str]] = [
    [
        "Scene 000",
        "Scene 001",
        "Scene 002",
        "Scene 003",
        "Scene 01",
        "Scene 02",
        "Scene 03",
        "Scene 04",
        "Scene 05",
        "Scene 06",
        "Scene 07",
        "Scene 08",
        "Scene 09",
        "Scene 10",
        "Scene 11",
        "Scene 12",
        "Scene 13",
        "Scene 14",
        "Scene 15",
        "Scene 16",
    ],
    [
        "Scene 000",
        "Scene 001",
        "Scene 01",
        "Scene 020",
        "Scene 021",
        "Scene 03",
        "Scene 040",
        "Scene 041",
        "Scene 05",
        "Scene 06",
        "Scene 07",
        "Scene 08",
        "Scene 09",
        "Scene 10",
        "Scene 11",
        "Scene 15",
    ],
    [
        "Scene 00",
        "Scene 01",
        "Scene 02",
        "Scene 03",
        "Scene 04",
        "Scene 05",
        "Scene 06",
        "Scene 07",
    ],
    ["Scene 00", "Scene 01", "Scene 02", "Scene 02A", "Scene 03"],
    ["Scene XX", "Scene 00"],
    ["Scene 00"],
    [
        "Scene 00",
        "Scene 01",
        "Scene 02",
        "Scene 03",
        "Scene 04",
        "Scene 05",
        "Scene 06",
        "Scene 07",
    ],
]

type OpKind = Literal["op0", "op1", "op2", "list", "cctb"]


@dataclass(frozen=True)
class OpInfo:
    name: str
    kind: OpKind


OPCODES: dict[int, OpInfo] = {
    0x01: OpInfo("ET1PE", "list"),
    0x02: OpInfo("ET1P", "list"),
    0x03: OpInfo("ET1P2", "list"),
    0x04: OpInfo("ET1P3", "list"),
    0x05: OpInfo("ET2PE", "list"),
    0x06: OpInfo("ET2P", "list"),
    0x07: OpInfo("ET2P2", "list"),
    0x08: OpInfo("ET2P3", "list"),
    0x09: OpInfo("ENTBE", "list"),
    0x0A: OpInfo("ENTB", "list"),
    0x0B: OpInfo("ENTB2", "list"),
    0x0C: OpInfo("ENTB3", "list"),
    0x0D: OpInfo("SKPETO", "op1"),
    0x0E: OpInfo("SKPETU", "op1"),
    0x0F: OpInfo("SKIP", "op1"),
    0x10: OpInfo("SCNINIT", "op0"),
    0x14: OpInfo("BGTB", "op1"),
    0x1A: OpInfo("EV3JP1", "op2"),
    0x20: OpInfo("GMTMF", "op1"),
    0x21: OpInfo("GMTAD", "op1"),
    0x22: OpInfo("CLRGFST", "op0"),
    0x28: OpInfo("WLTB", "op1"),
    0x32: OpInfo("CLTB", "list"),
    0x33: OpInfo("KGTB", "list"),
    0x3C: OpInfo("CCTB", "cctb"),
    0x41: OpInfo("BSFT", "op1"),
    0x42: OpInfo("CAMDR2", "op1"),
    0x43: OpInfo("PYPMD", "op1"),
    0x44: OpInfo("SHDWLT", "op2"),
    0x45: OpInfo("CGMFNSH", "op1"),
    0x46: OpInfo("SKYKD", "op1"),
    0x47: OpInfo("SKYTB", "op1"),
    0x48: OpInfo("FKRTB", "op1"),
    0x49: OpInfo("CHGSM", "op1"),
    0x4A: OpInfo("NCHGCF", "op1"),
    0x4B: OpInfo("CAMDR", "op1"),
    0x4C: OpInfo("GGCOL", "op2"),
    0x4D: OpInfo("GGSET", "op1"),
    0x4E: OpInfo("REMFRM", "op1"),
    0x4F: OpInfo("TEXCHG", "op1"),
    0x50: OpInfo("WAIT_ENNUM", "op1"),
    0x51: OpInfo("WAIT_FRM", "op1"),
    0x52: OpInfo("WAIT_ITEM", "op1"),
    0x53: OpInfo("WAIT_CAMJOB", "op0"),
    0x54: OpInfo("WAIT_CAMFRM", "op1"),
    0x55: OpInfo("WAIT_ENALV", "op1"),
    0x57: OpInfo("RNWCJ", "op2"),
    0x58: OpInfo("ITEMON", "op1"),
    0x5A: OpInfo("SNDON", "op1"),
    0x5B: OpInfo("ATCMD", "op1"),
    0x5C: OpInfo("WAIT", "op0"),
    0x5D: OpInfo("NEXTEV", "op0"),
}

CAMERA_JOB_NAMES: dict[int, str] = {
    0x10: "flags",
    0x11: "job11",
    0x12: "callback",
    0x13: "copyTable",
    0x14: "countdown",
    0x15: "camMode",
    0x20: "poseTable",
    0x21: "camMode2",
    0x40: "rail",
}


@dataclass
class SpawnRecord:
    offset: int
    typeId: int
    flags: int | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    rx: float | None = None
    ry: float | None = None
    rz: float | None = None
    posMode: int | None = None
    unk22: int | None = None
    """Byte copied to entity+0xd4 (spawn event id)."""
    spawnEventId: int | None = None
    unk25: int | None = None
    unk26: int | None = None
    unk27: int | None = None
    """ENTB2 only: u16 at +4."""
    unk04: int | None = None


@dataclass
class CameraBind:
    job: int
    jobName: str
    args: list[int]
    """Present on job 0x40 (FUN_00460fd0)."""
    startFrame: int | None = None
    endFrame: int | None = None
    """camALL.rbh group index (0–141)."""
    camGroup: int | None = None
    flags: int | None = None


@dataclass
class EventOp:
    offset: int
    op: int
    name: str
    args: list[int]
    spawns: list[SpawnRecord] | None = None
    """CLTB/KGTB payload (ids, not spawn records)."""
    list: list[int] | None = None
    camera: CameraBind | None = None
    floats: list[float] | None = None
    unknown: bool | None = None


@dataclass
class EventSection:
    offset: int
    """Raw u32 words, including internal list terminators. Trailing event 0xFFFFFFFF omitted."""
    words: list[int]
    ops: list[EventOp]
    """Bytes after the last decoded op that were not consumed (should be empty)."""
    undecoded: list[int] | None = None


@dataclass
class EventScene:
    index: int
    offset: int
    sections: list[EventSection]
    name: str | None = None


@dataclass
class EventStage:
    index: int
    name: str | None = field(metadata={"keep_none": True})
    offset: int | None = field(metadata={"keep_none": True})
    scenes: list[EventScene]


@dataclass
class EventBank:
    stages: list[EventStage]
    path: str | None = None


def looks_like_root_table(body: bytes) -> bool:
    if len(body) < 8:
        return False
    first = u32(body, 0)
    if first == 0 or first == NULL or first % 4 != 0:
        return False
    if first > 0x400 or first >= len(body):
        return False
    return True


def read_root_with_nulls(body: bytes) -> list[int]:
    first_child = u32(body, 0)
    entries: list[int] = []
    for at in range(0, first_child, 4):
        entries.append(u32(body, at))
    return entries


def in_body(body: bytes, offset: int, size: int) -> bool:
    return offset >= 0 and offset + size <= len(body)


def cctb_word_count(job: int) -> int:
    """CCTB word count including opcode. job/16 selects the packed record size."""
    return ((job >> 4) * 4 + 8) >> 2


def parse_entb_record(body: bytes, offset: int) -> SpawnRecord | None:
    if not in_body(body, offset, 0x28):
        return None
    return SpawnRecord(
        offset=offset,
        typeId=u32(body, offset),
        flags=u32(body, offset + 4),
        x=f32(body, offset + 8),
        y=f32(body, offset + 12),
        z=f32(body, offset + 16),
        rx=f32(body, offset + 20),
        ry=f32(body, offset + 24),
        rz=f32(body, offset + 28),
        posMode=body[offset + 0x20] & 3,
        unk22=u16(body, offset + 0x22),
        spawnEventId=body[offset + 0x24],
        unk25=body[offset + 0x25],
        unk26=body[offset + 0x26],
        unk27=body[offset + 0x27],
    )


def parse_entb2_record(body: bytes, offset: int) -> SpawnRecord | None:
    if not in_body(body, offset, 8):
        return None
    return SpawnRecord(
        offset=offset,
        typeId=u32(body, offset),
        unk04=u16(body, offset + 4),
    )


def parse_entbe_record(body: bytes, offset: int) -> SpawnRecord | None:
    if not in_body(body, offset, 0x24):
        return None
    return SpawnRecord(
        offset=offset,
        typeId=u32(body, offset),
        flags=u32(body, offset + 4),
        x=f32(body, offset + 8),
        y=f32(body, offset + 12),
        z=f32(body, offset + 16),
        rx=f32(body, offset + 20),
        ry=f32(body, offset + 24),
        rz=f32(body, offset + 28),
        unk22=u16(body, offset + 0x20),
    )


def parse_spawns(body: bytes, op: int, ptrs: list[int]) -> list[SpawnRecord]:
    out: list[SpawnRecord] = []
    for ptr in ptrs:
        rec: SpawnRecord | None = None
        if op == 0x0B:
            rec = parse_entb2_record(body, ptr)
        elif op == 0x09:
            rec = parse_entbe_record(body, ptr)
        else:
            rec = parse_entb_record(body, ptr)
        if rec is not None:
            out.append(rec)
    return out


def parse_camera(job: int, args: list[int]) -> CameraBind:
    bind = CameraBind(
        job=job,
        jobName=CAMERA_JOB_NAMES.get(job, f"job{job}"),
        args=args,
    )
    if job == 0x40 and len(args) >= 4:
        bind.startFrame = args[0]
        bind.endFrame = args[1]
        bind.camGroup = args[2]
        bind.flags = args[3]
    return bind


def read_list(body: bytes, pc: int, end_offset: int) -> tuple[list[int], int]:
    values: list[int] = []
    at = pc
    while at + 4 <= end_offset:
        word = u32(body, at)
        at += 4
        if word == NULL:
            break
        values.append(word)
    return values, at


def decode_section(body: bytes, offset: int, end_offset: int) -> EventSection:
    ops: list[EventOp] = []
    pc = offset
    failed = False

    while pc + 4 <= end_offset:
        op = u32(body, pc)
        if op == NULL:
            break

        info = OPCODES.get(op)
        if info is None:
            # Not an opcode: spawn records / padding sit after the script
            # until the next section. Stop without treating them as script.
            break

        inst = EventOp(offset=pc, op=op, name=info.name, args=[])

        if info.kind == "op0":
            pc += 4
        elif info.kind == "op1":
            if pc + 8 > end_offset:
                failed = True
                break
            inst.args.append(u32(body, pc + 4))
            pc += 8
            if op == 0x28 and in_body(body, inst.args[0], 24):
                p = inst.args[0]
                inst.floats = [
                    f32(body, p),
                    f32(body, p + 4),
                    f32(body, p + 8),
                    f32(body, p + 12),
                    f32(body, p + 16),
                    f32(body, p + 20),
                ]
            if op == 0x48 and in_body(body, inst.args[0], 4):
                inst.floats = [f32(body, inst.args[0])]
        elif info.kind == "op2":
            if pc + 12 > end_offset:
                failed = True
                break
            inst.args.append(u32(body, pc + 4))
            inst.args.append(u32(body, pc + 8))
            pc += 12
        elif info.kind == "list":
            values, nxt = read_list(body, pc + 4, end_offset)
            inst.args = values
            pc = nxt
            if op in (0x32, 0x33):
                inst.list = values
            else:
                spawns = parse_spawns(body, op, values)
                if spawns:
                    inst.spawns = spawns
        elif info.kind == "cctb":
            if pc + 8 > end_offset:
                failed = True
                break
            job = u32(body, pc + 4)
            n = cctb_word_count(job)
            if n < 2 or pc + n * 4 > end_offset:
                failed = True
                break
            for i in range(2, n):
                inst.args.append(u32(body, pc + i * 4))
            inst.camera = parse_camera(job, inst.args)
            pc += n * 4
        else:
            failed = True
            break

        ops.append(inst)

    script_end = pc
    words: list[int] = []
    for at in range(offset, script_end, 4):
        if at + 4 > script_end:
            break
        word = u32(body, at)
        if word == NULL and at + 4 == script_end:
            break
        words.append(word)

    section = EventSection(offset=offset, words=words, ops=ops)
    if failed:
        leftover: list[int] = []
        for at in range(pc, end_offset, 4):
            if at + 4 > end_offset:
                break
            leftover.append(u32(body, at))
        while leftover and leftover[-1] == NULL:
            leftover.pop()
        if leftover:
            section.undecoded = leftover
            ops.append(
                EventOp(
                    offset=pc,
                    op=leftover[0],
                    name="unknown",
                    args=leftover[1:],
                    unknown=True,
                )
            )
    return section


def next_bound(sorted_offs: list[int], offset: int, body_len: int) -> int:
    for at in sorted_offs:
        if at > offset:
            return at
    return body_len


def parse_event_bank(file: RbhFile) -> EventBank:
    if len(file.bodies) != 1:
        raise ValueError(f"Expected 1 BODY for event bank, got {len(file.bodies)}")
    body = file.bodies[0].data
    if not looks_like_root_table(body):
        raise ValueError("BODY does not look like an event stage pointer table")

    stage_ptrs = read_root_with_nulls(body)

    @dataclass
    class SceneSkel:
        index: int
        offset: int
        section_ptrs: list[int]
        name: str | None = None

    @dataclass
    class StageSkel:
        index: int
        name: str | None
        offset: int | None
        scenes: list[SceneSkel]

    skeleton: list[StageSkel] = []
    all_section_offs: list[int] = []

    for i, ptr in enumerate(stage_ptrs):
        name = STAGE_NAMES[i] if i < len(STAGE_NAMES) else None
        if ptr == NULL:
            skeleton.append(StageSkel(index=i, name=name, offset=None, scenes=[]))
            continue
        scene_ptrs = read_pointer_table(body, ptr).entries
        scene_names = SCENE_NAMES[i] if i < len(SCENE_NAMES) else None
        scenes: list[SceneSkel] = []
        for si, sp in enumerate(scene_ptrs):
            section_ptrs = read_pointer_table(body, sp).entries
            all_section_offs.extend(section_ptrs)
            scene_name = None
            if scene_names is not None and si < len(scene_names) and scene_names[si]:
                scene_name = scene_names[si]
            scenes.append(
                SceneSkel(index=si, offset=sp, section_ptrs=section_ptrs, name=scene_name)
            )
        skeleton.append(StageSkel(index=i, name=name, offset=ptr, scenes=scenes))

    sorted_offs = sorted(set(all_section_offs))
    stages = [
        EventStage(
            index=st.index,
            name=st.name,
            offset=st.offset,
            scenes=[
                EventScene(
                    index=sc.index,
                    name=sc.name,
                    offset=sc.offset,
                    sections=[
                        decode_section(body, ptr, next_bound(sorted_offs, ptr, len(body)))
                        for ptr in sc.section_ptrs
                    ],
                )
                for sc in st.scenes
            ],
        )
        for st in skeleton
    ]

    return EventBank(path=file.path, stages=stages)


def extract_events(source: Source) -> EventBank:
    return parse_event_bank(load_rbh(source))


@dataclass
class WriteEventsResult:
    bank: EventBank
    written: list[str]
    opCount: int
    spawnCount: int
    railBindCount: int
    undecodedWords: int


def count_ops(bank: EventBank) -> tuple[int, int, int, int]:
    ops = 0
    spawns = 0
    rails = 0
    undecoded = 0
    for st in bank.stages:
        for sc in st.scenes:
            for sec in sc.sections:
                ops += len(sec.ops)
                if sec.undecoded is not None:
                    undecoded += len(sec.undecoded)
                for inst in sec.ops:
                    if inst.spawns is not None:
                        spawns += len(inst.spawns)
                    if inst.camera is not None and inst.camera.camGroup is not None:
                        rails += 1
    return ops, spawns, rails, undecoded


def convert_events_to_json(source: Source, out_dir: str) -> WriteEventsResult:
    """Write events.json under outDir."""
    bank = extract_events(source)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ops, spawns, rails, undecoded = count_ops(bank)

    payload = {
        "source": bank.path,
        "stageCount": len(bank.stages),
        "opCount": ops,
        "spawnCount": spawns,
        "railBindCount": rails,
        "undecodedWords": undecoded,
        "stages": bank.stages,
    }

    path = str(Path(out_dir) / "events.json")
    write_json(path, payload)
    return WriteEventsResult(
        bank=bank,
        written=[path],
        opCount=ops,
        spawnCount=spawns,
        railBindCount=rails,
        undecodedWords=undecoded,
    )
