r"""B站 CDP 浏览器自动化上传 · Bit Browser DevTools Protocol.

大文件 (>500MB) 走 CDP 浏览器上传，绕过 API 限速。
小文件优先用 stage_15_publish.py (API 直连)。

Usage:
  python tools/stage_16_cdp_upload.py --slug <slug> --page-id <CDP_PAGE_ID>
      [--title "标题"] [--tags "tag1,tag2,..."] [--port 55054]

前置条件:
  1. Bit Browser 已打开并登录 B站
  2. 浏览器中已打开一个 B站页面（任意页面，脚本会导航到上传页）
  3. 获取 PAGE_ID: curl http://127.0.0.1:55054/json

产出目录自动检测:
  D:\workspace\_output\猫波信号站\视频\<slug>\\
    ├── cover.jpg
    ├── 成片/<title>.mp4
    └── _runtime/metadata.json
"""

import argparse
import json
import sys
import time
import websocket
from pathlib import Path

# Fix GBK console encoding on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir as _slug_dir
BILI_UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"
BILI_MANAGE_URL = "https://member.bilibili.com/platform/upload-manage"


# ═══════════════════════════════════════════════════════════════
# CDP 连接
# ═══════════════════════════════════════════════════════════════

def cdp_connect(port, page_id):
    """Connect to Bit Browser CDP WebSocket, return (ws, send) tuple."""
    ws = websocket.create_connection(
        f"ws://127.0.0.1:{port}/devtools/page/{page_id}",
        timeout=30, suppress_origin=True
    )
    msg_id = [0]

    def send(method, params=None, timeout=20):
        msg_id[0] += 1
        mid = msg_id[0]
        msg = {"id": mid, "method": method}
        if params is not None:
            msg["params"] = params
        ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            ws.settimeout(max(1, deadline - time.time()))
            try:
                resp = json.loads(ws.recv())
            except Exception:
                return {"error": "timeout"}
            if resp.get("id") == mid:
                return resp
        return {"error": "timeout"}

    return ws, send


# ═══════════════════════════════════════════════════════════════
# 鼠标操作
# ═══════════════════════════════════════════════════════════════

def native_click(send, x, y, delay=0.5):
    """CDP mouse click at screen coordinates."""
    send("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y,
        "button": "left", "clickCount": 1
    })
    time.sleep(0.05)
    send("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y,
        "button": "left", "clickCount": 1
    })
    time.sleep(delay)


# ═══════════════════════════════════════════════════════════════
# 页面导航
# ═══════════════════════════════════════════════════════════════

def navigate_to_upload(send):
    """Navigate to B站 upload page and wait for load."""
    send("Page.enable")
    send("Page.navigate", {"url": BILI_UPLOAD_URL})
    time.sleep(4)
    send("Runtime.enable")
    r = send("Runtime.evaluate", {
        "expression": "document.title"
    })
    title = r.get("result", {}).get("result", {}).get("value", "")
    print(f"  页面标题: {title}")
    return "创作中心" in str(title)


# ═══════════════════════════════════════════════════════════════
# 视频上传
# ═══════════════════════════════════════════════════════════════

