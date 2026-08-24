"""山东电力现货价格仿真器。

在没有真实数据 API 的情况下，生成贴近山东现货市场特征的价格序列：
- 凌晨负荷低谷，价格低位平稳；
- 午间（10:00-15:00）光伏大发形成"鸭子曲线"深谷，晴天可接近 0 甚至负电价；
- 晚高峰（17:00-21:00）光伏退出 + 负荷高峰，价格冲顶；
- 周末/节假日整体下移；极端气温抬高晚高峰；
- 天气（云量/辐射）直接驱动午间谷的深度。

单位：元/MWh（日前/实时现货口径）。
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import math
import numpy as np

from .base import PriceDataAdapter, SpotPricePoint


def _daily_profile(hour_float: float) -> float:
    """日内基础形状（元/MWh），工作日晴天基准。"""
    pts = [
        (0, 300), (4, 280), (6, 300), (8, 420), (9, 400),
        (10, 300), (11, 120), (12, 40), (13, 30), (14, 90),
        (15, 220), (16, 350), (17, 520), (18, 640), (19, 660),
        (20, 600), (21, 480), (22, 400), (23, 340), (24, 300),
    ]
    for (h0, v0), (h1, v1) in zip(pts, pts[1:]):
        if h0 <= hour_float <= h1:
            t = (hour_float - h0) / (h1 - h0)
            return v0 + (v1 - v0) * t
    return 300.0


class SimulatorAdapter(PriceDataAdapter):
    name = "simulator"

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def fetch_spot_prices(self, start: datetime, end: datetime,
                          interval_min: int = 60,
                          weather: Optional[Dict[datetime, dict]] = None,
                          holiday_dates: Optional[set] = None) -> List[SpotPricePoint]:
        step = timedelta(minutes=interval_min)
        out: List[SpotPricePoint] = []
        ts = start
        while ts < end:
            h = ts.hour + ts.minute / 60.0
            day_index = (ts.date() - start.date()).days
            price = _daily_profile(h)

            # 季节项：夏季/冬季负荷高
            price += 60 * math.cos((ts.month - 7.5) / 12 * 2 * math.pi)

            # 周末 / 节假日下移
            if ts.weekday() >= 5:
                price *= 0.85
            if holiday_dates and ts.date() in holiday_dates:
                price *= 0.75

            # 天气驱动：云量低 -> 午间光伏大发 -> 深谷更深（可负价）
            w = weather.get(ts.replace(minute=0)) if weather else None
            if w and 9 <= h <= 16:
                cloud = w.get("cloud_pct", 50) or 50
                solar_factor = max(0.0, 1 - cloud / 100.0)
                price -= 220 * solar_factor * math.sin((h - 9) / 7 * math.pi)
            if w:
                temp = w.get("temp_c", 20) or 20
                if 17 <= h <= 21:  # 极端气温抬高晚高峰
                    if temp >= 35:
                        price += 80 + (temp - 35) * 30
                    elif temp <= -5:
                        price += 80 + (-5 - temp) * 20

            # 趋势 + 噪声
            trend = 30 * math.sin(day_index / 17.0)
            noise = float(self.rng.normal(0, 35 + (60 - interval_min) * 1.5))
            price = price + trend + noise

            # 山东现货限价（近似）：-80 ~ 1500 元/MWh
            price = min(1500.0, max(-80.0, price))
            out.append({"ts": ts, "spot_price": round(price, 2)})
            ts += step
        return out
