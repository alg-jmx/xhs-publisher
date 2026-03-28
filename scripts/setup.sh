#!/usr/bin/env bash
# xhs-publisher 环境搭建脚本
set -e

echo "🦞 XHS Publisher 环境搭建"
echo "========================="

# 1. 安装 Python 依赖
echo ""
echo "📦 安装 Python 依赖..."
pip3 install xhs requests lxml 2>/dev/null || pip install xhs requests lxml
echo "✅ Python 依赖安装完成"

# 2. 检查 Docker
echo ""
echo "🐳 检查 Docker..."
if ! command -v docker &> /dev/null; then
    echo "⚠️  Docker 未安装。签名服务需要 Docker。"
    echo "   请安装 Docker Desktop: https://www.docker.com/products/docker-desktop/"
    echo "   或者手动运行签名服务（见 references/troubleshooting.md）"
    exit 1
fi

# 3. 启动签名服务
echo ""
echo "🔑 启动签名服务..."
CONTAINER_NAME="xhs-sign-server"

# 检查是否已在运行
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "✅ 签名服务已在运行"
else
    # 检查是否有停止的容器
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "🔄 重启已有的签名服务容器..."
        docker start "$CONTAINER_NAME"
    else
        echo "📥 拉取并启动签名服务..."
        docker run -d --name "$CONTAINER_NAME" -p 5005:5005 --restart unless-stopped reajason/xhs-api:latest
    fi
    
    # 等待服务就绪
    echo "⏳ 等待服务启动..."
    for i in $(seq 1 30); do
        if curl -s http://localhost:5005/ > /dev/null 2>&1; then
            echo "✅ 签名服务已就绪 (localhost:5005)"
            break
        fi
        if [ "$i" = "30" ]; then
            echo "⚠️  签名服务启动超时，请检查 Docker 日志: docker logs $CONTAINER_NAME"
            exit 1
        fi
        sleep 1
    done
fi

# 4. 获取签名服务的 a1 值
echo ""
echo "📋 签名服务信息:"
SIGN_A1=$(docker logs "$CONTAINER_NAME" 2>&1 | grep -o 'a1=[^ ]*' | tail -1 || echo "")
if [ -n "$SIGN_A1" ]; then
    echo "   签名服务 a1: $SIGN_A1"
    echo "   ⚠️  建议将你的 cookie 中的 a1 与此值保持一致"
fi

echo ""
echo "========================="
echo "✅ 环境搭建完成！"
echo ""
echo "下一步："
echo "  1. 在浏览器中登录 xiaohongshu.com（关闭 VPN）"
echo "  2. 从 DevTools > Application > Cookies 复制完整 cookie"
echo "  3. 运行: python3 $(dirname $0)/cookie_manager.py import \"你的cookie字符串\""
