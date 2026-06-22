"""Stage ⑤: DeepSeek EN→ZH translation + proper noun post-processing.

Usage: python stage_05_translate.py --slug <slug>
Input:  <output>/_runtime/字幕/02_seg_clean.srt
Output: <output>/_runtime/字幕/03_zh.srt
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import SubEntry, read_srt, srt_path, write_srt


# Proper noun whitelist: patterns in Chinese → correct English
PROPER_NOUN_FIXES: list[tuple[str, str]] = [
    ("光标", "Cursor"),
    ("黄金 Cursor 选项卡", "黄金 Cursor Tab"),
]


def run(slug: str, *, api_key: str | None = None, batch_size: int = 10):
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    src = srt_path(slug, "02_seg_clean.srt")
    if not src.exists():
        print(f"ERROR: {src} not found. Run stage_04 first.")
        sys.exit(1)

    if not api_key:
        print("[⑤] No DEEPSEEK_API_KEY, skipping translation")
        return

    entries = read_srt(src)
    print(f"[⑤] Translating {len(entries)} entries...")

    batches = [entries[i:i + batch_size] for i in range(0, len(entries), batch_size)]
    translated = [None] * len(entries)

    with ThreadPoolExecutor(max_workers=min(len(batches), 5)) as executor:
        futures = {}
        for bi, batch in enumerate(batches):
            futures[executor.submit(_translate_batch, batch, api_key)] = bi * batch_size

        for f in as_completed(futures):
            offset = futures[f]
            try:
                for j, zh_text in enumerate(f.result()):
                    if zh_text:
                        idx = offset + j
                        en_text = entries[idx].text.strip()
                        translated[idx] = SubEntry(
                            entries[idx].index, entries[idx].start, entries[idx].end,
                            f"{zh_text}\\N{en_text}",
                        )
            except Exception as exc:
                print(f"  Batch at offset {offset} failed: {exc}")

    for i, e in enumerate(entries):
        if translated[i] is None:
            translated[i] = SubEntry(e.index, e.start, e.end, f"[未翻译]\\N{e.text.strip()}")

    zh_path = srt_path(slug, "03_zh.srt")
    write_srt(translated, zh_path)
    print(f"  → {zh_path.name}")

    # Post-process proper nouns
    _fix_proper_nouns(zh_path)


def _translate_batch(batch: list[SubEntry], api_key: str) -> list[str]:
    texts = [e.text.strip() for e in batch]
    n = len(batch)

    system_prompt = (
        "You are a professional EN→ZH subtitle translator. "
        f"Translate EXACTLY {n} lines below. Output {n} numbered lines (1. 2. ... {n}.). "
        "One Chinese translation per line. No explanations, no extra text. "
        "CRITICAL: translate EVERY line — even garbled ASR artifacts. "
        "If the English is unreadable, give your best guess. "
        f"Your output MUST contain exactly {n} non-empty numbered lines. "
        "IMPORTANT — keep these names UNTRANSLATED (留英文): "
        "Cursor, Copilot, GitHub Copilot, Claude, Sonnet, GPT, GPT-4, OpenAI, "
        "Anthropic, VS Code, Visual Studio Code, Vim, Neovim, JetBrains, "
        "IntelliJ, macOS, Windows, Linux, AWS, GCP, Azure, "
        "JavaScript, TypeScript, Python, Rust, Go, React, Node.js, "
        "API, GPU, CPU, SSD, CUDA, PyTorch, TensorFlow, "
        "Stripe, Slack, Discord, Zoom, Google, Microsoft, Apple, Meta, "
        "DeepSeek, Llama, Gemini, o1, ChatGPT, "
        "Lex Fridman, Elon Musk, Sam Altman."
    )

    prompt = f"Translate these {n} English subtitle lines to Chinese:\n\n"
    for i, t in enumerate(texts, 1):
        prompt += f"{i}. {t}\n"

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                }).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
                content = body["choices"][0]["message"]["content"].strip()
                raw = [l.strip() for l in content.split("\n") if l.strip()]
                lines = []
                for l in raw:
                    m = re.match(r"^\d+[\.\)\s、\)]\s*(.*)", l)
                    if m:
                        t = m.group(1).strip()
                        if t:
                            lines.append(t)
                    elif not re.match(r"^\d+$", l):
                        lines.append(l)

                if len(lines) == n:
                    return lines
                if len(lines) > n:
                    return lines[:n]

                if attempt < 2:
                    print(f"  Line mismatch (got {len(lines)}), retry {attempt+2}...")
                    time.sleep(2 ** attempt)
                    continue

                while len(lines) < n:
                    lines.append(f"[跳过:{texts[len(lines)][:30]}]")
                return lines[:n]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise e


def _fix_proper_nouns(srt_path: Path):
    entries = read_srt(srt_path)
    fixed_count = 0
    for e in entries:
        parts = e.text.split("\\N", 1)
        zh = parts[0]
        en = parts[1] if len(parts) > 1 else ""
        for pattern, replacement in PROPER_NOUN_FIXES:
            if pattern in zh:
                zh = zh.replace(pattern, replacement)
                fixed_count += 1
        e.text = f"{zh}\\N{en}" if len(parts) > 1 else zh
    write_srt(entries, srt_path)
    if fixed_count:
        print(f"  Proper noun fixes: {fixed_count}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="⑤ EN→ZH translation")
    p.add_argument("--slug", required=True)
    args = p.parse_args()
    run(args.slug)
