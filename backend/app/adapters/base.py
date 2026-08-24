"""价格数据适配器接口。

要接入真实数据源（如山东电力交易中心、第三方数据商），只需：
1. 继承 PriceDataAdapter，实现 fetch_spot_prices(start, end, interval_min)
2. 在 services/sync.py 的 ADAPTERS 注册表中登记
系统其余部分（预测、调度、回测）不需要任何改动。
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, TypedDict


class SpotPricePoint(TypedDict):
    ts: datetime          # 时段起始时间（本地时间，naive）
    spot_price: float     # 现货价，元/MWh


class PriceDataAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def fetch_spot_prices(self, start: datetime, end: datetime,
                          interval_min: int = 60) -> List[SpotPricePoint]:
        """拉取 [start, end) 区间、指定颗粒度的现货价格序列。"""
        raise NotImplementedError
