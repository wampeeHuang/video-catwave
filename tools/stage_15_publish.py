"""B站自动投稿 · 直连 API，Cookie 认证。

Usage:
  python stage_15_publish.py --video <mp4> --metadata <json> --cookie <str> [--cover <jpg>]

依赖: requests
"""
import argparse
import base64
import json
import math
import mimetypes
import sys
from pathlib import Path

import requests


BILIBILI_PREUPLOAD = "https://member.bilibili.com/preupload"
BILIBILI_UPLOAD_FINISH = "https://member.bilibili.com/x/vupre/web/upload/upload"
BILIBILI_COVER_UP = "https://member.bilibili.com/x/vu/web/cover/up"
BILIBILI_ADD = "https://member.bilibili.com/x/vu/web/add"
BILIBILI_DRAFT = "https://member.bilibili.com/x/vupre/web/archive/drafts"
BILIBILI_CHAPTERS = "https://api.bilibili.com/x/v2/upload/video/chapters/edit"


def cookie_to_dict(cookie_str):
    """Parse raw cookie header into dict."""
    d = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def get_csrf(cookies):
    return cookies.get("bili_jct", "")


def upos_path(upos_uri):
    """Extract path from UPOS URI (strip 'upos://' prefix)."""
    return upos_uri.replace("upos://", "")


