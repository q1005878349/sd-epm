"""系统默认配置与山东工商业分时电价（峰谷）时段定义。

注意：分时时段为可配置的近似值，政策会随年份/季节调整，
请以山东省发改委最新文件为准，可在 /api/params 中在线修改。
"""
from datetime import date, datetime

# 默认系统参数（可在前端"参数设置"页修改，持久化到 system_params 表）
DEFAULT_PARAMS = {
    # ---- 电池参数 ----
    "battery_capacity_kwh": 500.0,      # 电池容量
    "max_charge_power_kw": 250.0,       # 电池最大充电功率
    "max_discharge_power_kw": 250.0,    # 电池最大放电功率
    "grid_power_limit_kw": 400.0,       # 电网输电（并网）功率上限
    "soc_min": 0.05,                    # SOC 下限
    "soc_max": 0.95,                    # SOC 上限
    "soc_init": 0.5,                    # 每日初始 SOC
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95,
    "max_daily_cycles": 2.0,            # 每日最大等效循环次数
    # ---- 工商业到户电价转换：retail = spot/1000 * multiplier + adder ----
    # adder 近似含输配电价、系统运行费、政府性基金及附加、线损等
    "retail_multiplier": 1.0,
    "retail_adder_yuan_kwh": 0.238,
    # ---- 预测模型参数 ----
    "train_days": 60,          # 训练窗口（天）
    "lag_days": [1, 2, 3, 7],  # 滞后特征天数
    # ---- 数据颗粒度：60=按小时计价，15=15 分钟计价 ----
    "interval_min": 60,
}

# 山东工商业分时电价时段（近似，可配置）。
# 每段: (开始小时, 结束小时, 类型)  类型: deep_valley/valley/flat/peak/sharp
TOU_PERIODS = [
    (0, 7, "valley"),
    (7, 8, "flat"),
    (8, 11, "peak"),
    (11, 14, "deep_valley"),   # 山东午间光伏大发时段设置的深谷
    (14, 16, "flat"),
    (16, 17, "peak"),
    (17, 20, "sharp"),         # 晚尖峰（夏冬季月份更为典型）
    (20, 22, "peak"),
    (22, 23, "flat"),
    (23, 24, "valley"),
]

TOU_LABELS = {
    "deep_valley": "深谷",
    "valley": "低谷",
    "flat": "平段",
    "peak": "高峰",
    "sharp": "尖峰",
}

# 充电推荐时段类型（用于"充电是否落在谷段"的标识）
CHARGE_GOOD = {"valley", "deep_valley"}
DISCHARGE_GOOD = {"peak", "sharp"}


def tou_type_of(ts: datetime, periods=None) -> str:
    """返回某时刻所属的分时电价类型。"""
    periods = periods or TOU_PERIODS
    h = ts.hour + ts.minute / 60.0
    for start, end, kind in periods:
        if start <= h < end:
            return kind
    return "flat"


# 仿真数据起始日：向前生成的历史天数
SIM_HISTORY_DAYS = 120

# 天气坐标：默认济南（山东负荷中心），可改
WEATHER_LAT = 36.65
WEATHER_LON = 117.12
