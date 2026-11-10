#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI文案短视频助手 —— 命令行入口。

示例：
    python make.py --topic 护手霜
    python make.py --topic 护手霜 --orientation landscape
    python make.py --topic 护手霜 --point 要点一 --point 要点二 --point 要点三 --point 要点四
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# 保证从任意工作目录运行都能找到包
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicopyvideo.audio import render_audio
from aicopyvideo.copygen import generate_copies, render_markdown
from aicopyvideo.fonts import resolve_font_pair
from aicopyvideo.video import VideoSpec, render_video, scene_times


def _setup_stdio() -> None:
    # Windows 命令行默认编码可能不是 UTF-8，避免打印中文时报错
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="make.py",
        description="输入产品名或主题，生成 4 种风格小红书文案、15 秒短视频和封面。",
    )
    p.add_argument("--topic", required=True, help="产品名或主题，例如：护手霜")
    p.add_argument(
        "--point",
        action="append",
        dest="points",
        default=[],
        help="自定义要点，可重复最多 4 次。不填则使用默认要点。",
    )
    p.add_argument(
        "--points",
        dest="points_joined",
        default="",
        help="四个要点用竖线 | 分隔（避免和中文逗号冲突）",
    )
    p.add_argument("--hook", default="", help="自定义视频开头钩子句")
    p.add_argument("--sub", default="", help="自定义钩子下方的橙色副标题")
    p.add_argument("--outro", default="关注我，带你用AI做副业", help="结尾句子，可改成你自己的口号")
    p.add_argument(
        "--orientation",
        choices=["portrait", "landscape"],
        default="portrait",
        help="portrait=竖屏 1080x1920，landscape=横屏 1920x1080",
    )
    p.add_argument("--width", type=int, default=0, help="自定义宽度（默认随 orientation）")
    p.add_argument("--height", type=int, default=0, help="自定义高度（默认随 orientation）")
    p.add_argument("--duration", type=float, default=15.0, help="视频时长，单位秒，默认 15")
    p.add_argument("--fps", type=int, default=30, help="帧率，默认 30")
    p.add_argument("--crf", type=int, default=20, help="视频质量，18 更清晰、28 文件更小，默认 20")
    p.add_argument("--font", default="", help="中文字体文件路径（Windows 可填 C:/Windows/Fonts/msyh.ttc）")
    p.add_argument("--outdir", default="", help="输出文件夹，默认 output/主题名/")
    p.add_argument("--use-ai", action="store_true", help="若设置了 API Key，则尝试用 AI 写文案；失败自动回退模板")
    p.add_argument("--skip-video", action="store_true", help="只生成文案和封面，不渲染视频")
    p.add_argument("--skip-frames", action="store_true", help="不导出预览分镜图")
    return p.parse_args(argv)


def collect_points(args: argparse.Namespace) -> list:
    pts = list(args.points or [])
    if args.points_joined:
        pts.extend([x.strip() for x in args.points_joined.split("|") if x.strip()])
    # 去空、保序去重
    out, seen = [], set()
    for p in pts:
        p = p.strip()
        if p and p not in seen:
            out.append(p)
            seen.add(p)
    return out[:4]


