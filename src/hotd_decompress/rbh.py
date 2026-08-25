"""House of the Dead / Tantalus-style RBH container (PIFF/RBHF)."""

from __future__ import annotations

from dataclasses import dataclass

from hotd_decompress.binary import NULL, u32
from hotd_decompress.piff import PiffChunk, PiffFile, Source, load_piff

RbhChunk = PiffChunk


@dataclass(frozen=True)
class RbhHeaderEntry:
    """Unknown; usually 0."""
    field0: int
    """Size of the corresponding BODY payload."""
    bodySize: int
    """Type/flag; 0 for many sounds, 2 for evt/cam/art/sprite."""
    flags: int


@dataclass(frozen=True)
class RbhFile:
    byteLength: int
    form: str
    header: list[RbhHeaderEntry]
    chunks: list[RbhChunk]
    bodies: list[RbhChunk]
    packs: list[RbhChunk]
    relocations: list[RbhChunk]
    path: str | None = None


@dataclass(frozen=True)
class PointerTable:
    offset: int
    entries: list[int]


@dataclass
class RbhContentsSummary:
    file: RbhFile
    header: list[RbhHeaderEntry]
    bodyCount: int
    packCount: int
    relocationCount: int
    relocationEntries: int
    """For BODY blobs that start with null-terminated pointer tables (evt/cam-like)."""
    rootTables: list[PointerTable]
    description: str


def parse_header_entries(payload: bytes) -> list[RbhHeaderEntry]:
    if len(payload) % 12 != 0:
        raise ValueError(f"RBHH size {len(payload)} is not a multiple of 12")

    entries: list[RbhHeaderEntry] = []
    for i in range(0, len(payload), 12):
        entries.append(
            RbhHeaderEntry(
                field0=u32(payload, i),
                bodySize=u32(payload, i + 4),
                flags=u32(payload, i + 8),
            )
        )
    return entries


def from_piff(piff: PiffFile) -> RbhFile:
    if piff.form != "RBHF":
        raise ValueError(f"Expected RBHF form, got {piff.form!r}")

    rbhh = next((c for c in piff.chunks if c.tag == "RBHH"), None)
    if rbhh is None:
        raise ValueError("Missing RBHH chunk")

    return RbhFile(
        path=piff.path,
        byteLength=piff.byteLength,
        form=piff.form,
        header=parse_header_entries(rbhh.data),
        chunks=piff.chunks,
        bodies=[c for c in piff.chunks if c.tag == "BODY"],
        packs=[c for c in piff.chunks if c.tag == "PACK"],
        relocations=[c for c in piff.chunks if c.tag == "RELC"],
    )


def load_rbh(source: Source) -> RbhFile:
    """Load and parse an RBH container from a path or raw bytes."""
    return from_piff(load_piff(source))


def read_pointer_table(
    body: bytes,
    offset: int,
    *,
    max_entries: int = 4096,
    require_in_body: bool = True,
) -> PointerTable:
    """
    Read a null-terminated list of BODY-relative u32 pointers.
    Stops at 0xFFFFFFFF or when a value falls outside the BODY.
    """
    entries: list[int] = []

    for i in range(max_entries):
        at = offset + i * 4
        if at + 4 > len(body):
            break

        value = u32(body, at)
        if value == NULL:
            break
        if require_in_body and value >= len(body):
            break

        entries.append(value)

    return PointerTable(offset=offset, entries=entries)


def count_relocation_entries(relc: RbhChunk) -> int:
    count = 0
    for i in range(0, len(relc.data) - 3, 4):
        if u32(relc.data, i) != 0:
            count += 1
    return count


def looks_like_root_pointer_table(body: bytes) -> bool:
    if len(body) < 8:
        return False
    first = u32(body, 0)
    if first == 0 or first == NULL or first >= len(body):
        return False
    if first % 4 != 0:
        return False
    # Root tables in evt/cam typically point just past themselves.
    return first <= 0x400


def read_root_pointer_table(body: bytes) -> PointerTable | None:
    """
    Root tables can contain NULL slots mid-list. Their length is implied by the
    first non-null child offset (the child table begins immediately after).
    """
    if not looks_like_root_pointer_table(body):
        return None

    first_child = u32(body, 0)
    entries: list[int] = []

    for at in range(0, first_child, 4):
        value = u32(body, at)
        if value != NULL and value >= len(body):
            return None
        entries.append(value)

    return PointerTable(offset=0, entries=entries)


def summarize_root_tables(body: bytes) -> list[PointerTable]:
    root = read_root_pointer_table(body)
    if root is None:
        return []

    tables: list[PointerTable] = [root]

    for entry in root.entries:
        if entry == NULL:
            tables.append(PointerTable(offset=entry, entries=[]))
            continue
        tables.append(read_pointer_table(body, entry))

    return tables


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def describe_rbh(file: RbhFile) -> RbhContentsSummary:
    """Inspect a loaded RBH and produce a human-readable contents summary."""
    relocation_entries = sum(count_relocation_entries(chunk) for chunk in file.relocations)

    root_tables = summarize_root_tables(file.bodies[0].data) if len(file.bodies) == 1 else []

    lines: list[str] = []
    name = file.path if file.path is not None else "(buffer)"

    lines.append(f"RBH: {name}")
    lines.append(f"  size: {file.byteLength} bytes ({format_bytes(file.byteLength)})")
    lines.append(f"  form: {file.form}")
    lines.append(f"  chunks: {', '.join(f'{c.tag}({c.size})' for c in file.chunks)}")

    for i, entry in enumerate(file.header):
        lines.append(
            f"  RBHH[{i}]: bodySize={entry.bodySize}, flags={entry.flags}, field0={entry.field0}"
        )

    for i, body in enumerate(file.bodies):
        lines.append(f"  BODY[{i}] @ 0x{body.offset:x}: {body.size} bytes")

    for i, pack in enumerate(file.packs):
        lines.append(f"  PACK[{i}] @ 0x{pack.offset:x}: {pack.size} bytes (compressed)")

    for i, relc in enumerate(file.relocations):
        entries = count_relocation_entries(relc)
        lines.append(
            f"  RELC[{i}] @ 0x{relc.offset:x}: {relc.size} bytes, {entries} relocation offsets"
        )

    if root_tables:
        root = root_tables[0]
        groups = sum(1 for e in root.entries if e != NULL)
        nulls = len(root.entries) - groups
        lines.append(
            f"  pointer root: {len(root.entries)} slots ({groups} groups, {nulls} null)"
        )

        max_listed = 16
        child_tables = root_tables[1:]
        listed = child_tables[:max_listed]

        for i, table in enumerate(listed):
            root_entry = root.entries[i]
            if root_entry == NULL:
                lines.append(f"    group[{i}]: NULL")
                continue
            lines.append(
                f"    group[{i}] @ 0x{table.offset:x}: {len(table.entries)} entries"
            )

        if len(child_tables) > max_listed:
            remaining = len(child_tables) - max_listed
            remaining_entries = sum(len(t.entries) for t in child_tables[max_listed:])
            lines.append(f"    … {remaining} more groups ({remaining_entries} entries)")

    return RbhContentsSummary(
        file=file,
        header=file.header,
        bodyCount=len(file.bodies),
        packCount=len(file.packs),
        relocationCount=len(file.relocations),
        relocationEntries=relocation_entries,
        rootTables=root_tables,
        description="\n".join(lines),
    )


def inspect_rbh(source: Source) -> RbhContentsSummary:
    """Load an RBH file and return a contents summary."""
    return describe_rbh(load_rbh(source))
