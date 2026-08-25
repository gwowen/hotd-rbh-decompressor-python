"""
Stage / creature mesh RBHF (world*.rbh, CREAT*.rbh).

Container (FUN_00419cac / FUN_00419cf4 → FUN_005769c0):
  RBHH flags 2,0,0 → BODY0 graph + id table, BODY1 f32×3 verts, BODY2 empty
  RELC0 patches BODY0; RELC1 marks vertBase fields (offsets into BODY1)

Creat id table: 8-byte {s16 id, s16 flag, u32 nodePtr} until id == -1
World id table: {s16 id, s16 flag, u32 nodePtrs... 0} until id == 0

Mesh node:
  +0x00 u32 link0
  +0x04 u32 vertBase   // byte offset into BODY1
  +0x08 u32 link2
  +0x0C u32 pad
  +0x10 u32 fieldA
  +0x14 u32 fieldC
  +0x18 f32 scale
  +0x1C u16 unk, u16 0xFFFF
  World only: +0x20 f32 posX,Y,Z then batches at +0x2C
  Creat: batches at +0x20

Prim batches (FUN_00578bb0): header u16 count, flags, unk, sizeShorts
  kind = flags & 0x2007
    0      plain tri   (4 shorts)
    2      textured tri (18 shorts / 36 B)
    0x2001 plain quad  (5 shorts)
    0x2004 textured quad (22 shorts / 44 B)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hotd_decompress.binary import f32, s16, u16, u32
from hotd_decompress.jsonutil import write_json
from hotd_decompress.piff import Source
from hotd_decompress.rbh import RbhFile, load_rbh

"""VVTP pages are 256×256; UVs in prims are pixel coords."""
MESH_PAGE_SIZE = 256

type MeshKind = Literal["creat", "world"]


@dataclass
class MeshIdEntry:
    id: int
    flag: int
    nodeOffsets: list[int]


@dataclass
class MeshVertex:
    x: float
    y: float
    z: float


@dataclass
class MeshUv:
    u: float
    v: float


@dataclass
class MeshPrim:
    type: Literal["tri", "quad"]
    textured: bool
    indices: list[int]
    texPageId: int | None = None
    uvs: list[MeshUv] | None = None


@dataclass
class MeshBatch:
    offset: int
    count: int
    flags: int
    kind: int
    prims: list[MeshPrim]


@dataclass
class MeshNode:
    offset: int
    vertBase: int
    scale: float
    position: MeshVertex | None
    fieldA: int
    fieldC: int
    batches: list[MeshBatch]
    """Local vertex slice referenced by this node's indices."""
    vertices: list[MeshVertex]


@dataclass
class MeshBank:
    kind: MeshKind
    ids: list[MeshIdEntry]
    nodes: list[MeshNode]
    path: str | None = None


PRIM_SHORTS: dict[int, int] = {
    0: 4,
    1: 4,
    2: 0x12,
    0x2001: 5,
    0x2004: 0x16,
}


def is_mesh_rbh(file: RbhFile) -> bool:
    """True if this RBH matches the world/CREAT 3-BODY mesh container."""
    if len(file.header) < 2 or len(file.bodies) < 2:
        return False
    if file.header[0].flags != 2:
        return False
    if file.header[1].flags != 0:
        return False
    # BODY1 should be a multiple of 12 (float3 pool).
    return len(file.bodies[1].data) % 12 == 0


def try_parse_creat_ids(body: bytes) -> list[MeshIdEntry] | None:
    ids: list[MeshIdEntry] = []
    for o in range(0, len(body) - 7, 8):
        id_ = s16(body, o)
        if id_ == -1:
            return ids if ids else None
        flag = s16(body, o + 2)
        ptr = u32(body, o + 4)
        if ptr == 0 or ptr >= len(body):
            return None
        ids.append(MeshIdEntry(id=id_, flag=flag, nodeOffsets=[ptr]))
    return None


