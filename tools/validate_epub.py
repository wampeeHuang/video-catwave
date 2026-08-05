#!/usr/bin/env python3
"""EPUB verifier: checks .epub structure and validity.

Usage:
  python tools/validate_epub.py --slug <slug>

This is the VERIFICATION layer. Production: gen_epub.py (uses ebooklib).

Checks:
  1. EPUB file exists, non-empty, reasonable size (50KB-50MB)
  2. Valid ZIP archive
  3. Contains META-INF/container.xml
  4. Contains at least one .xhtml/.html chapter
  5. Has title metadata (opf)
"""

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir

MIN_SIZE_KB = 20
MAX_SIZE_MB = 50


def validate_epub(slug: str) -> tuple[bool, list[str]]:
    sdir = slug_dir(slug)
    epub_dir = sdir / "电子书"
    results: list[str] = []
    all_ok = True

    if not epub_dir.exists() or not epub_dir.is_dir():
        return False, [f"[FAIL] 电子书目录不存在: {epub_dir}"]

    epubs = list(epub_dir.glob("*.epub"))
    if not epubs:
        return False, [f"[FAIL] 电子书目录下无 .epub 文件: {epub_dir}"]

    epub_path = epubs[0]
    if len(epubs) > 1:
        results.append(f"[WARN] 多个 .epub 文件 ({len(epubs)})，检查: {epub_path.name}")

    # 1. File size
    size_kb = epub_path.stat().st_size / 1024
    size_mb = size_kb / 1024
    if size_kb < MIN_SIZE_KB:
        results.append(f"[FAIL] EPUB {size_kb:.0f}KB < {MIN_SIZE_KB}KB — 可能为空")
        all_ok = False
    elif size_mb > MAX_SIZE_MB:
        results.append(f"[FAIL] EPUB {size_mb:.1f}MB > {MAX_SIZE_MB}MB — 异常大")
        all_ok = False
    else:
        results.append(f"[OK] 文件大小 {size_kb:.0f}KB ({size_mb:.2f}MB)")

    # 2. Valid ZIP
    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            names = zf.namelist()

            # 3. Required EPUB structure
            if "META-INF/container.xml" not in names:
                results.append("[FAIL] 缺少 META-INF/container.xml — 不是有效 EPUB")
                all_ok = False
            else:
                results.append("[OK] 有效 ZIP + container.xml")

            # 4. Has content files
            xhtml_files = [n for n in names if n.endswith((".xhtml", ".html", ".htm"))]
            if not xhtml_files:
                results.append("[FAIL] 无 .xhtml/.html 章节文件")
                all_ok = False
            else:
                results.append(f"[OK] {len(xhtml_files)} 个章节文件")

            # 5. Has OPF
            opf_files = [n for n in names if n.endswith(".opf")]
            if not opf_files:
                results.append("[FAIL] 缺少 .opf 元数据文件")
                all_ok = False
            else:
                # Quick check for title in OPF
                try:
                    opf_content = zf.read(opf_files[0]).decode("utf-8", errors="replace")
                    if "<dc:title" in opf_content:
                        results.append("[OK] OPF 包含标题元数据")
                    else:
                        results.append("[WARN] OPF 缺少 dc:title")
                except Exception:
                    results.append("[WARN] 无法读取 OPF")

            # 6. Has NCX (navigation) or NAV
            has_ncx = any(n.endswith(".ncx") for n in names)
            has_nav = any("nav" in n.lower() for n in xhtml_files)
            if has_ncx or has_nav:
                results.append(f"[OK] 导航: {'NCX' if has_ncx else 'NAV'}")

            # 7. Bad ZIP entries check
            bad = zf.testzip()
            if bad:
                results.append(f"[FAIL] ZIP 损坏: {bad}")
                all_ok = False
            else:
                results.append("[OK] ZIP 完整性 OK")

    except zipfile.BadZipFile:
        results.append("[FAIL] 不是有效 ZIP 文件")
        all_ok = False
    except Exception as e:
        results.append(f"[FAIL] ZIP 读取异常: {e}")
        all_ok = False

    return all_ok, results


def main():
    p = argparse.ArgumentParser(description="验证 EPUB 电子书结构")
    p.add_argument("--slug", required=True)
    args = p.parse_args()

    ok, results = validate_epub(args.slug)
    for r in results:
        print(r)
    print(f"\n{'EPUB OK' if ok else 'EPUB NEEDS FIX'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
