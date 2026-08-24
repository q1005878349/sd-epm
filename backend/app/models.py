"""ORM 数据模型。

设计要点：
- price_records 同时承载 60 分钟与 15 分钟两种颗粒度，interval_min 区分，
  满足"当前按小时计价、后续可平滑切换到 15 分钟计价"的要求。
- 预测运行、调度计划、回测结果以 JSON 字段整体落库，便于前端回放历史结果。
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Boolean, JSON,
    UniqueConstraint, Index,
)
from .database import Base


class PriceRecord(Base):
    """电力现货价格 + 转换后的工商业到户电价。"""
    __tablename__ = "price_records"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, nullable=False, index=True)          # 时段起始时间
    interval_min = Column(Integer, nullable=False, default=60)  # 60 或 15
    spot_price = Column(Float, nullable=False)                 # 现货价 元/MWh
    retail_price = Column(Float, nullable=False)               # 工商业电价 元/kWh
    source = Column(String(32), default="simulator")           # simulator / 自定义适配器名
    __table_args__ = (
        UniqueConstraint("ts", "interval_min", name="uq_price_ts_interval"),
        Index("ix_price_interval_ts", "interval_min", "ts"),
    )


class WeatherRecord(Base):
    """天气数据（历史实况或预报），作为预测特征。"""
    __tablename__ = "weather_records"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, nullable=False, unique=True, index=True)
    temp_c = Column(Float)
    cloud_pct = Column(Float)      # 云量 %
    wind_ms = Column(Float)
    ghi_wm2 = Column(Float)        # 短波辐射 W/m²，光伏出力的代理变量
    is_forecast = Column(Boolean, default=False)


class Holiday(Base):
    """法定节假日。"""
    __tablename__ = "holidays"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    name = Column(String(64))
    is_offday = Column(Boolean, default=True)  # True=休息日(假期), False=调休上班


class SystemParams(Base):
    """系统/模型可调参数，单行存储。"""
    __tablename__ = "system_params"
    id = Column(Integer, primary_key=True)
    payload = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ForecastRun(Base):
    """一次预测运行的结果。"""
    __tablename__ = "forecast_runs"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    horizon = Column(String(8))        # "24h" 或 "1h"
    interval_min = Column(Integer)     # 60 或 15
    mae = Column(Float)                # 训练集外样本的 MAE（元/MWh），供参考
    points = Column(JSON)              # [{ts, price_spot, price_retail}]


class DispatchPlan(Base):
    """一次充放电调度计划。"""
    __tablename__ = "dispatch_plans"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    forecast_id = Column(Integer)
    interval_min = Column(Integer)
    params_snapshot = Column(JSON)
    schedule = Column(JSON)   # [{ts, action, power_kw, soc_kwh, price, tou, tou_match}]
    summary = Column(JSON)    # {revenue, charge_kwh, discharge_kwh, cycles, ...}


class BacktestResult(Base):
    """回测结果：预测策略 vs 固定谷时策略。"""
    __tablename__ = "backtest_results"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    start_date = Column(Date)
    end_date = Column(Date)
    interval_min = Column(Integer)
    params_snapshot = Column(JSON)
    result = Column(JSON)     # 明细 + 日/周/月/年节省汇总
