#!/usr/bin/env python3
"""
小红书笔记发布脚本
支持：图文发布、视频发布、创作者信息查看、笔记列表查看

用法:
  python3 publish.py image --title "标题" --desc "内容" --images "img1.jpg,img2.jpg"
  python3 publish.py video --title "标题" --desc "内容" --video "video.mp4"
  python3 publish.py info
  python3 publish.py notes
"""
import argparse
import json
import os
import sys
import time

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
COOKIE_FILE = os.path.join(DATA_DIR, ".cookie.json")

SIGN_SERVER = os.environ.get("XHS_SIGN_SERVER", "")


# ─── Cookie & Sign ───────────────────────────────────────

def load_cookie() -> str:
    """加载 cookie 字符串"""
    if not os.path.exists(COOKIE_FILE):
        print("❌ 未找到 Cookie，请先导入:")
        print(f"   python3 {SCRIPT_DIR}/cookie_manager.py import \"cookie字符串\"")
        sys.exit(1)
    with open(COOKIE_FILE, "r") as f:
        data = json.load(f)
    return data["cookie_string"]


def get_cookie_dict(cookie_str: str) -> dict:
    """解析 cookie 字符串"""
    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def do_sign(uri: str, data=None, a1: str = "", web_session: str = "") -> dict:
    """签名：优先使用 xhs 内置签名，回退到外部签名服务"""
    # 优先使用 xhs 库内置签名（无需浏览器/Docker）
    try:
        from xhs.help import sign as xhs_sign
        result = xhs_sign(uri, data, a1=a1)
        return {
            "x-s": result["x-s"],
            "x-t": result["x-t"],
            "x-s-common": result.get("x-s-common", ""),
        }
    except ImportError:
        pass

    # 回退到外部签名服务
    if SIGN_SERVER:
        try:
            res = requests.post(
                f"{SIGN_SERVER}/sign",
                json={"uri": uri, "data": data, "a1": a1, "web_session": web_session},
                timeout=10
            )
            signs = res.json()
            return {"x-s": signs["x-s"], "x-t": signs["x-t"]}
        except Exception as e:
            print(f"❌ 签名服务不可用: {e}")
            sys.exit(1)

    print("❌ 无可用签名方式（需要 xhs 库或外部签名服务）")
    print("   安装: pip3 install xhs")
    sys.exit(1)


def check_prerequisites():
    """检查前置条件"""
    # 检查签名能力
    try:
        from xhs.help import sign as _
        # xhs 内置签名可用，无需外部服务
    except ImportError:
        if not SIGN_SERVER:
            print("❌ 需要签名能力：安装 xhs 包或启动签名服务")
            print("   pip3 install xhs  (推荐)")
            print("   或: docker start xhs-sign-server")
            sys.exit(1)

    # 检查 cookie
    if not os.path.exists(COOKIE_FILE):
        print("❌ 未找到 Cookie")
        print(f"   请先导入: python3 {SCRIPT_DIR}/cookie_manager.py import \"cookie\"")
        sys.exit(1)


# ─── XHS Client (轻量版，不依赖 xhs 包) ──────────────────

