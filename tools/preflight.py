"""Preflight gate — validate all inputs before production starts.

Usage:
  python tools/preflight.py --slug <slug> [--check-deps] [--check-api]

Exit 0 = all gates pass, production can proceed.
Exit 1 = gate failure, do NOT proceed to production.

Checks (ordered — fail fast):
  1. Slug directory exists
  2. Required input files exist and are non-empty (per pipeline_manifest.STAGES)
  3. Chinese transcript exists and is non-empty (B站 compliance prerequisite)
  4. Dependencies importable (optional, --check-deps)
  5. API keys available (optional, --check-api)
"""

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir
from pipeline_manifest import STAGES, VALIDATORS


def check_inputs(slug: str) -> list[str]:
    """Validate all stage required_inputs exist and are non-empty. Returns errors."""
    sdir = slug_dir(slug)
    errors = []

    for stage_name, contract in STAGES.items():
        for rel in contract["required_inputs"]:
            fp = sdir / rel
            if not fp.exists():
                errors.append(f"[{stage_name}] 缺失: {rel}")
            elif fp.is_file() and fp.stat().st_size == 0:
                errors.append(f"[{stage_name}] 空文件: {rel}")

    return errors


def check_chinese_transcript(slug: str) -> list[str]:
    """Chinese transcript MUST exist and be non-empty — compliance prerequisite."""
    sdir = slug_dir(slug)
    errors = []

    zh_srt = sdir / "_runtime" / "字幕" / "03_zh.srt"
    transcript = sdir / "_runtime" / "字幕" / "transcript.txt"

    has_content = False
    for fp in [zh_srt, transcript]:
        if fp.exists() and fp.stat().st_size > 100:  # >100 bytes = real content
            has_content = True
            break

    if not has_content:
        errors.append(
            "B站合规阻断: 中文稿不存在或为空。"
            "合规检查无法扫描敏感内容，禁止继续生产。\n"
            f"  期望路径: {zh_srt} 或 {transcript}"
        )

    return errors


def check_deps() -> list[str]:
    """Verify all Python dependencies importable. Returns errors."""
    errors = []
    required = {
        "PIL": "Pillow",
        "ebooklib": "ebooklib",
    }
    for mod, pkg in required.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            errors.append(f"依赖缺失: {pkg} (import {mod} 失败)")
    return errors


def check_validators() -> list[str]:
    """Verify all registered validators are importable. Returns errors."""
    errors = []
    for name, (module_name, func_name) in VALIDATORS.items():
        try:
            mod = importlib.import_module(module_name)
            if not hasattr(mod, func_name):
                errors.append(f"Validator 未注册: {module_name}.{func_name}() 不存在")
        except ImportError:
            errors.append(f"Validator 模块缺失: {module_name}.py (注册于 manifest)")
    return errors


def check_api_keys() -> list[str]:
    """Verify required API keys are available. Returns errors."""
    errors = []
    from _lib import get_deepseek_key
    if not get_deepseek_key():
        errors.append("DEEPSEEK_API_KEY 未设置（翻译步骤需要）")
    return errors


def run_preflight(slug: str, check_deps_flag: bool = False,
                  check_api_flag: bool = False,
                  check_files: bool = True) -> tuple[bool, list[str]]:
    """Run all preflight checks. Returns (passed, all_messages).

    check_files=False skips file existence checks (use before pipeline runs).
    """
    all_ok = True
    messages = []

    def run(label: str, errors: list[str]):
        nonlocal all_ok
        messages.append(f"\n── {label} ──")
        if errors:
            all_ok = False
            for e in errors:
                messages.append(f"  FAIL  {e}")
        else:
            messages.append("  OK")

    if check_files:
        run("输入文件完整性", check_inputs(slug))
        run("中文稿合规前置", check_chinese_transcript(slug))

    if check_deps_flag:
        run("Python依赖", check_deps())
        run("Validator注册", check_validators())

    if check_api_flag:
        run("API密钥", check_api_keys())

    return all_ok, messages


def main():
    p = argparse.ArgumentParser(description="管线输入门禁")
    p.add_argument("--slug", required=True)
    p.add_argument("--check-deps", action="store_true", help="检查Python依赖和validator注册")
    p.add_argument("--check-api", action="store_true", help="检查API密钥")
    args = p.parse_args()

    ok, messages = run_preflight(args.slug, args.check_deps, args.check_api)
    for m in messages:
        print(m)

    if ok:
        print("\n✓ 所有门禁通过，可以进入生产")
    else:
        print(f"\n✗ 门禁未通过，禁止生产")
        sys.exit(1)


if __name__ == "__main__":
    main()