def try_parse_world_ids(body: bytes) -> list[MeshIdEntry] | None:
    ids: list[MeshIdEntry] = []
    o = 0
    while o + 8 <= len(body):
        id_ = s16(body, o)
        if id_ == 0:
            return ids if ids else None
        flag = s16(body, o + 2)
        o += 4
        node_offsets: list[int] = []
        while o + 4 <= len(body):
            ptr = u32(body, o)
            o += 4
            if ptr == 0:
                break
            if ptr >= len(body):
                return None
            node_offsets.append(ptr)
        ids.append(MeshIdEntry(id=id_, flag=flag, nodeOffsets=node_offsets))
        if len(ids) > 100_000:
            return None
    return None


def detect_kind(body0: bytes) -> tuple[MeshKind, list[MeshIdEntry]]:
    creat = try_parse_creat_ids(body0)
    if creat is not None:
        return ("creat", creat)

    world = try_parse_world_ids(body0)
    if world is not None:
        return ("world", world)

    raise ValueError("Unrecognized mesh id table (not creat or world)")


def read_vertex_pool(body1: bytes) -> list[MeshVertex]:
    verts: list[MeshVertex] = []
    for o in range(0, len(body1) - 11, 12):
        verts.append(
            MeshVertex(
                x=f32(body1, o),
                y=f32(body1, o + 4),
                z=f32(body1, o + 8),
            )
        )
    return verts


def parse_textured_tri(data: bytes, offset: int) -> MeshPrim:
    return MeshPrim(
        type="tri",
        textured=True,
        indices=[
            u16(data, offset),
            u16(data, offset + 2),
            u16(data, offset + 4),
        ],
        texPageId=u16(data, offset + 6),
        uvs=[
            MeshUv(u=f32(data, offset + 12), v=f32(data, offset + 16)),
            MeshUv(u=f32(data, offset + 20), v=f32(data, offset + 24)),
            MeshUv(u=f32(data, offset + 28), v=f32(data, offset + 32)),
        ],
    )


def parse_textured_quad(data: bytes, offset: int) -> MeshPrim:
    return MeshPrim(
        type="quad",
        textured=True,
        indices=[
            u16(data, offset),
            u16(data, offset + 2),
            u16(data, offset + 4),
            u16(data, offset + 6),
        ],
        texPageId=u16(data, offset + 8),
        uvs=[
            MeshUv(u=f32(data, offset + 12), v=f32(data, offset + 16)),
            MeshUv(u=f32(data, offset + 20), v=f32(data, offset + 24)),
            MeshUv(u=f32(data, offset + 28), v=f32(data, offset + 32)),
            MeshUv(u=f32(data, offset + 36), v=f32(data, offset + 40)),
        ],
    )


def parse_plain_tri(data: bytes, offset: int) -> MeshPrim:
    return MeshPrim(
        type="tri",
        textured=False,
        indices=[
            u16(data, offset),
            u16(data, offset + 2),
            u16(data, offset + 4),
        ],
    )


def parse_plain_quad(data: bytes, offset: int) -> MeshPrim:
    return MeshPrim(
        type="quad",
        textured=False,
        indices=[
            u16(data, offset),
            u16(data, offset + 2),
            u16(data, offset + 4),
            u16(data, offset + 6),
        ],
    )


