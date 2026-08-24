"""现货价 -> 工商业到户电价转换。

retail(元/kWh) = spot(元/MWh) / 1000 * multiplier + adder
adder 近似打包输配电价、系统运行费、政府性基金及附加、线损折价等，
multiplier / adder 均可在参数中调节。
"""


def spot_to_retail(spot_yuan_mwh: float, multiplier: float, adder: float) -> float:
    return round(spot_yuan_mwh / 1000.0 * multiplier + adder, 4)