class XhsPublisher:
    """轻量级小红书发布客户端，直接使用 requests + 签名服务"""

    def __init__(self, cookie_str: str):
        self.cookie_str = cookie_str
        self.cookies = get_cookie_dict(cookie_str)
        self.a1 = self.cookies.get("a1", "")
        self.web_session = self.cookies.get("web_session", "")
        self.session = requests.Session()
        self.session.headers.update({
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "origin": "https://www.xiaohongshu.com",
            "referer": "https://www.xiaohongshu.com/",
            "cookie": cookie_str,
        })
        self._host = "https://edith.xiaohongshu.com"
        self._creator_host = "https://creator.xiaohongshu.com"

    def _sign_and_set(self, uri: str, data=None):
        """签名并设置请求头"""
        signs = do_sign(uri, data, a1=self.a1, web_session=self.web_session)
        self.session.headers.update({k: v for k, v in signs.items() if v})

    def _get(self, uri: str, params=None, host=None):
        final_uri = uri
        if isinstance(params, dict) and params:
            final_uri = f"{uri}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        self._sign_and_set(final_uri)
        endpoint = host or self._host
        # 设置正确的 origin/referer
        if endpoint == self._creator_host:
            self.session.headers.update({
                "origin": "https://creator.xiaohongshu.com",
                "referer": "https://creator.xiaohongshu.com/",
            })
        resp = self.session.get(f"{endpoint}{final_uri}", timeout=15)
        # 恢复默认 origin/referer
        self.session.headers.update({
            "origin": "https://www.xiaohongshu.com",
            "referer": "https://www.xiaohongshu.com/",
        })
        return self._handle_response(resp)

    def _post(self, uri: str, data: dict = None, host=None, extra_headers=None):
        json_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False) if data else None
        self._sign_and_set(uri, data)
        endpoint = host or self._host
        headers = {}
        if extra_headers:
            headers.update(extra_headers)
        resp = self.session.post(
            f"{endpoint}{uri}",
            data=json_str.encode("utf-8") if json_str else None,
            timeout=30,
            headers=headers,
        )
        return self._handle_response(resp)

    def _handle_response(self, resp):
        if not resp.text:
            return resp
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return resp

        if resp.status_code in (461, 471):
            verify_type = resp.headers.get("Verifytype", "unknown")
            print(f"❌ 触发风控验证码 (Verifytype: {verify_type})")
            print("   建议等待几分钟后重试，或检查 cookie 是否过期")
            sys.exit(1)
        elif data.get("success"):
            return data.get("data", data.get("success"))
        else:
            code = data.get("code", "unknown")
            msg = data.get("msg", str(data))
            print(f"❌ API 错误 [{code}]: {msg}")
            sys.exit(1)

    # ─── 用户信息 ──────────────

    def get_self_info(self) -> dict:
        return self._get("/api/sns/web/v2/user/me")

    def get_creator_info(self) -> dict:
        self.session.headers.update({
            "referer": "https://creator.xiaohongshu.com/creator/home"
        })
        return self._get("/api/galaxy/creator/home/personal_info",
                         host=self._creator_host)

    def get_creator_notes(self, page: int = 0) -> dict:
        self.session.headers.update({
            "Referer": "https://creator.xiaohongshu.com/new/note-manager"
        })
        return self._get("/api/galaxy/creator/note/user/posted",
                         params={"tab": 0, "page": page},
                         host=self._creator_host)

    # ─── 上传 ──────────────────

    def get_upload_permit(self, file_type: str = "image") -> tuple:
        """获取上传许可，返回 (file_id, token)"""
        # scene: "image" for images, "video" for video
        # NOTE: scene 必须是 "image" 不是 "images"，否则返回空 permits
        scene = "image" if file_type == "image" else "video"
        params = {
            "biz_name": "spectrum",
            "scene": scene,
            "file_count": "1",
            "version": "1",
            "source": "web",
        }
        res = self._get("/api/media/v1/upload/web/permit", params=params,
                        host=self._creator_host)
        permits = res.get("uploadTempPermits", [])
        if not permits:
            msg = res.get("result", {}).get("message", "unknown error")
            print(f"❌ 获取上传许可失败: {msg}")
            sys.exit(1)
        permit = permits[0]
        file_id = permit["fileIds"][0]
        token = permit["token"]
        return file_id, token

    def upload_file(self, file_id: str, token: str, file_path: str,
                    content_type: str = "image/jpeg"):
        """上传文件到小红书 CDN"""
        url = f"https://ros-upload.xiaohongshu.com/{file_id}"
        headers = {
            "X-Cos-Security-Token": token,
            "Content-Type": content_type,
        }
        # 移除 session 默认的 Content-Type
        with open(file_path, "rb") as f:
            resp = requests.put(url, data=f, headers=headers, timeout=120)
        if resp.status_code not in (200, 204):
            print(f"❌ 上传失败 [{resp.status_code}]: {resp.text[:200]}")
            sys.exit(1)
        return resp

    # ─── 话题 & AT ─────────────

    def get_suggest_topics(self, keyword: str) -> list:
        """获取话题建议"""
        data = {
            "keyword": keyword,
            "suggest_topic_request": {"title": "", "desc": ""},
            "page": {"page_size": 20, "page": 1},
        }
        res = self._post("/web_api/sns/v1/search/topic", data)
        return res.get("topic_info_dtos", [])

    def get_suggest_ats(self, keyword: str) -> list:
        """获取 @ 用户建议"""
        data = {
            "keyword": keyword,
            "search_id": str(int(time.time() * 1000)),
            "page": {"page_size": 20, "page": 1},
        }
        res = self._post("/web_api/sns/v1/search/user_info", data)
        return res.get("user_info_dtos", [])

    # ─── 发布 ──────────────────

    def create_image_note(self, title: str, desc: str, image_paths: list,
                          topics: list = None, ats: list = None,
                          post_time: str = None, is_private: bool = False) -> dict:
        """发布图文笔记"""
        images = []
        for i, path in enumerate(image_paths):
            abs_path = os.path.expanduser(path.strip())
            if not os.path.exists(abs_path):
                print(f"❌ 图片不存在: {abs_path}")
                sys.exit(1)

            print(f"  📤 上传图片 {i+1}/{len(image_paths)}: {os.path.basename(abs_path)}...")
            file_id, token = self.get_upload_permit("image")

            # 根据扩展名判断 content_type
            ext = os.path.splitext(abs_path)[1].lower()
            ct_map = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
            content_type = ct_map.get(ext, "image/jpeg")

            self.upload_file(file_id, token, abs_path, content_type)
            images.append({
                "file_id": file_id,
                "metadata": {"source": -1},
                "stickers": {"version": 2, "floating": []},
                "extra_info_json": json.dumps({"mimeType": content_type}),
            })
            print(f"  ✅ 图片 {i+1} 上传成功")

        # 处理话题
        hash_tags = []
        if topics:
            for t in topics:
                t = t.strip().lstrip("#")
                if t:
                    suggestions = self.get_suggest_topics(t)
                    if suggestions:
                        tag = suggestions[0]
                        hash_tags.append({
                            "id": tag.get("id", ""),
                            "name": tag.get("name", t),
                            "link": tag.get("link", ""),
                            "type": "topic",
                        })
                    else:
                        hash_tags.append({
                            "id": "", "name": t, "link": "", "type": "topic"
                        })

        # 处理 @
        at_users = []
        if ats:
            for a in ats:
                a = a.strip().lstrip("@")
                if a:
                    suggestions = self.get_suggest_ats(a)
                    if suggestions:
                        user = suggestions[0]
                        at_users.append({
                            "user_id": user.get("user_id", ""),
                            "nickname": user.get("nickname", a),
                        })

        # 定时发布
        post_timestamp = None
        if post_time:
            from datetime import datetime
            dt = datetime.strptime(post_time, "%Y-%m-%d %H:%M:%S")
            post_timestamp = round(int(dt.timestamp()) * 1000)

        # 构造发布请求
        business_binds = json.dumps({
            "version": 1,
            "noteId": 0,
            "noteOrderBind": {},
            "notePostTiming": {"postTime": post_timestamp},
            "noteCollectionBind": {"id": ""}
        }, separators=(",", ":"))

        data = {
            "common": {
                "type": "normal",
                "title": title,
                "note_id": "",
                "desc": desc,
                "source": '{"type":"web","ids":"","extraInfo":"{\\"subType\\":\\"official\\"}"}',
                "business_binds": business_binds,
                "ats": at_users,
                "hash_tag": hash_tags,
                "post_loc": {},
                "privacy_info": {"op_type": 1, "type": int(is_private)},
            },
            "image_info": {"images": images},
            "video_info": None,
        }

        print("  📝 提交发布请求...")
        headers = {
            "Origin": "https://creator.xiaohongshu.com",
            "Referer": "https://creator.xiaohongshu.com/",
        }
        return self._post("/web_api/sns/v2/note", data, extra_headers=headers)

    def create_video_note(self, title: str, desc: str, video_path: str,
                          cover_path: str = None, topics: list = None,
                          ats: list = None, post_time: str = None,
                          is_private: bool = False) -> dict:
        """发布视频笔记"""
        abs_video = os.path.expanduser(video_path.strip())
        if not os.path.exists(abs_video):
            print(f"❌ 视频不存在: {abs_video}")
            sys.exit(1)

        print(f"  📤 上传视频: {os.path.basename(abs_video)}...")
        file_id, token = self.get_upload_permit("video")
        resp = self.upload_file(file_id, token, abs_video, "video/mp4")
        video_id = resp.headers.get("X-Ros-Video-Id", "")
        print("  ✅ 视频上传成功")

        # 封面
        is_upload = False
        image_id = None
        if cover_path:
            abs_cover = os.path.expanduser(cover_path.strip())
            if os.path.exists(abs_cover):
                print(f"  📤 上传封面: {os.path.basename(abs_cover)}...")
                image_id, img_token = self.get_upload_permit("image")
                self.upload_file(image_id, img_token, abs_cover)
                is_upload = True
                print("  ✅ 封面上传成功")
        
        if not image_id:
            # 等待自动截取首帧
            print("  ⏳ 等待视频首帧截取...")
            for _ in range(10):
                time.sleep(3)
                try:
                    frame_resp = self.session.post(
                        "https://www.xiaohongshu.com/fe_api/burdock/v2/note/query_transcode",
                        json={"videoId": video_id},
                        headers={
                            "content-type": "application/json;charset=UTF-8",
                            "referer": "https://creator.xiaohongshu.com/",
                        },
                        timeout=10
                    )
                    frame_data = frame_resp.json()
                    if frame_data.get("data", {}).get("hasFirstFrame"):
                        image_id = frame_data["data"]["firstFrameFileId"]
                        print("  ✅ 首帧截取成功")
                        break
                except Exception:
                    pass

        # 处理话题 & @（复用图文的逻辑）
        hash_tags = []
        if topics:
            for t in topics:
                t = t.strip().lstrip("#")
                if t:
                    suggestions = self.get_suggest_topics(t)
                    if suggestions:
                        tag = suggestions[0]
                        hash_tags.append({
                            "id": tag.get("id", ""),
                            "name": tag.get("name", t),
                            "link": tag.get("link", ""),
                            "type": "topic",
                        })

        at_users = []
        if ats:
            for a in ats:
                a = a.strip().lstrip("@")
                if a:
                    suggestions = self.get_suggest_ats(a)
                    if suggestions:
                        user = suggestions[0]
                        at_users.append({
                            "user_id": user.get("user_id", ""),
                            "nickname": user.get("nickname", a),
                        })

        post_timestamp = None
        if post_time:
            from datetime import datetime
            dt = datetime.strptime(post_time, "%Y-%m-%d %H:%M:%S")
            post_timestamp = round(int(dt.timestamp()) * 1000)

        cover_info = {
            "file_id": image_id,
            "frame": {"ts": 0, "is_user_select": False, "is_upload": is_upload},
        }
        video_info = {
            "file_id": file_id,
            "timelines": [],
            "cover": cover_info,
            "chapters": [],
            "chapter_sync_text": False,
            "entrance": "web",
        }

        business_binds = json.dumps({
            "version": 1,
            "noteId": 0,
            "noteOrderBind": {},
            "notePostTiming": {"postTime": post_timestamp},
            "noteCollectionBind": {"id": ""}
        }, separators=(",", ":"))

        data = {
            "common": {
                "type": "video",
                "title": title,
                "note_id": "",
                "desc": desc,
                "source": '{"type":"web","ids":"","extraInfo":"{\\"subType\\":\\"official\\"}"}',
                "business_binds": business_binds,
                "ats": at_users,
                "hash_tag": hash_tags,
                "post_loc": {},
                "privacy_info": {"op_type": 1, "type": int(is_private)},
            },
            "image_info": None,
            "video_info": video_info,
        }

        print("  📝 提交发布请求...")
        headers = {
            "Origin": "https://creator.xiaohongshu.com",
            "Referer": "https://creator.xiaohongshu.com/",
        }
        return self._post("/web_api/sns/v2/note", data, extra_headers=headers)


