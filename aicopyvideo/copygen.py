# -*- coding: utf-8 -*-
"""生成 4 种风格的小红书文案。默认纯模板、不需要联网或 API Key。

可选：设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY，并加上 --use-ai，
会尝试调用 OpenAI 兼容接口（如 DeepSeek）；失败则自动回退到模板。

文案遵守：不夸大功效、不保证阅读量/销量、提醒按真实体验修改。
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

STYLES = [
    ("funny", "搞笑吐槽"),
    ("warm", "温柔治愈"),
    ("review", "干货测评"),
    ("gift", "送礼推荐"),
]

# 个别常见主题的视频钩子和要点（演示更自然；其他主题走通用模板）
PRESETS: Dict[str, dict] = {
    "护手霜": {
        "hook": "秋冬洗手后，手背又干又糙？",
        "sub": "选护手霜，先看这四点",
        "points": [
            "干燥起皮时，优先选滋润型",
            "出门前、洗手后再补一层",
            "敏感肌先在小面积试用",
            "送人记得看成分表，别乱承诺效果",
        ],
    },
}

DISCLAIMER = (
    "说明：以上文案由模板（或可选的 AI 接口）生成，仅供学习与草稿参考。"
    "请根据真实使用体验修改后再发布。不要夸大产品效果，不要承诺阅读量、销量或排名。"
    "涉及功效、医疗或食品承诺时，请自行核对广告法与平台规则。"
)


def _clean_topic(topic: str) -> str:
    t = (topic or "").strip()
    t = re.sub(r"\s+", " ", t)
    if not t:
        raise ValueError("请提供产品名或主题，例如：--topic 护手霜")
    return t


def default_script(topic: str, points: Optional[List[str]] = None) -> dict:
    """生成视频用的钩子、副标题和 4 个要点。"""
    topic = _clean_topic(topic)
    preset = PRESETS.get(topic, {})
    hook = preset.get("hook") or f"想把「{topic}」讲清楚？"
    sub = preset.get("sub") or "先记住下面这四点"
    base_points = list(preset.get("points") or [
        f"先写清「{topic}」能帮你解决什么日常问题",
        "把使用方法和适用场景用大白话讲明白",
        "适合谁、不适合谁，提前说清楚更放心",
        "分享或送礼时，不要夸大效果、也不要打包票",
    ])
    if points:
        cleaned = [p.strip() for p in points if p and p.strip()]
        if cleaned:
            # 不足 4 条用默认补齐，超过 4 条只取前 4 条
            merged = cleaned[:4]
            for extra in base_points:
                if len(merged) >= 4:
                    break
                if extra not in merged:
                    merged.append(extra)
            while len(merged) < 4:
                merged.append(f"关于「{topic}」，把关键信息写具体一点")
            base_points = merged
    return {"topic": topic, "hook": hook, "sub": sub, "points": base_points[:4]}


def _tags(topic: str, extras: List[str]) -> List[str]:
    tags = [topic] + extras
    # 去重、去掉 # 和空格，固定 5 个
    seen = []
    for t in tags:
        t = t.replace("#", "").replace(" ", "").strip()
        if t and t not in seen:
            seen.append(t)
        if len(seen) == 5:
            break
    defaults = ["生活好物", "实用分享", "日常记录", "经验分享", "种草笔记"]
    for d in defaults:
        if len(seen) >= 5:
            break
        if d not in seen and d != topic:
            seen.append(d)
    return seen[:5]


def _bullets(points: List[str]) -> str:
    return "\n".join(f"· {p}" for p in points)


def template_copies(topic: str, points: List[str]) -> List[dict]:
    """4 种风格的离线模板。用真实体验口吻，避免绝对化承诺。"""
    topic = _clean_topic(topic)
    pts = points[:4]
    bullets = _bullets(pts)

    funny = {
        "style_id": "funny",
        "style_name": "搞笑吐槽",
        "title": f"关于{topic}，我有句吐槽不吐不快 😅",
        "body": (
            f"以前我对「{topic}」的态度很简单：有就用，没有就算了。"
            f"直到某天真实体会到——少了它，日常会变得小小地狼狈一下。\n\n"
            f"不是说它有多神奇，更不是用了就一定怎样。"
            f"只是把该做的步骤做对，体感会踏实很多。我后来给自己定了这几个小原则：\n\n"
            f"{bullets}\n\n"
            f"所以现在再写笔记，我也不再堆一堆空洞形容词了。"
            f"把场景讲清楚、把注意事项讲明白，比喊口号管用。\n\n"
            f"你们平时用「{topic}」踩过哪些坑？欢迎评论区聊聊，互相避雷。"
        ),
        "emoji": "😅🌿✨📝💬",
        "tags": _tags(topic, ["日常吐槽", "生活好物", "经验分享", "真实记录"]),
    }

    warm = {
        "style_id": "warm",
        "style_name": "温柔治愈",
        "title": f"把「{topic}」放进日常里，是一种小小的被照顾 🤍",
        "body": (
            f"有些东西不是为了制造惊喜，只是让一天过得更平稳一点。"
            f"对我来说，「{topic}」就是这样的存在。\n\n"
            f"不必一次做得很完美，也不必期待立竿见影。"
            f"按自己的节奏来，留意这些细节就很好：\n\n"
            f"{bullets}\n\n"
            f"如果是第一次尝试，建议先小范围试试看，再决定要不要长期用。"
            f"每个人的情况不一样，适合别人的，不一定正好适合你。\n\n"
            f"愿你也被自己好好对待着。今天也温柔一点，慢慢来就很好。"
        ),
        "emoji": "🤍🌿☁️✨🫶",
        "tags": _tags(topic, ["温柔日常", "生活记录", "自我关照", "慢生活"]),
    }

    review = {
        "style_id": "review",
        "style_name": "干货测评",
        "title": f"{topic}怎么选？先看这 4 个实际问题 ✅",
        "body": (
            f"这篇不当「万能测评」，也不打神秘分数。"
            f"只把挑选「{topic}」时真正用得上的问题列清楚，方便你对照自己的需求。\n\n"
            f"可以按下面 4 点自查：\n\n"
            f"{bullets}\n\n"
            f"建议你写笔记或下单前再确认三件事：\n"
            f"1. 自己最想解决的问题是什么，先写下来；\n"
            f"2. 看清使用方法、适用人群和注意事项；\n"
            f"3. 如果皮肤/体质比较敏感，先小面积或按说明试用。\n\n"
            f"以上是使用方法层面的整理，不是效果保证，也不是购买建议。"
            f"具体合不合适，还是以你自己的实际体验和官方说明为准。"
        ),
        "emoji": "✅📌📋💡✨",
        "tags": _tags(topic, ["干货分享", "选购思路", "使用方法", "经验记录"]),
    }

    gift = {
        "style_id": "gift",
        "style_name": "送礼推荐",
        "title": f"不知道送什么时，「{topic}」是一个温和的备选 🎁",
        "body": (
            f"送礼最怕两件事：太贵让对方有压力，太空又显得没用心。"
            f"如果对方日常生活里用得上，「{topic}」常常是一个不夸张、也不难收的选择。\n\n"
            f"送之前我一般会先想这 4 点：\n\n"
            f"{bullets}\n\n"
            f"几个实在建议：\n"
            f"· 先问问对方有没有忌口、过敏或已经在用的品牌，避免重复或踩雷；\n"
            f"· 把使用说明一起给到，比只给包装更贴心；\n"
            f"· 可以写一张小卡片说明「为什么想到送这个」，心意会更清楚；\n"
            f"· 不要替对方保证「用了一定喜欢」——合适与否，还是由本人决定。\n\n"
            f"适合：日常问候、节日伴手礼、贴心的小礼物。"
            f"请按预算和对方喜好选择，它不是万能礼物，只是一个可以考虑的方向。"
        ),
        "emoji": "🎁🌿💌✨😊",
        "tags": _tags(topic, ["送礼推荐", "礼物灵感", "生活好物", "贴心礼物"]),
    }
    return [funny, warm, review, gift]


def _call_openai_compatible(topic: str, points: List[str], timeout: int = 40) -> Optional[List[dict]]:
    """调用 OpenAI 兼容接口。任何失败都返回 None，由上层回退模板。"""
    api_key = (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    if not api_key:
        return None

    base = (
        os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com/v1"
    ).rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    else:
        url = base + "/chat/completions"
    model = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or "deepseek-chat"
    )

    system = (
        "你是小红书文案助手。请用中文为给定主题写 4 种风格文案："
        "搞笑吐槽、温柔治愈、干货测评、送礼推荐。"
        "每种必须包含 title、body、emoji（5 个以内）、tags（恰好 5 个中文标签，不含#）。"
        "硬性要求：不要夸大功效，不要写立即见效、药到病除、医学承诺；"
        "不要保证阅读量、销量、爆款或排名；不要虚构检测数据和用户数字；"
        "语气真实、可执行，提醒读者按自身情况判断。"
        "只返回 JSON 数组，不要 markdown。"
    )
    user = {
        "topic": topic,
        "points": points,
        "schema": [
            {
                "style_id": "funny|warm|review|gift",
                "style_name": "搞笑吐槽|温柔治愈|干货测评|送礼推荐",
                "title": "标题",
                "body": "正文",
                "emoji": "😊✨",
                "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
            }
        ],
    }

    payload = {
        "model": model,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
    }

    import urllib.error
    import urllib.request

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        obj = json.loads(raw)
        content = obj["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        items = json.loads(content)
        if not isinstance(items, list) or len(items) < 4:
            return None
        out = []
        id_map = {s[0]: s[1] for s in STYLES}
        name_map = {s[1]: s[0] for s in STYLES}
        for i, (sid, sname) in enumerate(STYLES):
            it = items[i] if i < len(items) else {}
            style_id = it.get("style_id") or sid
            style_name = it.get("style_name") or id_map.get(style_id) or sname
            if style_name in name_map:
                style_id = name_map[style_name]
            title = str(it.get("title") or "").strip()
            body = str(it.get("body") or "").strip()
            if not title or not body:
                return None
            tags = it.get("tags") or []
            if isinstance(tags, str):
                tags = [x for x in re.split(r"[#\s,，]+", tags) if x]
            tags = _tags(topic, [str(t) for t in tags])
            out.append({
                "style_id": style_id,
                "style_name": style_name,
                "title": title,
                "body": body,
                "emoji": str(it.get("emoji") or "").strip() or "✨",
                "tags": tags,
            })
        return out
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, ValueError):
        return None


def generate_copies(
    topic: str,
    points: Optional[List[str]] = None,
    use_ai: bool = False,
) -> dict:
    """返回 script + copies + source（template 或 ai）。"""
    script = default_script(topic, points)
    copies = None
    source = "template"
    if use_ai:
        copies = _call_openai_compatible(script["topic"], script["points"])
        if copies:
            source = "ai"
    if not copies:
        copies = template_copies(script["topic"], script["points"])
        source = "template"
    return {"script": script, "copies": copies, "source": source, "disclaimer": DISCLAIMER}


def render_markdown(result: dict) -> str:
    script = result["script"]
    topic = script["topic"]
    lines = [
        f"# {topic} · 小红书文案（4 种风格）",
        "",
        "由「AI文案短视频助手」生成，可复制到小红书草稿箱后，再按真实体验改一改。",
        "",
        f"- 生成方式：{'AI 接口（失败已回退模板）' if result['source']=='ai' else '离线模板（无需 API Key）'}",
        f"- 视频钩子：{script['hook']}",
        f"- 视频副标题：{script['sub']}",
        "- 四个要点：",
    ]
    for i, p in enumerate(script["points"], 1):
        lines.append(f"  {i}. {p}")
    lines += ["", "---", ""]

    for i, c in enumerate(result["copies"], 1):
        tags = " ".join("#" + t for t in c["tags"])
        lines += [
            f"## {i}. {c['style_name']}",
            "",
            "**标题**",
            "",
            c["title"],
            "",
            "**正文**",
            "",
            c["body"],
            "",
            f"**点缀 emoji**：{c.get('emoji') or '✨'}",
            "",
            "**话题标签**",
            "",
            tags,
            "",
            "---",
            "",
        ]
    lines += [DISCLAIMER, ""]
    return "\n".join(lines)
