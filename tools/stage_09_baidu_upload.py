"""Upload EPUB to Baidu Cloud shared folder via bypy.

Usage:
  python stage_09_baidu_upload.py --slug <slug>
  python stage_09_baidu_upload.py --epub <path.epub>

Permanent share link: https://pan.baidu.com/s/1huGTuQdCWXS0JFERhEf-8g?pwd=1234
"""
import argparse
import subprocess
import sys
from pathlib import Path

BAIDU_SHARE_LINK = "https://pan.baidu.com/s/1huGTuQdCWXS0JFERhEf-8g?pwd=1234"
BAIDU_FOLDER = "/猫波信号站电子书"
BYPOLL_INTERVAL = 5  # seconds between bypy progress polls
UPLOAD_TIMEOUT = 300  # seconds


def find_epub(slug: str) -> Path | None:
    from _lib import slug_dir

    epub_dir = slug_dir(slug) / "电子书"
    if epub_dir.exists():
        epubs = sorted(epub_dir.glob("*.epub"))
        if epubs:
            return epubs[-1]
    return None


def upload_epub(epub_path: Path) -> bool:
    cmd = [
        "bypy",
        "-v",
        "upload",
        str(epub_path),
        BAIDU_FOLDER + "/",
    ]
    print(f"  Running: bypy upload \"{epub_path.name}\" \"{BAIDU_FOLDER}/\"")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=UPLOAD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print("ERROR: Upload timed out after {UPLOAD_TIMEOUT}s")
        return False

    if result.stdout:
        for line in result.stdout.splitlines():
            if line.strip():
                print(f"  {line.strip()}")
    if result.stderr:
        for line in result.stderr.splitlines():
            s = line.strip()
            if s and not s.startswith("<W>"):
                print(f"  [stderr] {s}", file=sys.stderr)

    if result.returncode != 0:
        print(f"ERROR: bypy exited with code {result.returncode}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload EPUB to Baidu Cloud")
    parser.add_argument("--slug", help="Video slug to locate EPUB")
    parser.add_argument("--epub", help="Direct path to EPUB file")
    args = parser.parse_args()

    if args.epub:
        epub_path = Path(args.epub)
    elif args.slug:
        epub_path = find_epub(args.slug)
        if not epub_path:
            print(f"ERROR: No EPUB found for slug: {args.slug}")
            sys.exit(1)
    else:
        print("ERROR: --slug or --epub required")
        sys.exit(1)

    if not epub_path.exists():
        print(f"ERROR: EPUB not found: {epub_path}")
        sys.exit(1)

    size_kb = epub_path.stat().st_size / 1024
    print(f"EPUB:  {epub_path.name} ({size_kb:.0f} KB)")
    print(f"Dest:  {BAIDU_FOLDER}/")
    print()

    if upload_epub(epub_path):
        print()
        print(f"Upload complete.")
        print(f"Share: {BAIDU_SHARE_LINK}")
        print(f"Code:  1234")
    else:
        print()
        print("Upload failed. Check bypy auth: bypy info")
        sys.exit(1)


if __name__ == "__main__":
    main()
