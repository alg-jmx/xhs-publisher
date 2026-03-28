#!/usr/bin/env python3
"""
本地 X-S 签名服务（不依赖 Docker）
基于 Flask + Playwright，提供 /sign HTTP 接口

启动: python3 sign_server.py [--port 5005] [--headless]
"""
import argparse
import json
import os
import sys
from time import sleep

from flask import Flask, jsonify, request

app = Flask(__name__)

# 全局变量
_context_page = None
_browser_context = None
_browser = None
_playwright_instance = None
_a1 = ""

STEALTH_JS_URL = "https://cdn.jsdelivr.net/gh/nicegram/nicejs@main/nicejs.min.js"


def init_browser(headless=True):
    """初始化浏览器和签名环境"""
    global _context_page, _browser_context, _browser, _playwright_instance, _a1

    from playwright.sync_api import sync_playwright

    _playwright_instance = sync_playwright().start()
    _browser = _playwright_instance.chromium.launch(headless=headless)
    _browser_context = _browser.new_context()

    # 下载并注入 stealth.js
    stealth_path = os.path.join(os.path.dirname(__file__), "stealth.min.js")
    if not os.path.exists(stealth_path):
        print("📥 下载 stealth.min.js...")
        import requests as req
        # 尝试多个来源
        urls = [
            "https://cdn.jsdelivr.net/gh/nicegram/nicejs@main/nicejs.min.js",
            "https://cdn.jsdelivr.net/gh/nicegram/nicejs/nicejs.min.js",
            "https://raw.githubusercontent.com/nicegram/nicejs/main/nicejs.min.js",
        ]
        downloaded = False
        for url in urls:
            try:
                resp = req.get(url, timeout=30)
                if resp.status_code == 200 and len(resp.text) > 100:
                    with open(stealth_path, "w") as f:
                        f.write(resp.text)
                    downloaded = True
                    print(f"✅ stealth.min.js 下载成功 ({len(resp.text)} bytes)")
                    break
            except Exception:
                continue

        if not downloaded:
            print("⚠️  stealth.min.js 下载失败，尝试使用 requireCool 版本...")
            try:
                resp = req.get(
                    "https://cdn.jsdelivr.net/gh/requireCool/stealth.min.js/stealth.min.js",
                    timeout=30
                )
                if resp.status_code == 200:
                    with open(stealth_path, "w") as f:
                        f.write(resp.text)
                    print("✅ stealth.min.js (requireCool) 下载成功")
                else:
                    print("❌ 无法下载 stealth.min.js，签名可能不稳定")
            except Exception as e:
                print(f"❌ 下载失败: {e}")

    if os.path.exists(stealth_path):
        _browser_context.add_init_script(path=stealth_path)

    _context_page = _browser_context.new_page()
    _context_page.goto("https://www.xiaohongshu.com")
    sleep(1)

    # 获取 a1
    cookies = _browser_context.cookies()
    for cookie in cookies:
        if cookie["name"] == "a1":
            _a1 = cookie["value"]
            break

    print(f"✅ 浏览器初始化完成，a1={_a1}")
    return _a1


@app.route("/")
def index():
    return jsonify({
        "status": "ok",
        "service": "xhs-sign-server",
        "a1": _a1,
    })


@app.route("/sign", methods=["POST"])
def do_sign():
    """签名接口"""
    data = request.json
    uri = data.get("uri", "")
    payload = data.get("data")
    a1 = data.get("a1", _a1)
    web_session = data.get("web_session", "")

    # 如果传入的 a1 和当前不一致，更新 cookie
    if a1 and a1 != _a1:
        _browser_context.add_cookies([
            {"name": "a1", "value": a1, "domain": ".xiaohongshu.com", "path": "/"}
        ])
        _context_page.reload()
        sleep(0.5)

    try:
        encrypt_params = _context_page.evaluate(
            "([url, data]) => window._webmsxyw(url, data)",
            [uri, payload]
        )
        return jsonify({
            "x-s": encrypt_params["X-s"],
            "x-t": str(encrypt_params["X-t"]),
        })
    except Exception as e:
        # 重试一次
        try:
            _context_page.reload()
            sleep(1)
            encrypt_params = _context_page.evaluate(
                "([url, data]) => window._webmsxyw(url, data)",
                [uri, payload]
            )
            return jsonify({
                "x-s": encrypt_params["X-s"],
                "x-t": str(encrypt_params["X-t"]),
            })
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500


def main():
    parser = argparse.ArgumentParser(description="XHS 本地签名服务")
    parser.add_argument("--port", type=int, default=5005, help="端口号 (默认 5005)")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="无头模式 (默认 True)")
    parser.add_argument("--no-headless", action="store_true",
                        help="显示浏览器窗口（调试用）")
    args = parser.parse_args()

    headless = not args.no_headless

    print("🔑 XHS 本地签名服务")
    print("=" * 40)
    print(f"  端口: {args.port}")
    print(f"  模式: {'无头' if headless else '有窗口'}")
    print()

    print("🌐 初始化浏览器...")
    a1 = init_browser(headless=headless)
    print(f"\n🚀 签名服务已启动: http://localhost:{args.port}")
    print(f"   a1 = {a1}")
    print(f"   签名接口: POST http://localhost:{args.port}/sign")
    print()

    try:
        from gevent.pywsgi import WSGIServer
        http_server = WSGIServer(("0.0.0.0", args.port), app, log=None)
        http_server.serve_forever()
    except ImportError:
        app.run(host="0.0.0.0", port=args.port, threaded=False)


if __name__ == "__main__":
    main()
