from __future__ import annotations

import json
import math

from hotd_decompress.jsonutil import dumps, to_jsonable


def test_nan_and_inf_become_null() -> None:
    payload = {"x": math.nan, "y": math.inf, "z": -math.inf, "ok": 1.5}
    converted = to_jsonable(payload)
    assert converted["x"] is None
    assert converted["y"] is None
    assert converted["z"] is None
    assert converted["ok"] == 1.5
    parsed = json.loads(dumps(payload))
    assert parsed["x"] is None
    assert parsed["ok"] == 1.5
