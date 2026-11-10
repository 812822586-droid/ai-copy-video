# -*- coding: utf-8 -*-
"""查找可用的中文字体。优先 Noto Sans CJK SC，Windows 上自动回退到微软雅黑。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from PIL import ImageFont

# Noto Sans CJK *.ttc 中简体中文（SC）通常是第 3 个（index=2）
NOTO_SC_INDEX = 2

# 常见安装路径，按优先级排列
_FONT_CANDIDATES = [
    # 项目自带 fonts 目录（把 ttc/ttf 放进来即可）
    "fonts/NotoSansCJK-Bold.ttc",
    "fonts/NotoSansCJK-Regular.ttc",
    "fonts/NotoSansSC-Bold.otf",
    "fonts/NotoSansSC-Regular.otf",
    "fonts/msyhbd.ttc",
    "fonts/msyh.ttc",
    # Linux（本项目开发环境）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto-cjk/NotoSansCJK-Bold.ttc",
    # Windows 微软雅黑 / 黑体 / 宋体
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttf",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/msyhbd.otf",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/simsunb.ttf",
    "C:/Windows/Fonts/NotoSansCJK-Bold.ttc",
    "C:/Windows/Fonts/NotoSansSC-Bold.otf",
    # macOS
    "/Library/Fonts/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]


def _is_noto_cjk(path: str) -> bool:
    name = Path(path).name.lower()
    return "notosanscjk" in name.replace(" ", "") or "noto-sans-cjk" in name


def _is_msyh(path: str) -> bool:
    return "msyh" in Path(path).name.lower()


def font_index_for(path: str, bold: bool = True) -> int:
    """返回该字体文件应使用的 TTC 索引。"""
    if _is_noto_cjk(path):
        return NOTO_SC_INDEX
    if _is_msyh(path):
        # 微软雅黑 ttc：0 Regular，1 Bold，2 UI Regular，3 UI Bold
        return 1 if bold and path.lower().endswith(".ttc") else 0
    return 0


def _exists(path: str) -> bool:
    try:
        return Path(path).is_file()
    except OSError:
        return False


def resolve_font_pair(
    user_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Tuple[str, str, str]:
    """找到粗体、常规两套字体路径。

    返回 (bold_path, regular_path, note)。
    若只找到一个文件，粗体和常规会指向同一个文件。
    """
    env = (
        user_path
        or os.environ.get("AICOPY_FONT")
        or os.environ.get("FONT_PATH")
        or ""
    ).strip()

    searched = []
    if env:
        searched.append(env)

    root = Path(project_root) if project_root else Path.cwd()
    for rel in _FONT_CANDIDATES:
        if Path(rel).is_absolute():
            searched.append(rel)
        else:
            searched.append(str(root / rel))

    found = []
    seen = set()
    for p in searched:
        rp = str(Path(p))
        if rp in seen:
            continue
        seen.add(rp)
        if _exists(rp):
            found.append(rp)

    if not found:
        raise FileNotFoundError(
            "没有找到中文字体。请任选一种方法：\n"
            "  1. Windows 用户：确认 C:\\\\Windows\\\\Fonts\\\\msyh.ttc（微软雅黑）存在；\n"
            "  2. 安装 Noto Sans CJK SC，并把文件放到本项目的 fonts 文件夹；\n"
            "  3. 运行时加上参数  --font 字体文件的完整路径\n"
            "  4. 或设置环境变量 AICOPY_FONT=字体路径"
        )

    bold = found[0]
    regular = found[0]
    # 若第一个是 Bold，尝试配一个 Regular
    lower_names = {Path(p).name.lower(): p for p in found}
    name0 = Path(bold).name.lower()
    if "bold" in name0 or "msyhbd" in name0:
        for key, p in lower_names.items():
            if "regular" in key or key in ("msyh.ttc", "msyh.ttf", "msyh.otf"):
                regular = p
                break
    else:
        # 第一个像是常规，再找粗体
        regular = bold
        for key, p in lower_names.items():
            if "bold" in key or "msyhbd" in key:
                bold = p
                break

    label = Path(bold).name
    if _is_noto_cjk(bold):
        note = f"Noto Sans CJK SC（{label}）"
    elif _is_msyh(bold):
        note = f"微软雅黑（{label}）"
    else:
        note = label
    return bold, regular, note


_CACHE: dict = {}


def load_font(path: str, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """加载并缓存字体。"""
    size = max(8, int(size))
    idx = font_index_for(path, bold=bold)
    key = (path, size, idx)
    if key in _CACHE:
        return _CACHE[key]
    last_err = None
    # 优先建议索引，失败再试 0,1,2...
    for try_idx in (idx, 0, 1, 2, 3, 4):
        try:
            font = ImageFont.truetype(path, size=size, index=try_idx)
            _CACHE[key] = font
            return font
        except OSError as exc:
            last_err = exc
            continue
    raise OSError(f"无法加载字体 {path}：{last_err}") from last_err
