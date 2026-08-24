"""价格预测服务。

模型：HistGradientBoostingRegressor（直方图梯度提升树）
特征：
- 时分信息：时段序号、sin/cos 周期编码、星期、月份
- 日历信息：是否周末、是否法定节假日
- 天气信息：气温、云量、短波辐射（光伏代理）、风速
- 滞后信息：前 1/2/3/7 天同一时段现货价、近 7 天同时段滚动均值

支持 60 分钟与 15 分钟两种颗粒度（各自独立训练）。
horizon="24h" 预测未来 24 小时；horizon="1h" 预测未来 1 小时
（15 分钟颗粒度下为 4 个点）。
"""
from datetime import datetime, timedelta
from typing import List, Tuple
import math
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy.orm import Session

from ..models import PriceRecord, WeatherRecord, Holiday
from .params import get_params
from .pricing import spot_to_retail

FEATURE_COLS = [
    "slot", "tod_sin", "tod_cos", "dow", "is_weekend", "is_holiday", "month",
    "temp_c", "cloud_pct", "ghi_wm2", "wind_ms",
    "lag1", "lag2", "lag3", "lag7", "roll7",
]
_WEATHER_DEFAULTS = {"temp_c": 15.0, "cloud_pct": 50.0, "ghi_wm2": 200.0, "wind_ms": 3.0}


def _load_prices(db: Session, interval_min: int) -> pd.DataFrame:
    df = pd.read_sql(
        db.query(PriceRecord).filter(PriceRecord.interval_min == interval_min)
        .order_by(PriceRecord.ts).statement, db.bind)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"])
    return df.set_index("ts").sort_index()


def _load_weather(db: Session, interval_min: int) -> pd.DataFrame:
    df = pd.read_sql(db.query(WeatherRecord).order_by(WeatherRecord.ts).statement, db.bind)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"])
    w = df.set_index("ts").sort_index()[list(_WEATHER_DEFAULTS)]
    return w.resample(f"{interval_min}min").ffill()


def _holiday_set(db: Session) -> set:
    return {h.date for h in db.query(Holiday).filter(Holiday.is_offday == True).all()}  # noqa: E712


def _time_features(df: pd.DataFrame, interval_min: int, holidays: set) -> pd.DataFrame:
    idx = df.index
    df["slot"] = (idx.hour * 60 + idx.minute) // interval_min
    frac = (idx.hour * 60 + idx.minute) / 1440.0
    df["tod_sin"] = np.sin(2 * math.pi * frac)
    df["tod_cos"] = np.cos(2 * math.pi * frac)
    df["dow"] = idx.dayofweek
    df["is_weekend"] = (idx.dayofweek >= 5).astype(int)
    df["month"] = idx.month
    if "is_holiday" not in df.columns:
        df["is_holiday"] = [1 if t.date() in holidays else 0 for t in idx]
    return df


def _fill_weather(df: pd.DataFrame) -> pd.DataFrame:
    for col, default in _WEATHER_DEFAULTS.items():
        if col not in df.columns:
            df[col] = np.nan
        slot_mean = df.groupby("slot")[col].transform("mean")
        df[col] = df[col].fillna(slot_mean).fillna(default)
    return df


def _add_lags(df: pd.DataFrame, interval_min: int, lag_days: List[int]) -> pd.DataFrame:
    slots_per_day = 1440 // interval_min
    for d in lag_days:
        df[f"lag{d}"] = df["spot_price"].shift(slots_per_day * d)
    df["roll7"] = df["spot_price"].shift(slots_per_day).rolling(
        slots_per_day * 7, min_periods=slots_per_day).mean()
    return df


