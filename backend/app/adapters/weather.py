"""天气数据适配器：Open-Meteo 公开 API（免费、无需密钥）。

- 历史实况：archive-api.open-meteo.com
- 未来预报：api.open-meteo.com
默认坐标济南（山东负荷中心），可在 config.py 修改。
网络不可用时回退到内置的气候态仿真，保证系统离线可用。
"""
from datetime import datetime, timedelta
from typing import Dict, List
import math
import httpx

from ..config import WEATHER_LAT, WEATHER_LON


def _simulated_weather(start: datetime, end: datetime) -> List[dict]:
    """离线回退：按季节/日照规律生成的气候态天气。"""
    out = []
    ts = start
    while ts < end:
        h = ts.hour
        day_of_year = ts.timetuple().tm_yday
        temp_mean = 15 + 14 * math.cos((day_of_year - 200) / 365 * 2 * math.pi)
        temp = temp_mean + 6 * math.sin((h - 9) / 24 * 2 * math.pi)
        daylight = max(0.0, math.sin((h - 6) / 12 * math.pi)) if 6 <= h <= 18 else 0.0
        ghi = 800 * daylight * max(0.2, math.sin(day_of_year / 365 * math.pi) + 0.4)
        out.append({
            "ts": ts, "temp_c": round(temp, 1), "cloud_pct": 40.0,
            "wind_ms": 3.0, "ghi_wm2": round(ghi, 1), "is_forecast": ts > datetime.now(),
        })
        ts += timedelta(hours=1)
    return out


def fetch_weather(start: datetime, end: datetime) -> List[dict]:
    """拉取 [start, end) 的逐小时天气；失败时回退仿真。"""
    now = datetime.now()
    points: Dict[datetime, dict] = {}
    try:
        with httpx.Client(timeout=15) as client:
            # 历史部分
            hist_end = min(end, now)
            if start < hist_end:
                r = client.get("https://archive-api.open-meteo.com/v1/archive", params={
                    "latitude": WEATHER_LAT, "longitude": WEATHER_LON,
                    "start_date": start.date().isoformat(),
                    "end_date": (hist_end - timedelta(hours=1)).date().isoformat(),
                    "hourly": "temperature_2m,cloud_cover,wind_speed_10m,shortwave_radiation",
                    "timezone": "Asia/Shanghai",
                })
                r.raise_for_status()
                data = r.json()["hourly"]
                for i, t in enumerate(data["time"]):
                    ts = datetime.fromisoformat(t)
                    points[ts] = {
                        "ts": ts,
                        "temp_c": data["temperature_2m"][i],
                        "cloud_pct": data["cloud_cover"][i],
                        "wind_ms": data["wind_speed_10m"][i],
                        "ghi_wm2": data["shortwave_radiation"][i],
                        "is_forecast": False,
                    }
            # 预报部分
            if end > now:
                r = client.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": WEATHER_LAT, "longitude": WEATHER_LON,
                    "start_date": max(start, now).date().isoformat(),
                    "end_date": end.date().isoformat(),
                    "hourly": "temperature_2m,cloud_cover,wind_speed_10m,shortwave_radiation",
                    "timezone": "Asia/Shanghai",
                })
                r.raise_for_status()
                data = r.json()["hourly"]
                for i, t in enumerate(data["time"]):
                    ts = datetime.fromisoformat(t)
                    if start <= ts < end:
                        points[ts] = {
                            "ts": ts,
                            "temp_c": data["temperature_2m"][i],
                            "cloud_pct": data["cloud_cover"][i],
                            "wind_ms": data["wind_speed_10m"][i],
                            "ghi_wm2": data["shortwave_radiation"][i],
                            "is_forecast": True,
                        }
    except Exception:
        return _simulated_weather(start, end)
    return [points[k] for k in sorted(points)] if points else _simulated_weather(start, end)