def main(argv=None) -> int:
    _setup_stdio()
    args = parse_args(argv)

    if args.duration < 5 or args.duration > 60:
        print("时长请放在 5 到 60 秒之间。", file=sys.stderr)
        return 2
    if args.fps < 15 or args.fps > 60:
        print("帧率请放在 15 到 60 之间。", file=sys.stderr)
        return 2

    try:
        result = generate_copies(args.topic, collect_points(args), use_ai=args.use_ai)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    script = result["script"]
    if args.hook.strip():
        script["hook"] = args.hook.strip()
    if args.sub.strip():
        script["sub"] = args.sub.strip()

    topic = script["topic"]
    if args.orientation == "landscape":
        width, height = 1920, 1080
        ori_name = "横屏"
    else:
        width, height = 1080, 1920
        ori_name = "竖屏"
    if args.width > 0:
        width = args.width
    if args.height > 0:
        height = args.height
    # H.264 要求宽高为偶数
    width -= width % 2
    height -= height % 2

    outdir = Path(args.outdir) if args.outdir else (ROOT / "output" / topic)
    outdir = outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    frames_dir = outdir / "frames"

    try:
        font_bold, font_regular, font_note = resolve_font_pair(args.font or None, project_root=ROOT)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    md_path = outdir / "文案.md"
    md_path.write_text(render_markdown(result), encoding="utf-8")

    cover_path = outdir / "封面.png"
    safe_topic = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in topic)
    mp4_path = outdir / f"{safe_topic}_{int(args.duration)}秒_{ori_name}.mp4"

    print("=" * 46)
    print("  AI文案短视频助手")
    print("=" * 46)
    print(f"主题    ：{topic}")
    print(f"钩子    ：{script['hook']}")
    print(f"要点    ：{' / '.join(script['points'])}")
    print(f"画幅    ：{width}x{height}（{ori_name}）  {args.duration:.0f}秒 {args.fps}fps")
    print(f"字体    ：{font_note}")
    print(f"文案    ：{md_path}")
    print(f"生成方式：{'AI 接口' if result['source']=='ai' else '离线模板（不用 API Key）'}")
    print()

    spec = VideoSpec(
        topic=topic,
        hook=script["hook"],
        sub=script["sub"],
        points=script["points"],
        outro=args.outro,
        width=width,
        height=height,
        fps=args.fps,
        duration=args.duration,
        font_bold=font_bold,
        font_regular=font_regular,
        crf=args.crf,
    )

    # 先出封面和分镜，视频失败时至少还有图
    from aicopyvideo.video import Renderer

    renderer = Renderer(spec)
    renderer.cover().save(cover_path, "PNG", optimize=True)
    print(f"封面    ：{cover_path}")

    if not args.skip_frames:
        frames_dir.mkdir(parents=True, exist_ok=True)
        for name, t in renderer.still_times():
            renderer.frame(t).save(frames_dir / f"{name}.png", "PNG", optimize=True)
        print(f"分镜图  ：{frames_dir}")

    if args.skip_video:
        print("已按要求跳过视频渲染。")
        return 0

    scenes = scene_times(args.duration, len(script["points"]))
    pop_times = [s for s, _ in scenes] + [args.duration * 0.08]

    def progress(cur, total):
        pct = int(cur * 100 / total)
        # 每秒刷新一次
        print(f"\r正在渲染视频…… {cur}/{total} 帧（{pct}%）", end="", flush=True)

    wav_path = outdir / "_audio.wav"
    try:
        render_audio(args.duration, pop_times, wav_path)
        print("音频已生成，开始逐帧画画面（大约 1～2 分钟，请稍候）……")
        render_video(
            spec,
            audio_wav=wav_path,
            out_mp4=mp4_path,
            frames_dir=None if args.skip_frames else frames_dir,
            cover_path=cover_path,
            progress=progress,
        )
        print()
        size_mb = mp4_path.stat().st_size / 1024 / 1024
        print(f"视频    ：{mp4_path}  （约 {size_mb:.1f} MB）")
    except FileNotFoundError as exc:
        print()
        print(str(exc), file=sys.stderr)
        print("文案和封面已经生成，装好 ffmpeg 后重新运行即可补出视频。", file=sys.stderr)
        return 3
    except Exception as exc:
        print()
        print(f"视频生成失败：{exc}", file=sys.stderr)
        return 1
    finally:
        try:
            if wav_path.exists():
                wav_path.unlink()
        except OSError:
            pass

    print()
    print("全部完成。请打开输出文件夹查看：")
    print(f"  {outdir}")
    print("记得先预览再发布。文案请按真实体验修改，不要夸大效果，也不要承诺阅读量。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