def _fit_predict(hist: pd.DataFrame, future_ts: list, interval_min: int,
                 params: dict, holidays: set, weather: pd.DataFrame
                 ) -> Tuple[pd.Series, float]:
    """核心流程：在 hist（含 spot_price）上训练，预测 future_ts 的现货价。"""
    lag_days = params.get("lag_days", [1, 2, 3, 7])
    hist = hist.join(weather, how="left")
    hist["is_holiday"] = [1 if t.date() in holidays else 0 for t in hist.index]

    future = pd.DataFrame(index=pd.DatetimeIndex(future_ts), columns=["spot_price"])
    future["spot_price"] = np.nan
    future = future.join(weather, how="left")
    future["is_holiday"] = [1 if t.date() in holidays else 0 for t in future.index]

    combined = pd.concat([hist[["spot_price", "temp_c", "cloud_pct", "ghi_wm2",
                                "wind_ms", "is_holiday"]], future])
    combined = _time_features(combined, interval_min, holidays)
    combined = _fill_weather(combined)
    combined = _add_lags(combined, interval_min, lag_days)

    last_ts = hist.index.max()
    train_df = combined.loc[:last_ts].dropna(subset=["lag7", "roll7"])
    train_days = int(params.get("train_days", 60))
    windowed = train_df[train_df.index >= last_ts - timedelta(days=train_days)]
    if len(windowed) >= 200:
        train_df = windowed
    if len(train_df) < 50:
        raise ValueError("可用训练数据不足，请先同步更长的历史数据")

    val_cut = train_df.index.max() - timedelta(days=3)
    tr, va = train_df[train_df.index < val_cut], train_df[train_df.index >= val_cut]
    if len(tr) < 50 or len(va) < 20:
        tr, va = train_df, train_df.iloc[0:0]

    model = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.06, l2_regularization=1.0, random_state=42)
    model.fit(tr[FEATURE_COLS], tr["spot_price"])
    mae = float(np.mean(np.abs(model.predict(va[FEATURE_COLS]) - va["spot_price"]))) \
        if len(va) else None
    model.fit(train_df[FEATURE_COLS], train_df["spot_price"])  # 全量重训

    fut = combined.loc[future_ts].copy()
    global_mean = train_df["spot_price"].mean()
    fut["roll7"] = fut["roll7"].fillna(global_mean)
    for d in lag_days:
        fut[f"lag{d}"] = fut[f"lag{d}"].fillna(fut["roll7"]).fillna(global_mean)

    return pd.Series(model.predict(fut[FEATURE_COLS]), index=future_ts), mae


def run_forecast(db: Session, horizon: str = "24h", interval_min: int = 60
                 ) -> Tuple[List[dict], float]:
    """从当前最新数据起预测。返回 (预测点列表, 验证集 MAE 元/MWh)。"""
    params = get_params(db)
    hist = _load_prices(db, interval_min)
    if hist.empty:
        raise ValueError("没有价格数据，请先执行数据同步")
    weather = _load_weather(db, interval_min)
    holidays = _holiday_set(db)

    step = timedelta(minutes=interval_min)
    last_ts = hist.index.max().to_pydatetime()
    n = {"24h": 1440 // interval_min, "1h": 60 // interval_min}[horizon]
    future_ts = [last_ts + (i + 1) * step for i in range(n)]

    preds, mae = _fit_predict(hist, future_ts, interval_min, params, holidays, weather)
    points = [{
        "ts": t.isoformat(sep=" "),
        "price_spot": round(float(preds.loc[t]), 2),
        "price_retail": spot_to_retail(float(preds.loc[t]), params["retail_multiplier"],
                                       params["retail_adder_yuan_kwh"]),
    } for t in future_ts]
    return points, mae


def predict_for_date(db: Session, target_date, interval_min: int = 60) -> List[dict]:
    """回测专用：只用 target_date 之前的数据训练，预测 target_date 全天的价格。"""
    params = get_params(db)
    hist_all = _load_prices(db, interval_min)
    if hist_all.empty:
        raise ValueError("没有价格数据")
    day_start = datetime.combine(target_date, datetime.min.time())
    hist = hist_all[hist_all.index < day_start]
    if len(hist) < 50:
        raise ValueError(f"{target_date} 之前的历史数据不足")

    weather = _load_weather(db, interval_min)
    holidays = _holiday_set(db)
    step = timedelta(minutes=interval_min)
    n = 1440 // interval_min
    future_ts = [day_start + i * step for i in range(n)]

    preds, _ = _fit_predict(hist, future_ts, interval_min, params, holidays, weather)
    return [{
        "ts": t.isoformat(sep=" "),
        "price_spot": round(float(preds.loc[t]), 2),
        "price_retail": spot_to_retail(float(preds.loc[t]), params["retail_multiplier"],
                                       params["retail_adder_yuan_kwh"]),
    } for t in future_ts]
