---
name: xhs-publisher
description: >
  通过纯 API 方式发布小红书（Xiaohongshu/RedNote）图文笔记，无需实时浏览器，VPN 环境下也能正常发布。
  基于 ReaJason/xhs Python 库 + Docker 签名服务，Cookie 认证（一次登录长期使用）。
  支持：图文笔记发布、视频笔记发布、定时发布、话题标签、@用户、
  Cookie 管理（导入/验证/过期检测）、签名服务管理、创作者数据查看。
  触发场景：发布小红书、发小红书笔记、小红书图文、小红书视频、xhs publish、
  管理小红书cookie、导入cookie、检查小红书登录状态、小红书创作者数据、配置小红书。
  当用户提到发布内容到小红书、发小红书、写小红书笔记时，优先使用此技能而非 xiaohongshu-mcp。
---

# XHS Publisher — 小红书纯 API 发布技能

通过逆向 creator.xiaohongshu.com 的 Web API，实现无浏览器依赖的小红书笔记发布。
核心依赖：`xhs` Python 库（ReaJason/xhs）+ Docker 签名服务。

## 架构概览

```
Cookie（一次获取） + Docker签名服务（常驻后台）→ 纯 Python API 调用 → 发布笔记
```

- **签名服务**：Docker 容器 `reajason/xhs-api:latest`，端口 5005，负责生成 X-S 签名
- **Cookie**：通过浏览器手动导出或扫码获取，存储在 `data/.cookie.json`
- **发布**：纯 HTTP 请求，不需要浏览器运行

## 前置条件

1. Python 3.9+
2. Docker（用于签名服务）
3. 有效的小红书账号 Cookie

## 1. 环境搭建

首次使用时执行 setup 脚本安装所有依赖：

```bash
bash <skill-dir>/scripts/setup.sh
```

这会：
- 安装 `xhs` 和 `requests` Python 包
- 拉取并启动 Docker 签名服务容器
- 验证签名服务可用性

如果 Docker 不可用，也可以手动启动签名服务（参考 references/troubleshooting.md）。

## 2. Cookie 管理

### 导入 Cookie（推荐方式）

用户在**不开 VPN** 的浏览器中登录小红书后，从 DevTools 导出 cookie：

```bash
python3 <skill-dir>/scripts/cookie_manager.py import "完整cookie字符串"
```

关键字段：`a1`、`web_session`、`webId` 必须包含。

### 检查 Cookie 状态

```bash
python3 <skill-dir>/scripts/cookie_manager.py status
```

返回：用户昵称、Cookie 获取时间、是否有效。

### Cookie 过期处理

Cookie 有效期通常数周到数月。当 API 返回 401/461 时，需要重新获取。
脚本会自动检测并提示用户刷新。

## 3. 发布图文笔记

```bash
python3 <skill-dir>/scripts/publish.py image \
  --title "笔记标题" \
  --desc "笔记正文内容" \
  --images "/path/to/img1.jpg,/path/to/img2.jpg" \
  --topics "话题1,话题2" \
  --ats "用户名1,用户名2"
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--title` | ✅ | 笔记标题，≤20字 |
| `--desc` | ✅ | 笔记正文 |
| `--images` | ✅ | 图片路径，逗号分隔，支持 jpg/png/webp |
| `--topics` | ❌ | 话题标签，逗号分隔 |
| `--ats` | ❌ | @用户，逗号分隔 |
| `--schedule` | ❌ | 定时发布，格式 "2026-03-29 10:00:00" |
| `--private` | ❌ | 私密发布 |

### 发布视频笔记

```bash
python3 <skill-dir>/scripts/publish.py video \
  --title "视频标题" \
  --desc "视频描述" \
  --video "/path/to/video.mp4" \
  --cover "/path/to/cover.jpg" \
  --topics "话题1"
```

## 4. 查看创作者数据

```bash
python3 <skill-dir>/scripts/publish.py info
python3 <skill-dir>/scripts/publish.py notes
```

## 5. 工作流程（给 Agent 的指引）

当用户要求发布小红书笔记时，按以下流程执行：

1. **检查 Cookie**：运行 `cookie_manager.py status`，确认登录有效
2. **检查签名服务**：`curl -s http://localhost:5005/ | head -1`，确认 Docker 服务在跑
3. **准备内容**：
   - 如果用户提供了图片路径，直接使用
   - 如果用户要求生成图片，先用图片生成技能创建，保存到本地
   - 标题控制在 20 字以内
4. **发布**：调用 `publish.py image` 或 `publish.py video`
5. **确认结果**：返回 note_id 和链接

### 错误处理

- **461/471**：触发风控验证码，等待几分钟后重试，或检查 cookie 是否过期
- **签名失败**：检查 Docker 签名服务是否运行，`docker ps | grep xhs`
- **上传失败**：检查图片格式（需要 jpg/png/webp）和大小（单张 < 20MB）
- **Cookie 过期**：提示用户关闭 VPN 后重新导入 cookie

详细排错指南见 `references/troubleshooting.md`。
