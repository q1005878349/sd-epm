"""回测服务：预测策略 vs 固定谷时策略。

流程（逐日滚动）：
1. 用当日之前的全部历史训练模型，预测当日价格曲线；
2. 以预测价格为输入做 LP 优化，得到当日充放电计划；
3. 计划按实际（历史真实）价格结算 -> 预测策略的实际收益；
4. 同一天用固定谷时策略按实际价格结算 -> 基线收益；
5. 差值即"预测策略相比固定谷时"的日节省，再汇总周/月，年化为日均×365。
"""
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List
from sqlalchemy.orm import Session

from ..models import PriceRecord
from .params import get_params
from .forecast import predict_for_date
from .dispatch import optimize_dispatch, baseline_dispatch


def _actual_prices(db: Session, day, interval_min: int) -> List[dict]:
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    rows = (db.query(PriceRecord)
            .filter(PriceRecord.interval_min == interval_min,
                    PriceRecord.ts >= start, PriceRecord.ts < end)
            .order_by(PriceRecord.ts).all())
    return [{"ts": r.ts.isoformat(sep=" "), "price_retail": r.retail_price,
             "price_spot": r.spot_price} for r in rows]


def run_backtest(db: Session, start_date, end_date, interval_min: int = 60) -> dict:
    params = get_params(db)
    days = []
    d = start_date
    while d <= end_date:
        days.append(d)
        d += timedelta(days=1)

    daily = []
    for day in days:
        actual = _actual_prices(db, day, interval_min)
        if not actual:
            continue
        try:
            forecast = predict_for_date(db, day, interval_min)
        except ValueError:
            continue  # 历史不足，跳过
        sched_m, sum_m = optimize_dispatch(forecast, params)
        # 预测策略的计划按实际价格结算
        actual_map = {pt["ts"]: pt["price_retail"] for pt in actual}
        dt_h = interval_min / 60.0
        realized_m = sum(
            actual_map.get(s["ts"], s["price"]) * (s["discharge_kw"] - s["charge_kw"])
            for s in sched_m
        ) * dt_h
        _, sum_b = baseline_dispatch(actual, params)

        daily.append({
            "date": day.isoformat(),
            "model_revenue": round(float(realized_m), 2),
            "baseline_revenue": sum_b["revenue_yuan"],
            "saving": round(float(realized_m) - sum_b["revenue_yuan"], 2),
            "charge_in_valley_ratio_model": sum_m["charge_in_valley_ratio"],
            "discharge_in_peak_ratio_model": sum_m["discharge_in_peak_ratio"],
            "charge_in_valley_ratio_baseline": sum_b["charge_in_valley_ratio"],
            "discharge_in_peak_ratio_baseline": sum_b["discharge_in_peak_ratio"],
            "schedule_model": [
                {k: s[k] for k in ("ts", "action", "charge_kw", "discharge_kw",
                                   "soc_kwh", "tou", "tou_label", "tou_match")}
                for s in sched_m],
        })

    if not daily:
        raise ValueError("回测区间内没有可结算的数据（历史价格或训练数据不足）")

    weekly = defaultdict(float)
    monthly = defaultdict(float)
    for r in daily:
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        iso = d.isocalendar()
        weekly[f"{iso[0]}-W{iso[1]:02d}"] += r["saving"]
        monthly[d.strftime("%Y-%m")] += r["saving"]

    total_model = sum(r["model_revenue"] for r in daily)
    total_baseline = sum(r["baseline_revenue"] for r in daily)
    total_saving = total_model - total_baseline
    avg_daily_saving = total_saving / len(daily)

    return {
        "days": len(daily),
        "daily": daily,
        "weekly": [{"week": k, "saving": round(v, 2)} for k, v in sorted(weekly.items())],
        "monthly": [{"month": k, "saving": round(v, 2)} for k, v in sorted(monthly.items())],
        "summary": {
            "total_model_revenue": round(total_model, 2),
            "total_baseline_revenue": round(total_baseline, 2),
            "total_saving": round(total_saving, 2),
            "avg_daily_saving": round(avg_daily_saving, 2),
            "avg_weekly_saving": round(avg_daily_saving * 7, 2),
            "avg_monthly_saving": round(avg_daily_saving * 30.4, 2),
            "projected_yearly_saving": round(avg_daily_saving * 365, 2),
            "saving_pct": round(total_saving / abs(total_baseline) * 100, 1)
            if total_baseline else None,
        },
        "note": "年节省为区间日均节省 × 365 的年化估算；周/月为区间实际汇总。",
    }