# ─── CLI ─────────────────────────────────────────────────

def cmd_image(args):
    """发布图文笔记"""
    check_prerequisites()
    cookie = load_cookie()
    client = XhsPublisher(cookie)

    # 验证用户
    info = client.get_self_info()
    print(f"👤 当前用户: {info.get('nickname', '未知')}")

    images = [p.strip() for p in args.images.split(",") if p.strip()]
    if not images:
        print("❌ 请提供至少一张图片")
        sys.exit(1)

    topics = [t.strip() for t in args.topics.split(",") if t.strip()] if args.topics else None
    ats = [a.strip() for a in args.ats.split(",") if a.strip()] if args.ats else None

    print(f"\n📋 发布图文笔记")
    print(f"  标题: {args.title}")
    print(f"  图片: {len(images)} 张")
    if topics:
        print(f"  话题: {', '.join(topics)}")
    if args.schedule:
        print(f"  定时: {args.schedule}")
    if args.private:
        print(f"  私密: 是")
    print()

    result = client.create_image_note(
        title=args.title,
        desc=args.desc,
        image_paths=images,
        topics=topics,
        ats=ats,
        post_time=args.schedule,
        is_private=args.private,
    )

    print("\n" + "=" * 40)
    if isinstance(result, dict):
        note_id = result.get("note_id", result.get("noteId", ""))
        print(f"✅ 发布成功！")
        if note_id:
            print(f"  笔记ID: {note_id}")
            print(f"  链接: https://www.xiaohongshu.com/explore/{note_id}")
    else:
        print(f"✅ 发布请求已提交")
    print(json.dumps(result, indent=2, ensure_ascii=False) if isinstance(result, dict) else str(result))


