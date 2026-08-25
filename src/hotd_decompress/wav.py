"""Minimal PCM WAV writer (little-endian RIFF)."""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class WavPcmFormat:
    sampleRate: int
    channels: int
    """Bytes per sample per channel (1 = 8-bit unsigned, 2 = 16-bit signed)."""
    bytesPerSample: int


def encode_wav(pcm: bytes, format: WavPcmFormat) -> bytes:
    """Encode raw PCM samples as a WAV file."""
    sample_rate = format.sampleRate
    channels = format.channels
    bytes_per_sample = format.bytesPerSample
    if channels < 1 or channels > 2:
        raise ValueError(f"Unsupported channel count {channels}")
    if bytes_per_sample not in (1, 2):
        raise ValueError(f"Unsupported sample width {bytes_per_sample}")
    if len(pcm) % (channels * bytes_per_sample) != 0:
        raise ValueError(
            f"PCM size {len(pcm)} is not a multiple of frame size {channels * bytes_per_sample}"
        )

    block_align = channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    bits_per_sample = bytes_per_sample * 8
    # 8-bit PCM is unsigned; 16-bit is signed little-endian.
    audio_format = 1  # WAVE_FORMAT_PCM

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        audio_format,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        len(pcm),
    )
    return header + pcm


def encode_wav_pcm8_mono(pcm: bytes, sample_rate: int) -> bytes:
    """Encode unsigned 8-bit mono PCM (HotD SFX default)."""
    return encode_wav(
        pcm,
        WavPcmFormat(sampleRate=sample_rate, channels=1, bytesPerSample=1),
    )
