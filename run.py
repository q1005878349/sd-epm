"""启动后端服务（单进程托管前端构建产物）。

用法:
    python run.py              # 监听 127.0.0.1:8000
    PORT=8001 python run.py    # 指定端口
"""
import os
import sys

# 将 backend 加入模块搜索路径，使 "app.main:app" 可导入
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

import uvicorn


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
