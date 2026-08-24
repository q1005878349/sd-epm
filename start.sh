#!/usr/bin/env bash
# 一键启动：安装依赖 -> 构建前端（如有 node）-> 启动后端（自动托管前端）
set -e
cd "$(dirname "$0")"

cd backend
pip install -r requirements.txt

if command -v npm >/dev/null 2>&1 && [ ! -d ../frontend/dist ]; then
  echo "构建前端..."
  cd ../frontend && npm install && npm run build && cd ../backend
fi

python run.py
