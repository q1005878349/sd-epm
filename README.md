# 山东电价预测与储能套利系统

面向山东电力现货市场的工商业电价预测与储能充放电优化系统。

- **后端**：Python · FastAPI · SQLAlchemy（ORM）· SQLite
- **前端**：Vue 3 · Vite · Element Plus · ECharts
- **算法**：梯度提升树价格预测 + 线性规划（LP）充放电优化

## 功能对照

| 需求 | 实现 |
|---|---|
| 1. 获取山东实时现货价并转换为工商业电价 | 价格适配器（当前为仿真器）+ 可配置转换公式 `到户价 = 现货价÷1000×乘数 + 附加项` |
| 2. 内置预测模型，24h / 1h 预测 | HistGradientBoosting 模型，`POST /api/forecast`，horizon=24h/1h |
| 3. 可调参数：电池容量、最大充电功率、电网输电功率 | 「充放电策略」页和「参数与数据」页均可在线调节，持久化到 SQLite |
| 4. 按预测价决定充放电 | LP 优化自动在最低价时段充电、最高价时段放电，含 SOC/功率/循环次数约束 |
| 5. 支持按小时 → 15 分钟计价切换 | 数据表带 `interval_min` 字段，60/15 分钟双颗粒度数据与模型并存，一键切换 |
| 6. 天气 / 法定节假日 / 时分信息参与预测 | Open-Meteo 天气 API、timor.tech 节假日 API、时分周期编码，均为模型特征 |
| 7. 充放电谷峰符合性标识 | 每时段标注深谷/低谷/平段/高峰/尖峰，并给出「✓符合 / —平段 / ✗偏离」标识 |
| 8. Python 服务 + Vue 前端 + SQLite + ORM | 即本工程 |
| 9. 对比固定谷时策略的日/周/月/年节省 | 「回测与节省」页：逐日滚动回测，输出日/周/月/年（年化）节省 |

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

**单进程运行（推荐演示）**：先 `cd frontend && npm run build`，再启动后端，
直接访问 http://127.0.0.1:8000 （后端自动托管 `frontend/dist`）。

## 接入真实数据源

价格数据通过适配器接口接入，替换仿真器只需两步：

1. 继承 `backend/app/adapters/base.py` 中的 `PriceDataAdapter`，实现
   `fetch_spot_prices(start, end, interval_min)`，返回
   `[{"ts": datetime, "spot_price": 元/MWh}, ...]`；
2. 在 `backend/app/services/sync.py` 的 `ADAPTERS` 注册表登记，并把
   `DEFAULT_ADAPTER` 改为你的适配器名。

预测、调度、回测、前端均无需改动。

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/sync | 全量同步（价格/天气/节假日） |
| GET | /api/prices?day=&interval_min= | 某日现货价 + 工商业电价（含分时类型） |
| POST | /api/forecast | 运行预测 `{horizon: 24h/1h, interval_min: 60/15}` |
| POST | /api/dispatch | 生成充放电计划（可先跑预测再 LP 优化） |
| GET | /api/dispatch/latest | 最近一次调度计划 |
| POST | /api/backtest | 回测 `{start_date, end_date, interval_min}` |
| GET/PUT | /api/params | 读取/修改系统参数 |
| GET | /api/tou | 分时电价时段配置 |
| GET | /api/overview | 仪表盘聚合 |

## 说明与免责

- 现货价格为**仿真数据**：具有山东市场典型特征（午间光伏深谷、晚尖峰、负电价可能性），
  用于产品演示与算法验证，**不是真实交易数据**。
- 分时电价时段为近似配置（`backend/app/config.py` 中 `TOU_PERIODS`），
  请以山东省发改委最新文件为准。
- 年节省为「区间日均节省 × 365」的年化估算，实际收益取决于真实价格与预测精度。
- 天气/节假日依赖公开 API，网络不可用时自动回退到内置仿真/列表，系统离线可用。

## 目录结构

```
sd-epm/
├── backend/
│   ├── run.py                  # 启动入口
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI 应用（含前端 dist 托管）
│       ├── database.py         # SQLite + SQLAlchemy
│       ├── models.py           # ORM 表：价格/天气/节假日/参数/预测/调度/回测
│       ├── config.py           # 默认参数 + 分时电价时段
│       ├── adapters/           # 价格适配器接口、仿真器、天气、节假日
│       ├── services/           # 同步、转换、预测、调度(LP)、回测
│       └── routers/api.py      # REST API
└── frontend/
    └── src/views/              # 总览 / 电价预测 / 充放电策略 / 回测与节省 / 参数与数据
```
