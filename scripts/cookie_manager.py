#!/usr/bin/env python3
"""
小红书 Cookie 管理器
- import: 导入 cookie 字符串并验证
- status: 检查当前 cookie 状态
- clear: 清除已保存的 cookie
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
COOKIE_FILE = os.path.join(DATA_DIR, ".cookie.json")

SIGN_SERVER = os.environ.get("XHS_SIGN_SERVER", "")

# 必需的 cookie 字段
REQUIRED_FIELDS = ["a1", "web_session"]

CN_TZ = timezone(timedelta(hours=8))


def parse_cookie_string(cookie_str: str) -> dict:
    """解析 cookie 字符串为 dict"""
    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            key, value = item.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def validate_cookie(cookie_str: str) -> dict:
    """验证 cookie 是否包含必需字段"""
    cookies = parse_cookie_string(cookie_str)
    missing = [f for f in REQUIRED_FIELDS if f not in cookies]
    if missing:
        return None
    return cookies


def sign_request(uri: str, data=None, a1: str = "", web_session: str = "") -> dict:
    """生成签名：优先内置，回退外部服务"""
    # 优先使用 xhs 内置签名
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

    print("❌ 无可用签名方式。安装 xhs: pip3 install xhs")
    sys.exit(1)


def verify_cookie(cookie_str: str) -> dict:
    """通过 API 验证 cookie 是否有效，返回用户信息"""
    cookies = parse_cookie_string(cookie_str)
    a1 = cookies.get("a1", "")
    web_session = cookies.get("web_session", "")

    # 使用 v2 接口验证（内置签名兼容性更好）
    uri = "/api/sns/web/v2/user/me"
    signs = sign_request(uri, a1=a1, web_session=web_session)

    headers = {
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "cookie": cookie_str,
        "origin": "https://www.xiaohongshu.com",
        "referer": "https://www.xiaohongshu.com/",
        "x-s": signs["x-s"],
        "x-t": signs["x-t"],
    }
    if signs.get("x-s-common"):
        headers["x-s-common"] = signs["x-s-common"]

    try:
        resp = requests.get(
            f"https://edith.xiaohongshu.com{uri}",
            headers=headers,
            timeout=15
        )
        data = resp.json()
        if data.get("data"):
            return data["data"]
        elif data.get("success"):
            return data.get("data", {})
        else:
            print(f"⚠️  API 返回错误: {data}")
            return None
    except Exception as e:
        print(f"❌ 验证请求失败: {e}")
        return None


def save_cookie(cookie_str: str, cookies: dict, user_info: dict = None):
    """保存 cookie 到文件"""
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(CN_TZ).isoformat()

    data = {
        "cookie_string": cookie_str,
        "a1": cookies.get("a1", ""),
        "web_session": cookies.get("web_session", ""),
        "webId": cookies.get("webId", ""),
        "obtained_at": now,
        "last_verified": now,
    }

    if user_info:
        data["user_id"] = user_info.get("user_id", "")
        data["nickname"] = user_info.get("nickname", "")
        data["red_id"] = user_info.get("red_id", "")

    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 设置文件权限为仅用户可读写
    os.chmod(COOKIE_FILE, 0o600)


def load_cookie() -> dict:
    """加载已保存的 cookie"""
    if not os.path.exists(COOKIE_FILE):
        return None
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_import(cookie_str: str):
    """导入并验证 cookie"""
    print("🔍 解析 Cookie...")
    cookies = validate_cookie(cookie_str)
    if not cookies:
        print(f"❌ Cookie 缺少必需字段: {', '.join(REQUIRED_FIELDS)}")
        print("   请确保从浏览器完整复制了 cookie")
        sys.exit(1)
    print(f"✅ 解析成功，包含 {len(cookies)} 个字段")
    print(f"   a1: {cookies['a1'][:8]}...")
    print(f"   web_session: {cookies['web_session'][:8]}...")

    print("\n🔐 验证 Cookie 有效性...")
    user_info = verify_cookie(cookie_str)
    if user_info:
        nickname = user_info.get("nickname", "未知")
        print(f"✅ Cookie 有效！用户: {nickname}")
        save_cookie(cookie_str, cookies, user_info)
        print(f"💾 Cookie 已保存到: {COOKIE_FILE}")
    else:
        print("⚠️  无法验证 Cookie（可能是签名服务问题或 Cookie 已过期）")
        print("   是否仍要保存？(y/n)", end=" ")
        if input().strip().lower() == "y":
            save_cookie(cookie_str, cookies)
            print(f"💾 Cookie 已保存（未验证）: {COOKIE_FILE}")
        else:
            print("已取消")


def cmd_status():
    """检查当前 cookie 状态"""
    data = load_cookie()
    if not data:
        print("❌ 未找到已保存的 Cookie")
        print("   请先导入: python3 cookie_manager.py import \"cookie字符串\"")
        sys.exit(1)

    print("📋 Cookie 状态")
    print("=" * 40)
    print(f"  用户: {data.get('nickname', '未知')}")
    print(f"  用户ID: {data.get('user_id', '未知')}")
    print(f"  小红书号: {data.get('red_id', '未知')}")
    print(f"  获取时间: {data.get('obtained_at', '未知')}")
    print(f"  上次验证: {data.get('last_verified', '未知')}")

    # 检查 cookie 年龄
    obtained = data.get("obtained_at")
    if obtained:
        try:
            obtained_dt = datetime.fromisoformat(obtained)
            age_days = (datetime.now(CN_TZ) - obtained_dt).days
            if age_days > 14:
                print(f"\n  ⚠️  Cookie 已使用 {age_days} 天，建议刷新")
            else:
                print(f"\n  ✅ Cookie 使用 {age_days} 天，状态良好")
        except Exception:
            pass

    # 在线验证
    print("\n🔐 在线验证...")
    user_info = verify_cookie(data["cookie_string"])
    if user_info:
        print(f"✅ Cookie 有效！当前用户: {user_info.get('nickname', '未知')}")
        # 更新验证时间
        data["last_verified"] = datetime.now(CN_TZ).isoformat()
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        print("❌ Cookie 已失效，请重新导入")


def cmd_clear():
    """清除已保存的 cookie"""
    if os.path.exists(COOKIE_FILE):
        os.remove(COOKIE_FILE)
        print("✅ Cookie 已清除")
    else:
        print("ℹ️  没有已保存的 Cookie")


def cmd_get():
    """输出 cookie 字符串（供其他脚本使用）"""
    data = load_cookie()
    if data:
        print(data["cookie_string"])
    else:
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 cookie_manager.py import \"cookie字符串\"  # 导入 cookie")
        print("  python3 cookie_manager.py status                 # 检查状态")
        print("  python3 cookie_manager.py clear                  # 清除 cookie")
        print("  python3 cookie_manager.py get                    # 输出 cookie（内部用）")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "import":
        if len(sys.argv) < 3:
            print("❌ 请提供 cookie 字符串")
            print('用法: python3 cookie_manager.py import "a1=xxx; web_session=xxx; ..."')
            sys.exit(1)
        cmd_import(sys.argv[2])
    elif cmd == "status":
        cmd_status()
    elif cmd == "clear":
        cmd_clear()
    elif cmd == "get":
        cmd_get()
    else:
        print(f"❌ 未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
