"""数据同步编排：价格 / 天气 / 节假日入库。

价格数据通过适配器接口接入——当前注册的是仿真器；
接入真实数据源时，在 ADAPTERS 中注册你的适配器实现即可。
"""
from datetime import datetime, timedelta, time as dtime
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..models import PriceRecord, WeatherRecord, Holiday
from ..adapters.simulator import SimulatorAdapter
from ..adapters.weather import fetch_weather
from ..adapters.holidays import fetch_holidays
from .params import get_params
from .pricing import spot_to_retail

# 价格数据适配器注册表：接入真实数据时替换/新增
ADAPTERS = {
    "simulator": SimulatorAdapter(),
}
DEFAULT_ADAPTER = "simulator"


def sync_prices(db: Session, days: int = 120, interval_min: int = 60,
                adapter_name: str = DEFAULT_ADAPTER) -> int:
    """生成/拉取最近 days 天的现货价，并转换出工商业电价入库。返回写入条数。"""
    adapter = ADAPTERS[adapter_name]
    params = get_params(db)
    end = datetime.combine(datetime.now().date() + timedelta(days=1), dtime.min)
    start = end - timedelta(days=days)

    # 天气与节假日用于驱动仿真器（真实适配器通常不需要）
    weather = {w["ts"]: w for w in fetch_weather(start - timedelta(days=1), end)}
    holiday_dates = set()
    for year in {start.year, end.year}:
        holiday_dates |= {d for d, h in fetch_holidays(year).items() if h["is_offday"]}

    if adapter_name == "simulator":
        points = adapter.fetch_spot_prices(start, end, interval_min,
                                           weather=weather, holiday_dates=holiday_dates)
    else:
        points = adapter.fetch_spot_prices(start, end, interval_min)

    count = 0
    for p in points:
        stmt = sqlite_insert(PriceRecord).values(
            ts=p["ts"], interval_min=interval_min, spot_price=p["spot_price"],
            retail_price=spot_to_retail(p["spot_price"], params["retail_multiplier"],
                                        params["retail_adder_yuan_kwh"]),
            source=adapter.name,
        ).on_conflict_do_update(
            index_elements=["ts", "interval_min"],
            set_={"spot_price": p["spot_price"],
                  "retail_price": spot_to_retail(p["spot_price"], params["retail_multiplier"],
                                                 params["retail_adder_yuan_kwh"]),
                  "source": adapter.name},
        )
        db.execute(stmt)
        count += 1
    db.commit()
    return count


def sync_weather(db: Session, days_back: int = 120, days_forward: int = 3) -> int:
    start = datetime.now() - timedelta(days=days_back)
    end = datetime.now() + timedelta(days=days_forward)
    count = 0
    for w in fetch_weather(start, end):
        stmt = sqlite_insert(WeatherRecord).values(
            ts=w["ts"], temp_c=w["temp_c"], cloud_pct=w["cloud_pct"],
            wind_ms=w["wind_ms"], ghi_wm2=w["ghi_wm2"], is_forecast=w["is_forecast"],
        ).on_conflict_do_update(
            index_elements=["ts"],
            set_={"temp_c": w["temp_c"], "cloud_pct": w["cloud_pct"],
                  "wind_ms": w["wind_ms"], "ghi_wm2": w["ghi_wm2"],
                  "is_forecast": w["is_forecast"]},
        )
        db.execute(stmt)
        count += 1
    db.commit()
    return count


def sync_holidays(db: Session, years=None) -> int:
    years = years or [datetime.now().year - 1, datetime.now().year, datetime.now().year + 1]
    count = 0
    for y in years:
        for d, info in fetch_holidays(y).items():
            stmt = sqlite_insert(Holiday).values(
                date=d, name=info["name"], is_offday=info["is_offday"],
            ).on_conflict_do_update(
                index_elements=["date"],
                set_={"name": info["name"], "is_offday": info["is_offday"]},
            )
            db.execute(stmt)
            count += 1
    db.commit()
    return count


def sync_all(db: Session) -> dict:
    """首次启动/手动触发：全量同步。"""
    params = get_params(db)
    interval = int(params.get("interval_min", 60))
    return {
        "holidays": sync_holidays(db),
        "weather": sync_weather(db),
        "prices_60min": sync_prices(db, interval_min=60),
        "prices_15min": sync_prices(db, interval_min=15),
        "active_interval": interval,
    }
