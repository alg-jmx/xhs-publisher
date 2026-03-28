# XHS Publisher 常见问题排错指南

## 1. 签名服务相关

### 签名服务无法启动
```bash
# 检查 Docker 是否运行
docker info

# 检查端口是否被占用
lsof -i :5005

# 查看容器日志
docker logs xhs-sign-server
```

### 没有 Docker 怎么办？

可以用本地 Python 启动签名服务（需要 playwright）：

```bash
pip install flask gevent playwright
playwright install chromium

# 克隆 xhs 仓库并运行 sign server
git clone https://github.com/ReaJason/xhs.git /tmp/xhs-repo
cd /tmp/xhs-repo
python example/basic_sign_server.py
```

然后设置环境变量让脚本使用自定义地址：
```bash
export XHS_SIGN_SERVER="http://localhost:5005"
```

### 签名服务的 a1 和 Cookie 不一致

签名服务启动时会生成一个 a1 值。为了避免签名错误，建议：
1. 查看签名服务日志中的 a1 值：`docker logs xhs-sign-server | grep a1`
2. 确保 cookie 中的 a1 与签名服务一致
3. 如果不一致，可以修改 cookie 中的 a1，或重启签名服务

## 2. Cookie 相关

### 如何从浏览器获取 Cookie

1. 在浏览器中打开 https://www.xiaohongshu.com（**关闭 VPN**）
2. 登录账号
3. 按 F12 打开 DevTools
4. 切换到 Application（应用）标签
5. 左侧展开 Cookies → https://www.xiaohongshu.com
6. 找到 `a1`、`web_session`、`webId` 字段
7. 也可以在 Console 中执行 `document.cookie` 获取完整 cookie 字符串

### Cookie 失效 (HTTP 401 / 461)

- Cookie 有效期通常 2-4 周
- 如果在其他浏览器/设备登录同一账号，当前 cookie 会被踢掉
- 解决：关 VPN → 重新登录 → 重新导入 cookie

### VPN 环境下 Cookie 获取失败

小红书检测到海外 IP 时会拦截登录和部分 API。解决方案：
- **方案 A**：暂时关闭 VPN，获取 cookie 后再开启 VPN
- **方案 B**：使用分流规则，仅 xiaohongshu.com 走直连
- **方案 C**：在手机上登录后，用 Charles/mitmproxy 抓包获取 cookie

## 3. 发布相关

### 461 / 471 风控验证码

触发频率限制。建议：
- 两次发布间隔 > 5 分钟
- 避免短时间内大量上传
- 如果持续触发，等待 30 分钟后重试

### 图片上传失败

- 支持格式：jpg, png, webp, gif
- 单张大小限制：< 20MB
- 建议分辨率：宽度 ≥ 1080px
- 最多 18 张图片

### 标题限制

- 最大长度：20 个字符
- 不能包含敏感词
- 不能全是特殊符号

### 定时发布

- 格式：`2026-03-29 10:00:00`
- 最早可设置 2 小时后
- 最晚可设置 30 天后
- 时区跟随系统设置

## 4. 与 xiaohongshu-mcp 的区别

| 特性 | xhs-publisher | xiaohongshu-mcp |
|------|---------------|-----------------|
| 核心用途 | **发布**笔记 | **读取**数据 |
| 浏览器依赖 | ❌ 不需要 | ✅ 需要 Chrome |
| VPN 兼容 | ✅ 发布可用 | ❌ 登录失败 |
| 认证方式 | Cookie 导入 | QR 扫码 |
| 搜索功能 | ❌ | ✅ |
| 评论功能 | ❌ | ✅ |

两个 skill 互补使用：用 xiaohongshu-mcp 搜索和分析，用 xhs-publisher 发布。