def cmd_video(args):
    """发布视频笔记"""
    check_prerequisites()
    cookie = load_cookie()
    client = XhsPublisher(cookie)

    info = client.get_self_info()
    print(f"👤 当前用户: {info.get('nickname', '未知')}")

    topics = [t.strip() for t in args.topics.split(",") if t.strip()] if args.topics else None
    ats = [a.strip() for a in args.ats.split(",") if a.strip()] if args.ats else None

    print(f"\n📋 发布视频笔记")
    print(f"  标题: {args.title}")
    print(f"  视频: {args.video}")
    print()

    result = client.create_video_note(
        title=args.title,
        desc=args.desc,
        video_path=args.video,
        cover_path=args.cover,
        topics=topics,
        ats=ats,
        post_time=args.schedule,
        is_private=args.private,
    )

    print("\n" + "=" * 40)
    if isinstance(result, dict):
        note_id = result.get("note_id", result.get("noteId", ""))
        print(f"✅ 发布成功！")
        if note_id:
            print(f"  笔记ID: {note_id}")
            print(f"  链接: https://www.xiaohongshu.com/explore/{note_id}")
    else:
        print(f"✅ 发布请求已提交")


def cmd_info(args):
    """查看创作者信息"""
    check_prerequisites()
    cookie = load_cookie()
    client = XhsPublisher(cookie)

    print("📊 创作者信息")
    print("=" * 40)
    info = client.get_self_info()
    print(f"  昵称: {info.get('nickname', '')}")
    print(f"  小红书号: {info.get('red_id', '')}")
    print(f"  性别: {'女' if info.get('gender') == 1 else '男' if info.get('gender') == 0 else '未知'}")
    print(f"  简介: {info.get('desc', '')}")