def parse_batches(body0: bytes, start: int) -> list[MeshBatch]:
    batches: list[MeshBatch] = []
    p = start

    while p + 8 <= len(body0):
        count = u16(body0, p)
        if count == 0:
            break

        flags = u16(body0, p + 2)
        size_shorts = s16(body0, p + 6)
        if size_shorts < 0:
            break

        kind = flags & 0x2007
        prim_shorts = PRIM_SHORTS.get(kind)
        payload_start = p + 8
        payload_bytes = size_shorts * 2

        if payload_start + payload_bytes > len(body0):
            raise ValueError(f"Batch @ 0x{p:x} payload extends past BODY0")

        prims: list[MeshPrim] = []
        if prim_shorts is not None and count > 0:
            for i in range(count):
                at = payload_start + i * prim_shorts * 2
                if at + prim_shorts * 2 > payload_start + payload_bytes:
                    break
                if kind in (0, 1):
                    prims.append(parse_plain_tri(body0, at))
                elif kind == 2:
                    prims.append(parse_textured_tri(body0, at))
                elif kind == 0x2001:
                    prims.append(parse_plain_quad(body0, at))
                elif kind == 0x2004:
                    prims.append(parse_textured_quad(body0, at))

        batches.append(MeshBatch(offset=p, count=count, flags=flags, kind=kind, prims=prims))
        p = payload_start + payload_bytes
        if len(batches) > 100_000:
            break

    return batches


def max_index_used(batches: list[MeshBatch]) -> int:
    max_idx = -1
    for batch in batches:
        for prim in batch.prims:
            for idx in prim.indices:
                if idx > max_idx:
                    max_idx = idx
    return max_idx


def parse_node(body0: bytes, pool: list[MeshVertex], offset: int, kind: MeshKind) -> MeshNode:
    if offset + 0x20 > len(body0):
        raise ValueError(f"Node @ 0x{offset:x} truncated (header)")

    vert_base = u32(body0, offset + 4)
    field_a = u32(body0, offset + 0x10)
    field_c = u32(body0, offset + 0x14)
    scale = f32(body0, offset + 0x18)

    position: MeshVertex | None = None
    batch_start = offset + 0x20
    batches: list[MeshBatch] = []

    if kind == "world":
        # Some id-table tails point at header-only stubs (no pose / prims).
        if offset + 0x2C <= len(body0):
            position = MeshVertex(
                x=f32(body0, offset + 0x20),
                y=f32(body0, offset + 0x24),
                z=f32(body0, offset + 0x28),
            )
            batch_start = offset + 0x2C
            batches = parse_batches(body0, batch_start)
    else:
        batches = parse_batches(body0, batch_start)

    max_idx = max_index_used(batches)
    vert_base_index = vert_base // 12
    if vert_base % 12 != 0:
        raise ValueError(f"Node @ 0x{offset:x} vertBase 0x{vert_base:x} not aligned")

    vertices: list[MeshVertex] = []
    for i in range(max_idx + 1):
        pool_index = vert_base_index + i
        if pool_index >= len(pool):
            raise ValueError(
                f"Node @ 0x{offset:x} vertex {i} (pool {pool_index}) out of range"
            )
        vertices.append(pool[pool_index])

    return MeshNode(
        offset=offset,
        vertBase=vert_base,
        scale=scale,
        position=position,
        fieldA=field_a,
        fieldC=field_c,
        batches=batches,
        vertices=vertices,
    )


def parse_mesh_bank(file: RbhFile) -> MeshBank:
    if not is_mesh_rbh(file):
        raise ValueError("Not a world/CREAT mesh RBH container")

    body0 = file.bodies[0].data
    body1 = file.bodies[1].data
    kind, ids = detect_kind(body0)
    pool = read_vertex_pool(body1)

    unique_offsets = sorted({off for entry in ids for off in entry.nodeOffsets})
    nodes = [parse_node(body0, pool, off, kind) for off in unique_offsets]

    return MeshBank(path=file.path, kind=kind, ids=ids, nodes=nodes)


def extract_meshes(source: Source) -> MeshBank:
    return parse_mesh_bank(load_rbh(source))


def _js_num(n: float) -> str:
    if math.isnan(n):
        return "NaN"
    if math.isinf(n):
        return "Infinity" if n > 0 else "-Infinity"
    if n == 0:
        return "-0" if math.copysign(1.0, n) < 0 else "0"
    as_int = int(n)
    if n == as_int and abs(as_int) < 10**15:
        return str(as_int)
    return json.dumps(n)


