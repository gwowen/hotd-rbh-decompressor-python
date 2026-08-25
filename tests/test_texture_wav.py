from __future__ import annotations

from hotd_decompress.texture import TEXTURE_CLEAR, rgb555_to_rgba
from hotd_decompress.wav import encode_wav_pcm8_mono


def test_rgb555_clear_colors() -> None:
    assert rgb555_to_rgba(0) == (0, 0, 0, 0)
    assert rgb555_to_rgba(TEXTURE_CLEAR) == (0, 0, 0, 0)


def test_rgb555_opaque() -> None:
    # Full red in RGB555 (0x7C00) plus 0x8000 engine bit.
    r, g, b, a = rgb555_to_rgba(0xFC00)
    assert a == 255
    assert r == 255
    assert g == 0
    assert b == 0


def test_wav_header_layout() -> None:
    pcm = bytes([0x80, 0x81, 0x7F])
    wav = encode_wav_pcm8_mono(pcm, 11025)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav[36:40] == b"data"
    assert wav[44:] == pcm
    assert len(wav) == 44 + len(pcm)