def make_api_session():
    """Session for B站 API + CDN uploads (via proxy)."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://member.bilibili.com/",
        "Origin": "https://member.bilibili.com",
    })
    # Connection pooling for proxy stability
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=4,
        pool_maxsize=4,
        max_retries=0,
    )
    s.mount("https://", adapter)
    return s


def pre_upload(video_path, cookies, session):
    """Step 1: pre-upload to get upload endpoint + auth token."""
    name = video_path.name
    size = video_path.stat().st_size
    params = {
        "name": name,
        "size": size,
        "r": "upos",
        "profile": "ugcupos/bup",
        "version": "2.10.4.0",
    }
    resp = session.get(BILIBILI_PREUPLOAD, params=params, cookies=cookies, timeout=30)
    data = resp.json()
    if data.get("OK") != 1:
        raise RuntimeError(f"Pre-upload failed: {data}")
    chunk_size = data.get("chunk_size", 10 * 1024 * 1024)
    print(f"  pre-upload OK: endpoint={data.get('endpoint')}, chunks={math.ceil(size / chunk_size)}")
    return data


def init_multipart_upload(pre_data, session):
    """Step 2: initiate multipart upload session, get upload_id."""
    endpoint = pre_data["endpoint"].lstrip("/")
    path = upos_path(pre_data["upos_uri"])
    auth = pre_data["auth"]
    url = f"https://{endpoint}/{path}?uploads&output=json"
    headers = {"X-Upos-Auth": auth}
    resp = session.post(url, headers=headers, timeout=30)
    data = resp.json()
    upload_id = data.get("upload_id")
    if not upload_id:
        raise RuntimeError(f"Init multipart upload failed: {data}")
    print(f"  init multipart OK: upload_id={upload_id[:20]}...")
    return upload_id


def upload_chunks(video_path, pre_data, upload_id, session, pace=0.5):
    """Step 3: upload file in chunks via UPOS multipart protocol with retry."""
    endpoint = pre_data["endpoint"].lstrip("/")
    path = upos_path(pre_data["upos_uri"])
    auth = pre_data["auth"]
    chunk_size = pre_data.get("chunk_size", 10 * 1024 * 1024)

    file_size = video_path.stat().st_size
    total_chunks = math.ceil(file_size / chunk_size)
    etags = []

    headers = {
        "X-Upos-Auth": auth,
        "Content-Type": "application/octet-stream",
    }

    import time

    with open(video_path, "rb") as f:
        i = 0
        while i < total_chunks:
            f.seek(i * chunk_size)
            chunk = f.read(chunk_size)
            start = i * chunk_size
            end = start + len(chunk) - 1
            params = (
                f"partNumber={i + 1}&uploadId={upload_id}"
                f"&chunk={i}&chunks={total_chunks}"
                f"&size={len(chunk)}&start={start}&end={end}&total={file_size}"
            )
            url = f"https://{endpoint}/{path}?{params}"
            for attempt in range(8):
                try:
                    resp = session.put(url, data=chunk, headers=headers, timeout=300)
                    resp.raise_for_status()
                    etag = resp.headers.get("ETag", "")
                    etags.append(etag)
                    break
                except requests.exceptions.RequestException as e:
                    if attempt == 7:
                        raise
                    wait = 2 ** attempt
                    print(f"  chunk {i+1}/{total_chunks} retry {attempt+1}/8 after {wait}s: {e}")
                    time.sleep(wait)
            if (i + 1) % 10 == 0 or i == total_chunks - 1:
                print(f"  chunk {i+1}/{total_chunks} OK")
            i += 1
            if pace > 0:
                time.sleep(pace)

    return etags


def finish_upload(video_path, pre_data, upload_id, etags, cookies, upos_session, api_session):
    """Step 4: notify UPOS upload completion via CDN, then register via B站 API."""
    endpoint = pre_data["endpoint"].lstrip("/")
    path = upos_path(pre_data["upos_uri"])
    auth = pre_data["auth"]
    biz_id = pre_data.get("biz_id", "")

    # UPOS completion: POST with parts JSON (CDN)
    upos_url = (
        f"https://{endpoint}/{path}?output=json"
        f"&name={video_path.name}&profile=ugcupos%2Fbup"
        f"&uploadId={upload_id}&biz_id={biz_id}"
    )
    parts = [{"partNumber": i + 1, "eTag": etag} for i, etag in enumerate(etags)]
    headers = {"X-Upos-Auth": auth, "Content-Type": "application/json"}
    resp = upos_session.post(upos_url, json={"parts": parts}, headers=headers, timeout=30)
    upos_data = resp.json()
    print(f"  UPOS complete: {upos_data}")

    # B站 upload finish: register the uploaded video (API)
    csrf = get_csrf(cookies)
    params = {
        "name": video_path.name,
        "biz_id": biz_id,
        "profile": "ugcupos/bup",
        "csrf": csrf,
    }
    resp = api_session.post(BILIBILI_UPLOAD_FINISH, data=params, cookies=cookies, timeout=30)
    data = resp.json()
    if data.get("OK") != 1:
        raise RuntimeError(f"Upload finish failed: {data}")
    aid = data["data"]["aid"]
    cid = data["data"]["cid"]
    print(f"  upload finish OK: aid={aid}, cid={cid}")
    return aid, cid


def upload_cover(cover_path, cookies, session):
    """Step 4: upload cover image, return URL."""
    csrf = get_csrf(cookies)
    mime, _ = mimetypes.guess_type(cover_path) or ("image/jpeg",)
    with open(cover_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"

    form = {"cover": data_uri, "csrf": csrf}
    resp = session.post(BILIBILI_COVER_UP, data=form, cookies=cookies, timeout=30)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Cover upload failed: {data}")
    cover_url = data["data"]["url"]
    print(f"  cover upload OK: {cover_url[:60]}...")
    return cover_url


def submit(video_path, aid, cid, cover_url, metadata, cookies, session, draft=False, copyright=2, tid=208, no_reprint=1):
    """Step 5: submit video with metadata (or save as draft)."""
    csrf = get_csrf(cookies)
    videos = json.dumps([{"aid": aid, "cid": cid, "filename": video_path.name, "title": metadata["title"]}])

    form = {
        "copyright": copyright,
        "cover": cover_url,
        "title": metadata["title"],
        "tid": tid,
        "tag": ",".join(metadata.get("tags", [])[:10]),
        "desc_format_id": "0",
        "desc": metadata.get("description", ""),
        "source": metadata.get("source", ""),
        "no_reprint": no_reprint,
        "videos": videos,
        "csrf": csrf,
    }

    if draft:
        url = BILIBILI_DRAFT
        resp = session.post(url, data=form, cookies=cookies, timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Draft save failed: {data}")
        draft_id = data.get("data", {}).get("draft_id", "?")
        print(f"  draft saved OK: draft_id={draft_id}")
    else:
        url = f"{BILIBILI_ADD}?csrf={csrf}"
        resp = session.post(url, data=form, cookies=cookies, timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Submit failed: {data}")
        print(f"  submit OK: code={data['code']}")
    return data


def set_chapters(aid, chapters, cookies, session):
    """Step 6: set video chapters (B站 max 10).

    Accepts two formats:
      - [{"time": "00:00:00", "title": "..."}, ...]  (pass through)
      - [["00:00:00", "..."], ...]                    (convert)
    """
    csrf = get_csrf(cookies)
    normalized = []
    for ch in chapters[:10]:
        if isinstance(ch, dict):
            normalized.append(ch)
        elif isinstance(ch, (list, tuple)) and len(ch) >= 2:
            normalized.append({"time": ch[0], "title": ch[1]})
    payload = {"video_id": aid, "chapters": normalized}
    params = {"csrf": csrf}
    resp = session.post(BILIBILI_CHAPTERS, params=params, json=payload, cookies=cookies, timeout=30)
    data = resp.json()
    if data.get("code") != 0:
        print(f"  WARNING: chapters API returned: {data}")
    else:
        print(f"  chapters OK: {len(normalized)} chapters set")


def main():
    parser = argparse.ArgumentParser(description="B站自动投稿")
    parser.add_argument("--video", required=True, help="视频文件路径 (.mp4)")
    parser.add_argument("--metadata", required=True, help="元数据 JSON 路径 (metadata.json)")
    parser.add_argument("--cookie", required=True, help="Cookie 字符串 (从浏览器复制完整 cookie header)")
    parser.add_argument("--cover", default=None, help="封面图片路径 (.jpg)")
    parser.add_argument("--tid", type=int, default=208, help="分区 ID (默认 208=科技>人工智能)")
    parser.add_argument("--copyright", type=int, default=2, help="1=自制 2=转载 (默认 2)")
    parser.add_argument("--no-reprint", type=int, default=1, help="禁止转载 (默认 1)")
    parser.add_argument("--draft", action="store_true", help="存入草稿箱，不直接发布")
    parser.add_argument("--dry-run", action="store_true", help="只验证参数，不上传")
    args = parser.parse_args()

    video_path = Path(args.video)
    metadata_path = Path(args.metadata)
    cover_path = Path(args.cover) if args.cover else None

    if not video_path.exists():
        print(f"ERROR: video not found: {video_path}")
        sys.exit(1)
    if not metadata_path.exists():
        print(f"ERROR: metadata not found: {metadata_path}")
        sys.exit(1)
    if cover_path and not cover_path.exists():
        print(f"ERROR: cover not found: {cover_path}")
        sys.exit(1)

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    cookies = cookie_to_dict(args.cookie)
    bili_jct = get_csrf(cookies)
    if not bili_jct:
        print("ERROR: bili_jct not found in cookie")
        sys.exit(1)

    print(f"Video:  {video_path.name} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"Title:  {metadata['title']}")
    print(f"Tags:   {len(metadata.get('tags', []))} tags")
    print(f"Cover:  {cover_path.name if cover_path else 'N/A'}")
    print(f"Cookie: bili_jct={bili_jct[:8]}***, DedeUserID={cookies.get('DedeUserID', '?')}")

    if args.dry_run:
        print("\n[Dry run] 跳过上传。")
        return

    mode = "draft" if args.draft else "publish"
    total = 6 if args.draft else 7
    print(f"\nMode: {mode} ({total} steps)")

    api = make_api_session()

    print(f"\n[1/{total}] Pre-upload...")
    pre_data = pre_upload(video_path, cookies, api)

    print(f"[2/{total}] Init multipart upload...")
    upload_id = init_multipart_upload(pre_data, api)

    print(f"[3/{total}] Upload chunks...")
    etags = upload_chunks(video_path, pre_data, upload_id, api)

    print(f"[4/{total}] Finish upload...")
    aid, cid = finish_upload(video_path, pre_data, upload_id, etags, cookies, api, api)

    print(f"[5/{total}] Upload cover...")
    if cover_path:
        cover_url = upload_cover(cover_path, cookies, api)
    else:
        cover_url = ""

    if args.draft:
        print(f"[6/{total}] Save draft...")
        submit(video_path, aid, cid, cover_url, metadata, cookies, api, draft=True,
               copyright=args.copyright, tid=args.tid, no_reprint=args.no_reprint)
        print(f"\nDraft saved. aid={aid}")
        print("章节/定时发布等需在B站创作中心手动设置。")
    else:
        print(f"[6/{total}] Submit...")
        submit(video_path, aid, cid, cover_url, metadata, cookies, api,
               copyright=args.copyright, tid=args.tid, no_reprint=args.no_reprint)

        print(f"[7/{total}] Set chapters...")
        chapters = metadata.get("chapters", [])
        if chapters:
            set_chapters(aid, chapters, cookies, api)
        else:
            print("  No chapters in metadata, skipping.")

        print(f"\nDone. aid={aid}")


if __name__ == "__main__":
    main()
