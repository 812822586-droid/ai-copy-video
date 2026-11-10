# -*- coding: utf-8 -*-
"""用 Pillow 逐帧绘制、ffmpeg 合成为 H.264 + AAC 视频，并生成封面 PNG。

画面结构（默认 15 秒竖屏 1080x1920 @ 30fps）：
  0 ~ hook_dur          钩子句（大标题 + 橙色副标题胶囊）
  之后每个要点约 3 秒    进度点 + 标题 + 右侧聊天气泡打字效果
  最后 outro_dur        回顾要点 + 可配置结尾句（默认「关注我，带你用AI做副业」）

深蓝背景、橙色点缀、滑入/淡入。不使用任何公司 Logo，也不模仿其他软件界面。
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .fonts import load_font

NAVY_TOP = np.array([8, 14, 38], dtype=np.float64)
NAVY_BOT = np.array([22, 34, 82], dtype=np.float64)
ACC = (255, 98, 52)
ACC2 = (255, 170, 60)
WHITE = (255, 255, 255)
GREY = (160, 172, 200)
DOT_OFF = (60, 72, 110)
REPLY_BG = (44, 58, 105)
CARD_BG = (36, 50, 100)
DOT_IDLE = (210, 220, 245)


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1.0 - (1.0 - x) ** 3


def back_ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    c = 1.70158
    return 1.0 + (c + 1.0) * (x - 1.0) ** 3 + c * (x - 1.0) ** 2


@dataclass
class Layout:
    width: int
    height: int
    margin: int
    tag_y: int
    tag_size: int
    dots_y: int
    title_y: int
    title_size: int
    line_y: int
    chat_y: int
    chat_size: int
    hook_y: int
    hook_size: int
    sub_size: int
    cta_size: int
    recap_size: int
    recap_y: int
    cta_y: int
    max_title_w: int
    max_hook_w: int
    max_chat_w: int
    max_cta_w: int
    line_h_chat: int
    bubble_pad_x: int
    bubble_pad_y: int
    bubble_radius: int
    portrait: bool


def make_layout(width: int, height: int) -> Layout:
    portrait = height >= width
    if portrait:
        # 以 1080x1920 为基准按比例缩放
        sx = width / 1080.0
        sy = height / 1920.0
        s = min(sx, sy)
        return Layout(
            width=width,
            height=height,
            margin=int(90 * sx),
            tag_y=int(170 * sy),
            tag_size=max(28, int(40 * s)),
            dots_y=int(330 * sy),
            title_y=int(500 * sy),
            title_size=max(40, int(72 * s)),
            line_y=int(640 * sy),
            chat_y=int(760 * sy),
            chat_size=max(32, int(50 * s)),
            hook_y=int(740 * sy),
            hook_size=max(52, int(110 * s)),
            sub_size=max(36, int(72 * s)),
            cta_size=max(36, int(68 * s)),
            recap_size=max(28, int(44 * s)),
            recap_y=int(480 * sy),
            cta_y=int(1280 * sy),
            max_title_w=int(width - 180 * sx),
            max_hook_w=int(width - 180 * sx),
            max_chat_w=int(760 * sx),
            max_cta_w=int(width - 200 * sx),
            line_h_chat=int(78 * s),
            bubble_pad_x=int(40 * s),
            bubble_pad_y=int(22 * s),
            bubble_radius=int(48 * s),
            portrait=True,
        )
    # 横屏 1920x1080：上下空间更紧，字号略放大、纵向压缩
    sx = width / 1920.0
    sy = height / 1080.0
    s = min(sx, sy)
    return Layout(
        width=width,
        height=height,
        margin=int(80 * sx),
        tag_y=int(70 * sy),
        tag_size=max(24, int(32 * s)),
        dots_y=int(145 * sy),
        title_y=int(210 * sy),
        title_size=max(32, int(48 * s)),
        line_y=int(300 * sy),
        chat_y=int(360 * sy),
        chat_size=max(28, int(40 * s)),
        hook_y=int(380 * sy),
        hook_size=max(40, int(72 * s)),
        sub_size=max(28, int(48 * s)),
        cta_size=max(28, int(44 * s)),
        recap_size=max(24, int(32 * s)),
        recap_y=int(200 * sy),
        cta_y=int(820 * sy),
        max_title_w=int(width - 200 * sx),
        max_hook_w=int(width - 240 * sx),
        max_chat_w=int(1100 * sx),
        max_cta_w=int(width - 260 * sx),
        line_h_chat=int(60 * s),
        bubble_pad_x=int(36 * s),
        bubble_pad_y=int(16 * s),
        bubble_radius=int(36 * s),
        portrait=False,
    )


@dataclass
class VideoSpec:
    topic: str
    hook: str
    sub: str
    points: Sequence[str]
    outro: str = "关注我，带你用AI做副业"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration: float = 15.0
    font_bold: str = ""
    font_regular: str = ""
    crf: int = 20
    tag: Optional[str] = None  # 左上角小字，默认用主题名


def scene_times(duration: float, n_points: int) -> List[Tuple[float, float]]:
    """返回各镜头的 (start, end)。钩子略短、结尾留足 CTA 时间，中间均分给要点。"""
    duration = float(duration)
    n_points = max(1, int(n_points))
    hook = min(2.2, duration * 2.2 / 15.0)
    outro = min(2.6, duration * 2.6 / 15.0)
    # 太短的视频也至少给钩子和结尾各 1.2 秒
    hook = max(1.2, hook)
    outro = max(1.2, outro)
    if hook + outro >= duration * 0.7:
        hook = duration * 0.18
        outro = duration * 0.20
    remain = max(0.8, duration - hook - outro)
    step = remain / n_points
    t = 0.0
    scenes = [(0.0, hook)]
    t = hook
    for _ in range(n_points):
        scenes.append((t, t + step))
        t += step
    scenes.append((t, duration))
    # 修正浮点尾巴
    s, _ = scenes[-1]
    scenes[-1] = (s, duration)
    return scenes


_BREAK_AFTER = set("，。、；：！？,;!?、 ")


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    """按宽度折行；若必须断开，优先在逗号、句号等标点之后断开，避免单字落行。"""
    lines: List[str] = []
    cur = ""
    for ch in text.replace("\r", ""):
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if cur and draw.textlength(trial, font=font) > max_w:
            break_at = -1
            for i in range(len(cur) - 1, 0, -1):
                if cur[i] in _BREAK_AFTER:
                    break_at = i + 1
                    break
            if break_at >= 2 and break_at < len(cur):
                lines.append(cur[:break_at].rstrip())
                cur = cur[break_at:].lstrip() + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur = trial
    if cur or not lines:
        lines.append(cur)
    return lines


def fit_size(draw: ImageDraw.ImageDraw, text: str, font_loader, max_w: int, start: int, min_size: int = 22) -> int:
    """缩小字号直到单行能放下。"""
    sz = start
    while sz > min_size and draw.textlength(text, font=font_loader(sz)) > max_w:
        sz -= 2
    return sz


def text_hw(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font, anchor="lt")
    return box[2] - box[0], box[3] - box[1]


class Renderer:
    def __init__(self, spec: VideoSpec):
        if not spec.font_bold:
            raise ValueError("未指定字体路径")
        self.spec = spec
        self.L = make_layout(spec.width, spec.height)
        self.W, self.H = spec.width, spec.height
        self.points = [p.strip() for p in spec.points if p and str(p).strip()]
        if not self.points:
            raise ValueError("至少需要 1 个要点")
        self.scenes = scene_times(spec.duration, len(self.points))
        self._font_cache = {}
        self._bg = self._make_base_bg()
        self.tag = (spec.tag or spec.topic).strip()

    def font(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        path = self.spec.font_bold if bold else (self.spec.font_regular or self.spec.font_bold)
        key = (path, int(size), bold)
        if key not in self._font_cache:
            self._font_cache[key] = load_font(path, int(size), bold=bold)
        return self._font_cache[key]

    def _make_base_bg(self) -> np.ndarray:
        yy = np.linspace(0.0, 1.0, self.H)[:, None, None]
        bg = (NAVY_TOP * (1.0 - yy) + NAVY_BOT * yy) * np.ones((1, self.W, 1))
        return bg.astype(np.uint8)

    def _bg_with_orbs(self, t: float) -> Image.Image:
        im = Image.fromarray(self._bg).convert("RGBA")
        ov = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        # 三个缓慢移动的柔光圆
        orbs = [
            (0.83 * self.W, 0.18 * self.H, 0.24 * min(self.W, self.H), 0.0),
            (0.14 * self.W, 0.78 * self.H, 0.30 * min(self.W, self.H), 2.0),
            (0.74 * self.W, 0.86 * self.H, 0.19 * min(self.W, self.H), 4.0),
        ]
        for cx, cy, r, ph in orbs:
            ox = math.sin(t * 0.8 + ph) * (self.W * 0.028)
            oy = math.cos(t * 0.6 + ph) * (self.H * 0.016)
            for k in range(6):
                rr = r * (1 - k * 0.12)
                d.ellipse([cx + ox - rr, cy + oy - rr, cx + ox + rr, cy + oy + rr], fill=(255, 98, 52, 7))
        return Image.alpha_composite(im, ov)

    def _draw_tag(self, d: ImageDraw.ImageDraw) -> None:
        f = self.font(self.L.tag_size, bold=True)
        # 控制长度，避免贴边
        text = self.tag
        max_w = self.W - self.L.margin * 2
        if d.textlength(text, font=f) > max_w:
            while len(text) > 2 and d.textlength(text + "…", font=f) > max_w:
                text = text[:-1]
            text = text + "…"
        d.text((self.L.margin, self.L.tag_y), text, font=f, fill=GREY, anchor="lt")

    def _draw_progress(self, d: ImageDraw.ImageDraw, t: float) -> None:
        x = int(self.W * min(1.0, max(0.0, t / self.spec.duration)))
        if x > 0:
            bar_h = max(6, int(self.H * 0.0052))
            d.rectangle([0, 0, x, bar_h], fill=ACC)

    def _draw_dots(self, d: ImageDraw.ImageDraw, lit: int, total: Optional[int] = None) -> None:
        total = total or len(self.points)
        r = max(8, int(min(self.W, self.H) * 0.013))
        gap = r * 5
        cy = self.L.dots_y
        cx0 = self.W / 2 - (total - 1) * gap / 2
        for i in range(total):
            x = cx0 + i * gap
            on = i < lit
            d.ellipse([x - r, cy - r, x + r, cy + r], fill=ACC if on else DOT_OFF)

    def _centered_multiline(
        self,
        d: ImageDraw.ImageDraw,
        text: str,
        y: int,
        size: int,
        fill,
        max_w: int,
        max_lines: int = 2,
        min_size: int = 24,
        bold: bool = True,
        line_gap: float = 1.2,
    ) -> Tuple[int, int]:
        """在 (center, y) 处绘制最多 max_lines 行的居中文字。返回 (字号, 块高度)。"""
        sz = size
        font = self.font(sz, bold)
        lines = wrap_text(d, text, font, max_w)
        while (len(lines) > max_lines or any(d.textlength(ln, font=font) > max_w for ln in lines)) and sz > min_size:
            sz -= 2
            font = self.font(sz, bold)
            lines = wrap_text(d, text, font, max_w)
            if len(lines) > max_lines:
                # 强制把后面的行并入最后一行并加省略，避免溢出
                head, rest = lines[: max_lines - 1], "".join(lines[max_lines - 1 :])
                last = rest
                while last and d.textlength(last + "…", font=font) > max_w:
                    last = last[:-1]
                lines = head + [last + ("…" if last != rest else "")]
        lh = int(sz * line_gap)
        for i, ln in enumerate(lines):
            w = d.textlength(ln, font=font)
            d.text((self.W / 2 - w / 2, y + i * lh), ln, font=font, fill=fill, anchor="lt")
        return sz, lh * len(lines)

    def _chat_bubble(
        self,
        d: ImageDraw.ImageDraw,
        text: str,
        shown: int,
        y: int,
        t_loc: float,
        show_reply: bool,
        rt: float,
    ) -> int:
        L = self.L
        sz = L.chat_size
        font = self.font(sz, True)
        max_w = L.max_chat_w
        # 字太长就缩小，尽量控制在 3 行内
        lines = wrap_text(d, text, font, max_w)
        while len(lines) > 3 and sz > 24:
            sz -= 2
            font = self.font(sz, True)
            lines = wrap_text(d, text, font, max_w)
        line_h = max(L.line_h_chat, int(sz * 1.45))
        text_w = max(d.textlength(ln, font=font) for ln in lines) if lines else 0
        bw = int(text_w + L.bubble_pad_x * 2)
        bh = int(len(lines) * line_h + L.bubble_pad_y * 2)
        # 右对齐，并保证不贴边、不超出画面
        right_margin = L.margin if L.portrait else max(L.margin, int(self.W * 0.10))
        right = self.W - right_margin
        left = right - bw
        if left < L.margin:
            left = L.margin
            bw = right - left
        # 气泡底部不超过画面安全区
        if y + bh > self.H - int(self.H * 0.08):
            y = self.H - int(self.H * 0.08) - bh
        radius = min(L.bubble_radius, bh // 2, bw // 2)
        d.rounded_rectangle([left, y, right, y + bh], radius, fill=ACC)
        # 小尾巴（右下），保证仍在画面内
        tail = [
            (right - int(30 * bw / max(bw, 1) * 0.08 + 24), y + bh - int(bh * 0.22)),
            (min(self.W - 8, right + int(self.W * 0.01)), y + bh + 4),
            (right - int(bw * 0.12), y + bh - 8),
        ]
        d.polygon(tail, fill=ACC)

        n = 0
        for i, ln in enumerate(lines):
            vis = ln[: max(0, shown - n)]
            n += len(ln)
            d.text(
                (left + L.bubble_pad_x, y + L.bubble_pad_y + i * line_h),
                vis,
                font=font,
                fill=WHITE,
                anchor="lt",
            )
        # 打字光标
        if shown < len(text) and int(t_loc * 3) % 2 == 0:
            n = 0
            for i, ln in enumerate(lines):
                if shown <= n + len(ln):
                    prefix = ln[: max(0, shown - n)]
                    cxp = left + L.bubble_pad_x + d.textlength(prefix, font=font) + 4
                    cy0 = y + L.bubble_pad_y + i * line_h + 4
                    d.rectangle([cxp, cy0, cxp + max(4, sz // 10), cy0 + int(sz * 0.9)], fill=WHITE)
                    break
                n += len(ln)

        if show_reply:
            a = ease(rt / 0.3)
            if a > 0:
                rw = int(min(self.W * 0.24, 250 if L.portrait else 220) * max(0.4, a))
                rh = int(100 if L.portrait else 80)
                rx0 = L.margin
                ry = y + bh + int(self.H * (0.026 if L.portrait else 0.03))
                # 横屏时把回复气泡放在主气泡左下方，避免左右拉得太开
                if not L.portrait:
                    rx0 = max(L.margin, left - rw - int(self.W * 0.04))
                if ry + rh < self.H - 20:
                    d.rounded_rectangle([rx0, ry, rx0 + max(rw, rh), ry + rh], rh // 2, fill=REPLY_BG)
                    if a > 0.7:
                        for k in range(3):
                            s = 0.5 + 0.5 * math.sin(max(0.0, rt) * 8 - k * 0.9)
                            rr = (11 if L.portrait else 8) + 4 * s
                            gap = int((max(rw, 160) - 40) / 3)
                            cx = rx0 + 40 + k * max(36, gap)
                            cy = ry + rh / 2
                            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=DOT_IDLE)
        return y + bh

    def _scene_hook(self, d: ImageDraw.ImageDraw, tl: float) -> None:
        L = self.L
        a1 = ease(tl / 0.45)
        y = int(L.hook_y + (1 - a1) * (self.H * 0.03))
        # 钩子标题（最多两行），胶囊紧跟在真实高度下方，避免重叠
        _, hook_h = self._centered_multiline(
            d, self.spec.hook, y, L.hook_size, WHITE, L.max_hook_w, max_lines=2, min_size=32
        )

        if tl > 0.9:
            a2 = back_ease((tl - 0.9) / 0.4)
            sub = self.spec.sub
            sz = fit_size(d, sub, lambda s: self.font(s, True), L.max_cta_w - 80, L.sub_size, 26)
            font = self.font(sz, True)
            tw = d.textlength(sub, font=font)
            _, th = text_hw(d, sub, font)
            pad_x = int(sz * 0.7)
            pad_y = int(sz * 0.45)
            yc = y + hook_h + int(self.H * (0.035 if L.portrait else 0.045)) + (th + pad_y * 2) / 2
            hw = (tw / 2 + pad_x) * max(0.02, a2)
            hh = (th / 2 + pad_y) * max(0.02, a2)
            d.rounded_rectangle(
                [self.W / 2 - hw, yc - hh, self.W / 2 + hw, yc + hh],
                min(int(sz * 0.55), int(hh)),
                fill=ACC,
            )
            if a2 > 0.88:
                d.text((self.W / 2, yc), sub, font=font, fill=WHITE, anchor="mm")

        # 底部浅灰提示，避免和胶囊重叠
        tip_y = int(self.H * (0.72 if L.portrait else 0.82))
        tip = "内容仅供参考，请按真实体验分享"
        tip_sz = max(20, int(L.tag_size * 0.9))
        tf = self.font(tip_sz, False)
        if d.textlength(tip, font=tf) < self.W - 2 * L.margin:
            d.text((self.W / 2, tip_y), tip, font=tf, fill=GREY, anchor="mt")

    def _scene_point(self, d: ImageDraw.ImageDraw, idx: int, tl: float, dur: float) -> None:
        L = self.L
        point = self.points[idx]
        mark = "①②③④⑤⑥⑦⑧⑨⑩"[idx] if idx < 10 else f"{idx+1}."
        title = f"{mark}  {point}"
        # 能单行放下就单行，否则最多两行（优先在标点处断开）
        title_size = fit_size(d, title, lambda s: self.font(s, True), L.max_title_w, L.title_size, 48)
        _, title_h = self._centered_multiline(
            d, title, L.title_y, title_size, WHITE, L.max_title_w,
            max_lines=2, min_size=26, line_gap=1.25,
        )
        self._draw_dots(d, idx + 1)
        # 橙色短线放在标题下方，随标题实际高度移动，避免穿过第二行文字
        lw = int(self.W * (0.13 if L.portrait else 0.08))
        ly = L.title_y + title_h + int(self.H * (0.018 if L.portrait else 0.022))
        d.rounded_rectangle([self.W / 2 - lw, ly, self.W / 2 + lw, ly + max(6, int(self.H * 0.004))], 4, fill=ACC)

        # 打字：前 0.4 秒只显示气泡框架，之后在 ~1.3 秒内打完
        n = len(point)
        type_start = 0.35
        type_dur = min(1.35, max(0.7, dur - 1.15))
        if tl <= type_start:
            shown = 0
        else:
            shown = int((tl - type_start) / type_dur * n)
            shown = max(0, min(n, shown))
        show_reply = tl > type_start + type_dur + 0.15
        rt = tl - (type_start + type_dur + 0.15)
        chat_y = ly + int(self.H * (0.045 if L.portrait else 0.055))
        self._chat_bubble(d, point, shown, chat_y, tl, show_reply, rt)

    def _scene_outro(self, d: ImageDraw.ImageDraw, tl: float) -> None:
        L = self.L
        self._draw_dots(d, len(self.points))
        head = "四点记下来"
        self._centered_multiline(d, head, L.recap_y, L.title_size, WHITE, L.max_title_w, max_lines=1, min_size=28)

        # 四条回顾，逐条淡入，避免拥挤：横屏两列，竖屏一列
        items = list(self.points)
        start_y = L.recap_y + int(L.title_size * (1.7 if L.portrait else 2.3))
        rec_sz = L.recap_size
        font = self.font(rec_sz, True)
        if L.portrait:
            gap = int(rec_sz * 1.85)
            max_w = L.max_title_w
            for i, p in enumerate(items):
                a = ease((tl - 0.15 - i * 0.12) / 0.3)
                if a <= 0:
                    continue
                label = f"{i+1}. {p}"
                # 单行放不下就缩字号
                f = font
                sz = rec_sz
                while d.textlength(label, font=f) > max_w and sz > 22:
                    sz -= 2
                    f = self.font(sz, True)
                if d.textlength(label, font=f) > max_w:
                    s = label
                    while s and d.textlength(s + "…", font=f) > max_w:
                        s = s[:-1]
                    label = s + "…"
                color = (255, 255, 255, int(255 * a))
                # ImageDraw 在 RGB/RGBA 均可填 RGB
                y = start_y + i * gap + int((1 - a) * 16)
                d.text((self.W / 2, y), label, font=f, fill=WHITE, anchor="mt")
            last_y = start_y + len(items) * gap
        else:
            # 两列两行
            col_w = int((self.W - L.margin * 2) / 2)
            gap_y = int(rec_sz * 2.0)
            for i, p in enumerate(items):
                a = ease((tl - 0.15 - i * 0.12) / 0.3)
                if a <= 0:
                    continue
                col, row = i % 2, i // 2
                cx = L.margin + col * col_w + col_w / 2
                y = start_y + row * gap_y + int((1 - a) * 12)
                label = f"{i+1}. {p}"
                f = font
                sz = rec_sz
                max_w = col_w - 24
                while d.textlength(label, font=f) > max_w and sz > 20:
                    sz -= 2
                    f = self.font(sz, True)
                if d.textlength(label, font=f) > max_w:
                    s = label
                    while s and d.textlength(s + "…", font=f) > max_w:
                        s = s[:-1]
                    label = s + "…"
                d.text((cx, y), label, font=f, fill=WHITE, anchor="mt")
            last_y = start_y + 2 * gap_y

        # CTA 胶囊
        if tl > 0.7:
            a = ease((tl - 0.7) / 0.4)
            cta = self.spec.outro
            sz = fit_size(d, cta, lambda s: self.font(s, True), L.max_cta_w - 80, L.cta_size, 24)
            f = self.font(sz, True)
            tw = d.textlength(cta, font=f)
            _, th = text_hw(d, cta, f)
            pad_x = int(sz * 0.75)
            pad_y = int(sz * 0.48)
            # 放在回顾列表下方，同时不超出底部安全区
            min_y = last_y + int(self.H * (0.06 if L.portrait else 0.08))
            y0 = max(min_y, L.cta_y)
            box_h = th + pad_y * 2
            if y0 + box_h > self.H - int(self.H * 0.06):
                y0 = self.H - int(self.H * 0.06) - box_h
            y0 = y0 + int((1 - a) * (self.H * 0.03))
            d.rounded_rectangle(
                [self.W / 2 - tw / 2 - pad_x, y0, self.W / 2 + tw / 2 + pad_x, y0 + box_h],
                box_h // 2,
                fill=ACC,
            )
            if a > 0.85:
                d.text((self.W / 2, y0 + box_h / 2), cta, font=f, fill=WHITE, anchor="mm")

    def _compose_scene(self, t: float, for_cover: bool = False) -> Image.Image:
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        scenes = self.scenes
        # 找到当前镜头
        idx = len(scenes) - 1
        for i, (s, e) in enumerate(scenes):
            if s <= t < e or (i == len(scenes) - 1 and abs(t - e) < 1e-6):
                idx = i
                break
        start, end = scenes[idx]
        # 封面定格在钩子镜头接近结束处，不需要滑出
        if for_cover:
            self._scene_hook(d, 2.0)
            return layer, 0

        tl = t - start
        dur = end - start
        if idx == 0:
            self._scene_hook(d, tl)
        elif idx == len(scenes) - 1:
            self._scene_outro(d, tl)
        else:
            self._scene_point(d, idx - 1, tl, dur)

        ain = 1.0 if idx == 0 else ease(tl / 0.30)
        if idx < len(scenes) - 1:
            aout = 1.0 - ease((tl - (dur - 0.22)) / 0.22)
        else:
            aout = 1.0
        a = max(0.0, min(1.0, ain * aout))
        ox = int((1 - ain) * (self.W * 0.11) - (1 - aout) * (self.W * 0.11))
        if a < 1:
            al = layer.getchannel("A").point(lambda p, aa=a: int(p * aa))
            layer.putalpha(al)
        return layer, ox

    def frame(self, t: float, for_cover: bool = False) -> Image.Image:
        im = self._bg_with_orbs(t)
        overlay, ox = self._compose_scene(t, for_cover=for_cover)
        if ox == 0:
            im.alpha_composite(overlay)
        else:
            # 水平滑入/滑出
            if ox > 0:
                cropped = overlay.crop((0, 0, self.W - ox, self.H))
                im.alpha_composite(cropped, (ox, 0))
            else:
                cropped = overlay.crop((-ox, 0, self.W, self.H))
                im.alpha_composite(cropped, (0, 0))
        d = ImageDraw.Draw(im)
        self._draw_tag(d)
        if not for_cover:
            self._draw_progress(d, t)
        return im.convert("RGB")

    def cover(self) -> Image.Image:
        # 定格在钩子镜头已经完全展开的时刻
        t = min(2.05, max(0.0, self.scenes[0][1] - 0.15))
        return self.frame(t, for_cover=True)

    def still_times(self) -> List[Tuple[str, float]]:
        labels = ["01_hook"]
        for i in range(len(self.points)):
            labels.append(f"0{i+2}_point{i+1}")
        labels.append(f"0{len(self.points)+2}_outro")
        out = []
        for i, ((s, e), name) in enumerate(zip(self.scenes, labels)):
            # 取镜头后段，打字和 CTA 都已经出现
            if i == 0:
                t = min(e - 0.12, s + 1.9)
            elif i == len(self.scenes) - 1:
                t = min(e - 0.12, s + 1.7)
            else:
                t = min(e - 0.18, s + (e - s) * 0.78)
            out.append((name, max(s, t)))
        return out


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError(
            "没有找到 ffmpeg。Windows 用户可以：\n"
            "  1. 打开 Microsoft Store 搜索 ffmpeg，或\n"
            "  2. 访问 https://www.gyan.dev/ffmpeg/builds/ 下载，解压后把 bin 文件夹加到系统环境变量 Path；\n"
            "  3. 安装好后重新打开命令行，输入 ffmpeg -version 检查是否成功。"
        )
    return exe


def render_video(
    spec: VideoSpec,
    audio_wav: Path,
    out_mp4: Path,
    frames_dir: Optional[Path] = None,
    cover_path: Optional[Path] = None,
    progress=None,
) -> Path:
    renderer = Renderer(spec)
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    if cover_path:
        Path(cover_path).parent.mkdir(parents=True, exist_ok=True)
        renderer.cover().save(cover_path, "PNG", optimize=True)

    if frames_dir:
        frames_dir = Path(frames_dir)
        frames_dir.mkdir(parents=True, exist_ok=True)
        for name, t in renderer.still_times():
            renderer.frame(t).save(frames_dir / f"{name}.png", "PNG", optimize=True)

    ffmpeg = find_ffmpeg()
    nframes = int(round(spec.duration * spec.fps))
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{spec.width}x{spec.height}",
        "-r", str(spec.fps),
        "-i", "-",
        "-i", str(audio_wav),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", str(spec.crf), "-preset", "medium",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        "-t", f"{spec.duration:.3f}",
        str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for i in range(nframes):
            t = i / spec.fps
            frame = renderer.frame(t)
            proc.stdin.write(frame.tobytes())
            if progress and (i % max(1, spec.fps) == 0 or i == nframes - 1):
                progress(i + 1, nframes)
        proc.stdin.close()
        err = proc.stderr.read() if proc.stderr else b""
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg 合成失败（退出码 {rc}）：{err.decode('utf-8', errors='replace')}")
    except Exception:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.kill()
        raise
    return out_mp4
