## 快速启动

```bash
# 1. 后端（首次启动自动初始化 120 天仿真数据 + 天气 + 节假日）
cd backend
pip install -r requirements.txt
python run.py          # http://127.0.0.1:8000  接口文档 /docs

# 2. 前端（开发模式，代理到 8000）
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```