def encode_obj(node: MeshNode, name: str) -> str:
    lines: list[str] = [f"# hotd-viewer mesh {name}", f"o {name}"]
    if node.position is not None:
        px, py, pz = node.position.x, node.position.y, node.position.z
        lines.append(f"# position {_js_num(px)} {_js_num(py)} {_js_num(pz)}")
    lines.append(f"# scale {_js_num(node.scale)}")

    # World BODY1 verts are already in stage space; +0x20 is metadata (not a bake transform).
    for v in node.vertices:
        lines.append(f"v {_js_num(v.x)} {_js_num(v.y)} {_js_num(v.z)}")

    # Emit unique VT entries in encounter order; faces reference 1-based indices.
    vt_index: dict[tuple[float, float], int] = {}
    vt_list: list[str] = []
    faces: list[str] = []
    current_mtl: str | None = None

    for batch in node.batches:
        for prim in batch.prims:
            if prim.textured:
                assert prim.uvs is not None and prim.texPageId is not None
                mtl = f"page_{prim.texPageId}"
                if mtl != current_mtl:
                    faces.append(f"usemtl {mtl}")
                    current_mtl = mtl
                corners: list[str] = []
                for i, vi0 in enumerate(prim.indices):
                    vi = vi0 + 1
                    uv = prim.uvs[i]
                    key = (uv.u, uv.v)
                    ti = vt_index.get(key)
                    if ti is None:
                        ti = len(vt_list) + 1
                        vt_index[key] = ti
                        # OBJ V grows downward; HotD pixel V grows downward on the page too.
                        vt_list.append(
                            f"vt {_js_num(uv.u / MESH_PAGE_SIZE)} "
                            f"{_js_num((MESH_PAGE_SIZE - uv.v) / MESH_PAGE_SIZE)}"
                        )
                    corners.append(f"{vi}/{ti}")
                faces.append("f " + " ".join(corners))
            else:
                if current_mtl is not None:
                    faces.append("usemtl none")
                    current_mtl = None
                faces.append("f " + " ".join(str(i + 1) for i in prim.indices))

    lines.extend(vt_list)
    lines.extend(faces)
    lines.append("")
    return "\n".join(lines)


@dataclass
class WriteMeshesResult:
    bank: MeshBank
    written: list[str]


def convert_meshes_to_obj(source: Source, out_dir: str) -> WriteMeshesResult:
    """
    Export mesh bank: ids.json + one .obj per unique node.
    → decompressed_assets/<stem>_mesh/
    """
    bank = extract_meshes(source)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    ids_payload = {
        "source": bank.path,
        "kind": bank.kind,
        "idCount": len(bank.ids),
        "nodeCount": len(bank.nodes),
        "ids": [
            {
                "id": entry.id,
                "flag": entry.flag,
                "nodes": [
                    {
                        "offset": off,
                        "file": f"node_{off:06x}.obj",
                    }
                    for off in entry.nodeOffsets
                ],
            }
            for entry in bank.ids
        ],
        "nodes": [
            {
                "offset": node.offset,
                "file": f"node_{node.offset:06x}.obj",
                "vertBase": node.vertBase,
                "scale": node.scale,
                "position": (
                    {"x": node.position.x, "y": node.position.y, "z": node.position.z}
                    if node.position is not None
                    else None
                ),
                "vertexCount": len(node.vertices),
                "batchCount": len(node.batches),
                "primCount": sum(len(b.prims) for b in node.batches),
            }
            for node in bank.nodes
        ],
    }

    ids_path = str(Path(out_dir) / "ids.json")
    write_json(ids_path, ids_payload)
    written.append(ids_path)

    for node in bank.nodes:
        stem = f"node_{node.offset:06x}"
        obj_path = str(Path(out_dir) / f"{stem}.obj")
        Path(obj_path).write_text(encode_obj(node, stem), encoding="utf-8")
        written.append(obj_path)

    return WriteMeshesResult(bank=bank, written=written)
