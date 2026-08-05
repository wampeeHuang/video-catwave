"""B站合规检查 — 硬门禁。扫描中文字幕，命中敏感词 → 阻断生产。

Usage:
  python check_bilibili_compliance.py --slug <slug>
Exit 0 = clean, 1 = blocked (must edit before upload), 2 = warning (review manually)
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir

# Red-line patterns — any match = BLOCK production
RED_LINE = [
    # Taiwan sovereignty
    r"中国入侵台湾", r"中共入侵", r"台湾独立", r"台湾主权",
    # Xinjiang / Tibet
    r"新疆.*(?:独立|种族灭绝|集中营|再教育营)", r"西藏.*(?:独立|流亡|镇压)",
    # Hong Kong
    r"香港.*(?:独立|革命|光复)", r"反送中",
    # CCP / government attacks
    r"中共.*(?:独裁|专制|暴政|邪恶)", r"共产党.*(?:独裁|专制|暴政)",
    r"中国.*(?:独裁|威权|专制|暴政)",
    # Sensitive events
    r"六四", r"天安门.*(?:事件|屠杀|镇压|清场)", r"法轮功",
    # Military / war against China
    r"(?:攻击|入侵|打击).{0,10}(?:中国|台湾|香港)", r"对华战争",
    # Territorial claims
    r"中华民国(?!.*(?:历史|年代|时期))",
]

# Warning patterns — flag for manual review, don't block
WARNING = [
    r"台湾.{0,5}(?:防卫|安全|军事|武器)", r"南海.{0,5}(?:争端|冲突|军事)",
    r"蒋介石", r"毛泽东(?!.*(?:语录|诗词|时代))",
    r"维吾尔", r"香港.{0,5}(?:抗议|示威|自治)",
    r"共产党(?!员|员|章|宣言|宣言|校|学校|员先锋)",
    r"民主.{0,5}(?:运动|抗争|化|转型)",
    r"审查.{0,5}(?:制度|机制|体系)", r"(?:政治|言论).{0,5}(?:审查|管控|镇压)",
    r"加沙.{0,5}(?:战争|冲突|轰炸)", r"巴勒斯坦.{0,5}(?:抵抗|武装|占领)",
]


def check(slug: str) -> tuple[int, list[str], list[str]]:
    """Scan transcript. Returns (exit_code, red_hits, warning_hits)."""
    sdir = slug_dir(slug)
    zh_srt = sdir / "_runtime" / "字幕" / "03_zh.srt"
    transcript = sdir / "_runtime" / "字幕" / "transcript.txt"

    text = ""
    for p in [zh_srt, transcript]:
        if p.exists():
            text += p.read_text(encoding="utf-8") + "\n"

    if not text.strip():
        print(f"BLOCKED: 中文稿不存在或为空，合规检查无法执行")
        print(f"  期望路径: {zh_srt} 或 {transcript}")
        return 1, ["中文稿缺失，无法扫描敏感内容"], []

    red_hits = []
    for pattern in RED_LINE:
        matches = re.finditer(pattern, text)
        for m in matches:
            ctx_start = max(0, m.start() - 30)
            ctx_end = min(len(text), m.end() + 30)
            ctx = text[ctx_start:ctx_end].replace("\n", " ")
            red_hits.append(f"  RED: {m.group()} → ...{ctx}...")
            break  # one hit per pattern is enough

    warning_hits = []
    for pattern in WARNING:
        matches = re.finditer(pattern, text)
        for m in matches:
            if any(p.search(m.group()) for p in [re.compile(r) for r in RED_LINE]):
                continue  # already caught by RED
            ctx_start = max(0, m.start() - 30)
            ctx_end = min(len(text), m.end() + 30)
            ctx = text[ctx_start:ctx_end].replace("\n", " ")
            warning_hits.append(f"  WARN: {m.group()} → ...{ctx}...")
            break

    exit_code = 0
    if red_hits:
        exit_code = 1
    elif warning_hits:
        exit_code = 2

    return exit_code, red_hits, warning_hits


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="B站合规检查")
    p.add_argument("--slug", required=True)
    p.add_argument("--soft", action="store_true",
                   help="Soft mode: warn but don't block (exit 0 even on red hits)")
    args = p.parse_args()

    code, reds, warns = check(args.slug)

    if reds:
        print(f"\n{'='*50}")
        print(f"BLOCKED: B站红线命中 ({len(reds)} patterns)")
        print(f"{'='*50}")
        for r in reds:
            print(r)
        print(f"\n必须删除或修改敏感内容后才能上传。")

    if warns:
        print(f"\n{'='*50}")
        print(f"WARNING: 建议人工审核 ({len(warns)} patterns)")
        print(f"{'='*50}")
        for w in warns:
            print(w)

    if not reds and not warns:
        print(f"OK: B站合规检查通过")

    sys.exit(code if not args.soft else 0)