def cmd_notes(args):
    """查看已发布笔记列表"""
    check_prerequisites()
    cookie = load_cookie()
    client = XhsPublisher(cookie)

    print("📝 已发布笔记")
    print("=" * 40)
    result = client.get_creator_notes()
    if isinstance(result, dict):
        notes = result.get("notes", [])
        for note in notes[:20]:
            title = note.get("display_title", "无标题")
            note_type = "📹" if note.get("type") == "video" else "🖼️"
            interact = note.get("interact_info", {})
            likes = interact.get("liked_count", "0")
            print(f"  {note_type} {title}  ❤️{likes}")
    else:
        print("  暂无笔记")


def main():
    parser = argparse.ArgumentParser(description="小红书笔记发布工具")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # image 子命令
    p_image = subparsers.add_parser("image", help="发布图文笔记")
    p_image.add_argument("--title", required=True, help="笔记标题（≤20字）")
    p_image.add_argument("--desc", required=True, help="笔记正文")
    p_image.add_argument("--images", required=True, help="图片路径，逗号分隔")
    p_image.add_argument("--topics", default="", help="话题标签，逗号分隔")
    p_image.add_argument("--ats", default="", help="@用户，逗号分隔")
    p_image.add_argument("--schedule", default=None, help="定时发布 (格式: 2026-03-29 10:00:00)")
    p_image.add_argument("--private", action="store_true", help="私密发布")

    # video 子命令
    p_video = subparsers.add_parser("video", help="发布视频笔记")
    p_video.add_argument("--title", required=True, help="笔记标题")
    p_video.add_argument("--desc", required=True, help="笔记描述")
    p_video.add_argument("--video", required=True, help="视频文件路径")
    p_video.add_argument("--cover", default=None, help="封面图片路径")
    p_video.add_argument("--topics", default="", help="话题标签，逗号分隔")
    p_video.add_argument("--ats", default="", help="@用户，逗号分隔")
    p_video.add_argument("--schedule", default=None, help="定时发布")
    p_video.add_argument("--private", action="store_true", help="私密发布")

    # info 子命令
    subparsers.add_parser("info", help="查看创作者信息")

    # notes 子命令
    subparsers.add_parser("notes", help="查看已发布笔记列表")

    args = parser.parse_args()

    if args.command == "image":
        cmd_image(args)
    elif args.command == "video":
        cmd_video(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "notes":
        cmd_notes(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