def upload_video(send, video_path):
    """Upload video via CDP DOM.setFileInputFiles + progress monitoring.

    Returns True if upload started successfully.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        print(f"  ERROR: video not found: {video_path}")
        return False

    print(f"  视频: {video_path.name} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Enable DOM
    send("DOM.enable")

    # Find video file input
    doc = send("DOM.getDocument", {"depth": 3})
    root = doc.get("result", {}).get("root", {}).get("nodeId", 0)
    q = send("DOM.querySelectorAll", {"nodeId": root, "selector": 'input[type="file"]'})
    all_ids = q.get("result", {}).get("nodeIds", [])

    video_input_id = None
    for nid in all_ids:
        attrs = send("DOM.getAttributes", {"nodeId": nid})
        attr_list = attrs.get("result", {}).get("attributes", [])
        accept = ""
        for j, a in enumerate(attr_list):
            if a == "accept" and j + 1 < len(attr_list):
                accept = attr_list[j + 1]
        if accept and ".mp4" in accept:
            video_input_id = nid
            print(f"  找到视频 input: nodeId={nid}")
            break

    if not video_input_id:
        # Fallback: any file input that accepts video formats
        for nid in all_ids:
            attrs = send("DOM.getAttributes", {"nodeId": nid})
            attr_list = attrs.get("result", {}).get("attributes", [])
            for j, a in enumerate(attr_list):
                if a == "accept" and j + 1 < len(attr_list):
                    accept = attr_list[j + 1]
                    if any(ext in accept for ext in [".mp4", ".avi", ".mov", ".flv"]):
                        video_input_id = nid
                        print(f"  找到视频 input (fallback): nodeId={nid}")
                        break
            if video_input_id:
                break

    if not video_input_id:
        print("  ERROR: 未找到视频上传 input")
        return False

    r = send("DOM.setFileInputFiles", {
        "files": [str(video_path)],
        "nodeId": video_input_id
    }, timeout=15)
    if r.get("error"):
        print(f"  ERROR: 设置文件失败: {r['error']}")
        return False

    # Dispatch change event
    send("Runtime.evaluate", {
        "expression": """
        (() => {
            const inputs = document.querySelectorAll('input[type="file"]');
            for (const inp of inputs) {
                if (inp.accept && inp.accept.includes('.mp4')) {
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                    return 'fired';
                }
            }
            return 'no match';
        })()
        """
    })
    print("  上传已启动，监控进度...")
    return True


def monitor_upload(send, max_wait=3600, poll_interval=5):
    """Monitor upload progress until completion or timeout.

    Returns (completed, progress_pct).
    """
    start = time.time()
    last_pct = 0
    while time.time() - start < max_wait:
        time.sleep(poll_interval)
        r = send("Runtime.evaluate", {
            "expression": """
            (() => {
                const body = document.body.innerText;
                const match = body.match(/(\\d+\\.?\\d*)\\s*%/);
                return match ? match[1] : null;
            })()
            """
        })
        pct = r.get("result", {}).get("result", {}).get("value")
        if pct and pct != "null":
            pct_val = float(pct)
            if pct_val >= 100:
                print(f"  上传完成: {pct_val}%")
                return True, pct_val
            if pct_val - last_pct >= 10:
                print(f"  进度: {pct_val:.0f}%")
                last_pct = pct_val
            continue

        # Check if page redirected (upload complete)
        r = send("Runtime.evaluate", {
            "expression": "location.href"
        })
        url = r.get("result", {}).get("result", {}).get("value", "")
        if "home" in str(url) or "upload-manage" in str(url):
            print(f"  页面已跳转: {url}")
            return True, 100.0

    print(f"  监控超时 ({max_wait}s)")
    return False, last_pct


# ═══════════════════════════════════════════════════════════════
# 表单填写
# ═══════════════════════════════════════════════════════════════

def fill_title(send, title):
    """Set title via native input setter (Vue-compatible)."""
    r = send("Runtime.evaluate", {
        "expression": f"""
        (() => {{
            const inp = document.querySelector('input[placeholder*="标题"]');
            if (!inp) return 'NO_INPUT';
            const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            s.call(inp, {json.dumps(title)});
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return inp.value.length;
        }})()
        """
    })
    result = r.get("result", {}).get("result", {}).get("value")
    print(f"  标题: {result}/80 chars")
    return result and result != "NO_INPUT"


def fill_description(send, description):
    """Set description via contenteditable div."""
    r = send("Runtime.evaluate", {
        "expression": f"""
        (() => {{
            const div = document.querySelector('div[contenteditable="true"]');
            if (!div) return 'NO_DIV';
            div.focus();
            div.innerText = {json.dumps(description)};
            div.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return div.innerText.length;
        }})()
        """
    })
    result = r.get("result", {}).get("result", {}).get("value")
    print(f"  简介: {result} chars")
    return result and result != "NO_DIV"


def click_recommended_tags(send, target_tags):
    """Click recommended tags that match target_tags by label text."""
    if not target_tags:
        print("  标签: 无目标标签，跳过")
        return 0

    clicked = 0
    for tag_text in target_tags:
        r = send("Runtime.evaluate", {
            "expression": f"""
            (() => {{
                const items = document.querySelectorAll('.hot-tag-item, [class*="hot-tag"], [class*="recommend-tag"]');
                for (const item of items) {{
                    if (item.innerText.trim() === {json.dumps(tag_text)}) {{
                        const rect = item.getBoundingClientRect();
                        if (rect.width > 0) {{
                            return JSON.stringify({{x: rect.left + rect.width/2, y: rect.top + rect.height/2, found: true}});
                        }}
                    }}
                }}
                return JSON.stringify({{found: false}});
            }})()
            """
        })
        val = r.get("result", {}).get("result", {}).get("value", "{}")
        try:
            pos = json.loads(val)
        except Exception:
            pos = {"found": False}
        if pos.get("found"):
            native_click(send, pos["x"], pos["y"], delay=0.3)
            clicked += 1
            print(f"  标签点击: {tag_text}")
    print(f"  标签: {clicked}/{len(target_tags)} 个推荐标签已点击")
    return clicked


def delete_tag_by_text(send, tag_text):
    """Delete a tag by clicking its SVG close button."""
    r = send("Runtime.evaluate", {
        "expression": f"""
        (() => {{
            const items = document.querySelectorAll('.label-item-v2-container');
            for (const item of items) {{
                const content = item.querySelector('.label-item-v2-content');
                if (content && content.innerText.trim() === {json.dumps(tag_text)}) {{
                    const svg = item.querySelector('svg.close, svg[class*="close"]');
                    if (svg) {{
                        const rect = svg.getBoundingClientRect();
                        if (rect.width > 0) {{
                            return JSON.stringify({{x: rect.left + rect.width/2, y: rect.top + rect.height/2, found: true}});
                        }}
                    }}
                }}
            }}
            return JSON.stringify({{found: false}});
        }})()
        """
    })
    val = r.get("result", {}).get("result", {}).get("value", "{}")
    try:
        pos = json.loads(val)
    except Exception:
        pos = {"found": False}
    if pos.get("found"):
        native_click(send, pos["x"], pos["y"], delay=0.3)
        return True
    return False


def set_creation_statement(send, statement="含AI生成内容"):
    """Set 创作声明 by manipulating Vue component $data."""
    r = send("Runtime.evaluate", {
        "expression": f"""
        (() => {{
            const container = document.querySelector('.creation-statement-container');
            if (!container) return 'NO_CONTAINER';
            const bccSelect = container.querySelector('.bcc-select');
            if (!bccSelect || !bccSelect.__vue__) return 'NO_VUE';

            const v = bccSelect.__vue__;
            const oldVal = v.selectedLabel;

            // Check available options
            if (v.options) {{
                const target = v.options.find(o =>
                    (o.label || o.text || '').includes({json.dumps(statement[:4])})
                );
                if (target) {{
                    v.selectedLabel = target.label || target.text;
                    v.$forceUpdate();
                    return JSON.stringify({{old: oldVal, new: v.selectedLabel, ok: true}});
                }}
                return JSON.stringify({{options: v.options.map(o => o.label || o.text), ok: false}});
            }}

            // Direct set
            v.selectedLabel = {json.dumps(statement)};
            v.$forceUpdate();
            return JSON.stringify({{old: oldVal, new: v.selectedLabel, ok: true}});
        }})()
        """
    })
    result = r.get("result", {}).get("result", {}).get("value")
    print(f"  创作声明: {result}")
    try:
        data = json.loads(result) if isinstance(result, str) else result
        return data.get("ok", False) if isinstance(data, dict) else False
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 封面上传
# ═══════════════════════════════════════════════════════════════

def upload_cover(send, cover_path):
    """Upload cover via CDP: open editor → set file → confirm.

    Known limitation: B站 Vue bcc-upload component may not process
    the file set via DOM.setFileInputFiles. If the cover doesn't
    update after "完成", manual upload is needed.
    """
    cover_path = Path(cover_path)
    if not cover_path.exists():
        print(f"  ERROR: cover not found: {cover_path}")
        return False

    send("DOM.enable")

    # Step 1: Click cover area to open editor
    r = send("Runtime.evaluate", {
        "expression": """
        (() => {
            const el = document.querySelector('.cover-img, .cover-empty, .cover-main');
            if (!el) return 'NO_COVER';
            el.scrollIntoView({block: 'center'});
            const rect = el.getBoundingClientRect();
            return JSON.stringify({x: rect.left + rect.width/2, y: rect.top + rect.height/2});
        })()
        """
    })
    val = r.get("result", {}).get("result", {}).get("value", "{}")
    try:
        pos = json.loads(val)
    except Exception:
        print("  封面区域未找到")
        return False

    if not pos.get("x"):
        print("  封面区域未找到")
        return False

    native_click(send, pos["x"], pos["y"], delay=2.0)
    print("  封面编辑器已打开")

    # Step 2: Check editor opened
    r = send("Runtime.evaluate", {
        "expression": """
        (() => {
            const editor = document.querySelector('.cover-editor');
            if (!editor || editor.getBoundingClientRect().height < 100)
                return JSON.stringify({open: false});
            return JSON.stringify({open: true});
        })()
        """
    })
    val = r.get("result", {}).get("result", {}).get("value", "{}")
    try:
        ed_state = json.loads(val)
    except Exception:
        ed_state = {"open": False}

    if not ed_state.get("open"):
        print("  WARNING: 封面编辑器未正常打开")
        return False

    # Step 3: Find cover file input and set file
    doc = send("DOM.getDocument", {"depth": 4})
    root_id = doc.get("result", {}).get("root", {}).get("nodeId", 0)
    q = send("DOM.querySelectorAll", {"nodeId": root_id, "selector": 'input[type="file"]'})
    all_ids = q.get("result", {}).get("nodeIds", [])

    cover_set = False
    for nid in all_ids:
        attrs = send("DOM.getAttributes", {"nodeId": nid})
        attr_list = attrs.get("result", {}).get("attributes", [])
        accept = ""
        for j, a in enumerate(attr_list):
            if a == "accept" and j + 1 < len(attr_list):
                accept = attr_list[j + 1]
        if accept and "image/png" in accept and "image/jpeg" in accept:
            r = send("DOM.setFileInputFiles", {
                "files": [str(cover_path)],
                "nodeId": nid
            }, timeout=10)
            if not r.get("error"):
                cover_set = True
                print(f"  封面文件已设置 (nodeId={nid})")

                # Dispatch change event
                send("Runtime.evaluate", {
                    "expression": """
                    (() => {
                        const inputs = document.querySelectorAll(
                            'input[type="file"][accept*="image/png"]'
                        );
                        let count = 0;
                        inputs.forEach(inp => {
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            count++;
                        });
                        return count;
                    })()
                    """
                })
                time.sleep(1.5)
            break

    if not cover_set:
        print("  WARNING: 未找到封面文件 input")
        return False

    # Step 4: Click "完成" button
    r = send("Runtime.evaluate", {
        "expression": """
        (() => {
            const editor = document.querySelector('.cover-editor');
            if (!editor) return 'NOT_FOUND';

            // Search for the "完成" div button (class: button submit)
            const all = editor.querySelectorAll('*');
            for (const el of all) {
                const text = el.innerText.trim();
                if (text === '完成' && el.children.length <= 2 && el.tagName === 'DIV') {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0) {
                        return JSON.stringify({
                            x: rect.left + rect.width/2,
                            y: rect.top + rect.height/2
                        });
                    }
                }
            }
            return 'NOT_FOUND';
        })()
        """
    })
    val = r.get("result", {}).get("result", {}).get("value", "{}")
    try:
        done_pos = json.loads(val)
    except Exception:
        done_pos = None

    if done_pos and done_pos.get("x") and done_pos.get("x") > 100:
        native_click(send, done_pos["x"], done_pos["y"], delay=2.0)
        print("  '完成' 已点击")

        # Verify editor closed
        r = send("Runtime.evaluate", {
            "expression": """
            (() => {
                const editor = document.querySelector('.cover-editor');
                return editor && editor.getBoundingClientRect().height > 100
                    ? 'open' : 'closed';
            })()
            """
        })
        ed_status = r.get("result", {}).get("result", {}).get("value")
        print(f"  编辑器状态: {ed_status}")
        return ed_status == "closed"
    else:
        print("  '完成' 按钮未找到，尝试 Escape 关闭")
        send("Input.dispatchKeyEvent", {
            "type": "keyDown", "key": "Escape",
            "code": "Escape", "windowsVirtualKeyCode": 27
        })
        time.sleep(0.1)
        send("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Escape",
            "code": "Escape", "windowsVirtualKeyCode": 27
        })
        return False


# ═══════════════════════════════════════════════════════════════
# 存草稿
# ═══════════════════════════════════════════════════════════════

def save_draft(send):
    """Click 存草稿 button."""
    r = send("Runtime.evaluate", {
        "expression": """
        (() => {
            const span = document.querySelector('.submit-draft');
            if (!span) return 'NOT_FOUND';
            span.scrollIntoView({block: 'center'});
            const rect = span.getBoundingClientRect();
            return JSON.stringify({
                x: rect.left + rect.width/2,
                y: rect.top + rect.height/2
            });
        })()
        """
    })
    val = r.get("result", {}).get("result", {}).get("value", "{}")
    try:
        pos = json.loads(val)
    except Exception:
        pos = None

    if pos and pos.get("x"):
        native_click(send, pos["x"], pos["y"], delay=3.0)

        # Check for error
        r = send("Runtime.evaluate", {
            "expression": """
            (() => {
                const body = document.body.innerText;
                return JSON.stringify({
                    hasError: body.includes('请求错误'),
                    hasSuccess: body.includes('保存成功') || body.includes('已存入'),
                    url: location.href,
                });
            })()
            """
        })
        result = r.get("result", {}).get("result", {}).get("value", "{}")
        try:
            state = json.loads(result)
        except Exception:
            state = {}
        print(f"  存草稿: error={state.get('hasError')}, success={state.get('hasSuccess')}")
        return not state.get("hasError", True)
    else:
        print("  存草稿按钮未找到")
        return False


# ═══════════════════════════════════════════════════════════════
# 状态检查
# ═══════════════════════════════════════════════════════════════

def check_form_state(send):
    """Print current form state for verification."""
    r = send("Runtime.evaluate", {
        "expression": """
        (() => {
            const cs = document.querySelector('.creation-statement-container input.bcc-select-input-inner');
            const title = document.querySelector('input[placeholder*="标题"]');
            const desc = document.querySelector('div[contenteditable="true"]');
            const tags = [];
            document.querySelectorAll('.label-item-v2-content').forEach(t => tags.push(t.innerText.trim()));
            const coverImg = document.querySelector('.cover-img');
            const coverBg = coverImg ? coverImg.style.backgroundImage : '';

            return JSON.stringify({
                title: title ? title.value.length + '/80' : 'NO',
                descLen: desc ? desc.innerText.length : 0,
                cs: cs ? cs.value : 'NO',
                tags,
                coverBg: coverBg ? coverBg.substring(0, 120) : 'none',
                url: location.href,
            });
        })()
        """
    })
    result = r.get("result", {}).get("result", {}).get("value", "{}")
    try:
        state = json.loads(result)
    except Exception:
        state = {}
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return state


# ═══════════════════════════════════════════════════════════════
# 自动发现产出目录
# ═══════════════════════════════════════════════════════════════

def find_assets(slug):
    """Find cover, video, and metadata for a given slug."""
    base = _slug_dir(slug)
    if not base.exists():
        print(f"ERROR: slug 目录不存在: {base}")
        sys.exit(1)

    # Cover
    cover = base / "cover.jpg"
    if not cover.exists():
        print(f"WARNING: cover not found: {cover}")
        cover = None

    # Video (in 成片/)
    video_dir = base / "成片"
    video = None
    if video_dir.exists():
        videos = list(video_dir.glob("*.mp4"))
        if videos:
            video = videos[0]  # Take first mp4
            if len(videos) > 1:
                # Prefer non-测试 files
                for v in videos:
                    if "测试" not in v.name:
                        video = v
                        break

    # Metadata
    metadata = base / "_runtime" / "metadata.json"
    if not metadata.exists():
        print(f"WARNING: metadata not found: {metadata}")
        metadata = None

    return {
        "cover": cover,
        "video": video,
        "metadata": metadata,
    }


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="B站 CDP 浏览器自动化上传",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 自动发现 slug 目录下的 cover/video/metadata
  python tools/stage_16_cdp_upload.py --slug 20260624_dan-shipper-ai-native-lenny \\
      --page-id 6B7AAF237254D318C94EDE10CE07B0A4

  # 手动指定参数
  python tools/stage_16_cdp_upload.py --video "成片/视频.mp4" --cover cover.jpg \\
      --title "标题" --tags "tag1,tag2" --description "简介..." \\
      --page-id 6B7AAF237254D318C94EDE10CE07B0A4

  # 只填表单不传视频（视频已上传）
  python tools/stage_16_cdp_upload.py --slug <slug> --page-id <id> --no-upload
        """
    )

    # Slug-based auto-discovery
    parser.add_argument("--slug", help="产出目录 slug (自动发现 cover/video/metadata)")

    # Manual overrides
    parser.add_argument("--video", help="视频文件路径 (.mp4)")
    parser.add_argument("--cover", help="封面图片路径 (.jpg)")
    parser.add_argument("--metadata", help="元数据 JSON 路径")
    parser.add_argument("--title", help="视频标题 (≤80字)")
    parser.add_argument("--tags", help="标签,逗号分隔 (≤10个)")
    parser.add_argument("--description", help="视频简介")

    # CDP connection
    parser.add_argument("--page-id", required=True, help="CDP 页面 ID (从 http://127.0.0.1:55054/json 获取)")
    parser.add_argument("--port", type=int, default=55054, help="CDP 端口 (默认 55054)")

    # Steps control
    parser.add_argument("--no-upload", action="store_true", help="跳过视频上传 (视频已在页面中)")
    parser.add_argument("--no-fill", action="store_true", help="跳过表单填写")
    parser.add_argument("--no-cover", action="store_true", help="跳过封面上传")
    parser.add_argument("--no-save", action="store_true", help="跳过存草稿")
    parser.add_argument("--check-only", action="store_true", help="只检查表单状态，不做任何操作")

    args = parser.parse_args()

    # --- Resolve assets ---
    cover_path = None
    video_path = None
    title = args.title
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    description = args.description

    if args.slug:
        assets = find_assets(args.slug)
        cover_path = assets["cover"] or args.cover
        video_path = assets["video"] or args.video

        if assets["metadata"] and not (args.title and args.tags and args.description):
            with open(assets["metadata"], "r", encoding="utf-8") as f:
                meta = json.load(f)
            if not title:
                title = meta.get("title", "")
            if not tags:
                tags = meta.get("tags", [])
            if not description:
                description = meta.get("description", "")
    else:
        cover_path = args.cover
        video_path = args.video

    # Print plan
    print("=" * 60)
    print("B站 CDP 上传管线")
    print("=" * 60)
    print(f"  CDP:  ws://127.0.0.1:{args.port}/devtools/page/{args.page_id}")
    print(f"  视频: {video_path or 'N/A (--no-upload)'}")
    print(f"  封面: {cover_path or 'N/A (--no-cover)'}")
    print(f"  标题: {title or 'N/A'} ({len(title or '')}/80)")
    print(f"  标签: {tags}")
    print(f"  简介: {len(description or '')} chars")
    print()

    # --- Connect ---
    print("[连接]")
    try:
        ws, send = cdp_connect(args.port, args.page_id)
    except Exception as e:
        print(f"  ERROR: CDP 连接失败: {e}")
        print(f"  请确认 Bit Browser 已打开，CDP port={args.port}")
        print(f"  获取 page-id: curl http://127.0.0.1:{args.port}/json")
        sys.exit(1)
    print("  已连接")

    try:
        # --- Check only ---
        if args.check_only:
            print("\n[状态检查]")
            check_form_state(send)
            return

        # --- Navigate ---
        print("\n[导航]")
        navigate_to_upload(send)

        # --- Upload video ---
        if not args.no_upload and video_path:
            print("\n[视频上传]")
            if upload_video(send, video_path):
                monitor_upload(send)
        elif args.no_upload:
            print("\n[视频上传] 跳过 (--no-upload)")

        # --- Fill form ---
        if not args.no_fill:
            print("\n[表单填写]")
            if title:
                fill_title(send, title)

            if description:
                fill_description(send, description)

            if tags:
                click_recommended_tags(send, tags)

            # 创作声明
            set_creation_statement(send, "含AI生成内容")

        # --- Cover ---
        if not args.no_cover and cover_path:
            print("\n[封面上传]")
            ok = upload_cover(send, cover_path)
            if not ok:
                print("  ⚠ 封面上传可能未生效，请手动确认")

        # --- Check state ---
        print("\n[表单状态]")
        state = check_form_state(send)

        # --- Save draft ---
        if not args.no_save:
            print("\n[存草稿]")
            ok = save_draft(send)
            if ok:
                print("  ✓ 草稿保存成功，请在 Bit Browser 中确认")
            else:
                print("  ⚠ 草稿保存失败，请手动点击「存草稿」")

        # --- Final reminder ---
        print("\n" + "=" * 60)
        print("管线完成。请手动检查：")
        print("  1. 创作声明 → 含AI内容生成")
        print("  2. 封面上传是否生效")
        print("  3. 在稿件管理页确认草稿存在")
        print("=" * 60)

    finally:
        ws.close()


if __name__ == "__main__":
    main()
