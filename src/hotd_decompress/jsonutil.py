"""JSON dump that omits unset optional dataclass fields (TS undefined)."""

from __future__ import annotations

import json
import math
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, float):
        # JSON.stringify(NaN/Infinity) is null.
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in fields(obj):
            value = getattr(obj, f.name)
            if value is None and not f.metadata.get("keep_none"):
                continue
            out[f.name] = to_jsonable(value)
        return out
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


def dumps(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), indent=2, allow_nan=False) + "\n"


def write_json(path: str | Path, obj: Any) -> None:
    Path(path).write_text(dumps(obj), encoding="utf-8")
