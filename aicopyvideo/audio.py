# -*- coding: utf-8 -*-
"""用 numpy 生成无版权背景节拍，并在每个镜头切换处加一个「啵」音效。"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Iterable, List, Union

import numpy as np

SR = 44100


def _kick(rng: np.random.RandomState) -> np.ndarray:
    tt = np.arange(int(0.25 * SR)) / SR
    freq = 120 * np.exp(-tt * 25) + 45
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-tt * 14)


def _hat(rng: np.random.RandomState) -> np.ndarray:
    tt = np.arange(int(0.06 * SR)) / SR
    return rng.randn(len(tt)) * np.exp(-tt * 70) * 0.5


def _tone(freq: float, duration: float, decay: float = 6, harm=(1.0, 0.4, 0.2)) -> np.ndarray:
    tt = np.arange(int(duration * SR)) / SR
    sig = sum(h * np.sin(2 * np.pi * freq * (k + 1) * tt) for k, h in enumerate(harm))
    return sig * np.exp(-tt * decay) * np.minimum(1.0, tt * 200)


def _pop(f0: float = 700) -> np.ndarray:
    tt = np.arange(int(0.18 * SR)) / SR
    freq = f0 + 900 * np.exp(-tt * 40)
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-tt * 22)


def render_audio(
    duration: float,
    pop_times: Iterable[float],
    path: Union[str, Path],
    bpm: int = 120,
    seed: int = 1,
) -> Path:
    """生成立体声 16-bit WAV，采样率 44100。"""
    duration = float(duration)
    n = int(round(duration * SR))
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float64)
    rng = np.random.RandomState(seed)
    beat = 60.0 / bpm

    def add(sig: np.ndarray, at: float, gain: float = 1.0) -> None:
        i = int(at * SR)
        if i >= n or i < 0:
            return
        j = min(n, i + len(sig))
        out[i:j] += sig[: j - i] * gain

    kick = _kick(rng)
    hat = _hat(rng)
    bass = [110.0, 110.0, 146.83, 130.81]  # A2 A2 D3 C3
    arp = [
        [220.0, 261.63, 329.63, 392.0],
        [220.0, 293.66, 349.23, 440.0],
        [196.0, 246.94, 293.66, 392.0],
        [196.0, 261.63, 329.63, 392.0],
    ]

    nbeats = int(duration / beat)
    for b in range(nbeats):
        at = b * beat
        add(kick, at, 0.55)
        add(hat, at + beat / 2, 0.18)
        if b % 2 == 1:
            add(hat * 1.5, at, 0.10)
        bar = (b // 4) % 4
        add(_tone(bass[bar], beat * 0.9, 5, (1.0, 0.5)), at, 0.22)
        for k in range(2):
            a2 = at + k * beat / 2
            add(_tone(arp[bar][(b * 2 + k) % 4] * 2, 0.3, 9), a2, 0.09)

    pops: List[float] = sorted({0.0, *[float(x) for x in pop_times if 0 <= float(x) < duration - 0.05]})
    for i, s in enumerate(pops):
        add(_pop(900 if i % 3 == 1 else 700), s, 0.35)

    # 淡入淡出，避免爆音
    fade_in = np.minimum(1.0, t / 0.1)
    fade_out = np.minimum(1.0, np.maximum(0.0, (duration - t) / 0.6))
    out *= fade_in * fade_out
    peak = np.max(np.abs(out)) or 1.0
    out = out / peak * 0.55
    stereo = np.stack([out, out], axis=1)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767.0).astype("<i2").tobytes())
    return path
