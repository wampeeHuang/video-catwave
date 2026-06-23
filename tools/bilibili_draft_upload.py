"""B站草稿上传 — 使用 bilibili-api-python 的 VideoUploader + 草稿 API。

Usage:
  python bilibili_draft_upload.py --video <mp4> --metadata <json> --cookie-file <txt> [--cover <jpg>]
"""
import argparse
import json
import sys
from pathlib import Path

import bilibili_api.video_uploader as vu
from bilibili_api import Credential


def parse_cookie_file(path):
    """Parse raw cookie header into dict."""
    text = Path(path).read_text(encoding="utf-8").strip()
    d = {}
    for item in text.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--cookie-file", required=True)
    parser.add_argument("--cover", default=None)
    parser.add_argument("--tid", type=int, default=208)
    parser.add_argument("--copyright", type=int, default=2)
    parser.add_argument("--no-reprint", type=int, default=1)
    args = parser.parse_args()

    video_path = Path(args.video)
    metadata_path = Path(args.metadata)
    cover_path = Path(args.cover) if args.cover else None

    with open(metadata_path, encoding="utf-8") as f:
        meta = json.load(f)

    cookies = parse_cookie_file(args.cookie_file)
    credential = Credential(
        sessdata=cookies.get("SESSDATA", ""),
        bili_jct=cookies.get("bili_jct", ""),
        buvid3=cookies.get("buvid3", ""),
        buvid4=cookies.get("buvid4", ""),
        dedeuserid=cookies.get("DedeUserID", ""),
    )

    if not credential.bili_jct:
        print("ERROR: bili_jct not found in cookie")
        sys.exit(1)

    print(f"Video:  {video_path.name} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"Title:  {meta['title']}")
    print(f"Tags:   {len(meta.get('tags', []))} tags")
    print(f"Cover:  {cover_path.name if cover_path else 'N/A'}")

    import asyncio

    async def run():
        # Monkey-patch submit URL → draft
        vu._API["submit"]["url"] = "https://member.bilibili.com/x/vupre/web/archive/drafts"
        print("  submit URL patched → draft")

        page = vu.VideoUploaderPage(str(video_path), title=meta["title"])
        meta_obj = vu.VideoMeta(
            tid=args.tid,
            title=meta["title"],
            desc=meta.get("description", ""),
            cover=str(cover_path) if cover_path else "",
            tags=meta.get("tags", [])[:10],
            original=(args.copyright == 1),
            source=meta.get("source", ""),
            no_reprint=(args.no_reprint == 1),
        )

        uploader = vu.VideoUploader(
            pages=[page],
            meta=meta_obj,
            credential=credential,
            cover=str(cover_path) if cover_path else None,
            line=vu.Lines.BDA2,
        )

        print("Starting upload (this may take a while for large files)...")
        result = await uploader.start()
        print(f"Result: {result}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
