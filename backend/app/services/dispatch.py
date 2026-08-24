"""储能充放电调度优化。

模型策略：以预测电价为输入的线性规划（LP），
  变量：每时段充电功率 c_t、放电功率 d_t、SOC s_t
  目标：max Σ p_t·(d_t − c_t)·Δt
  约束：SOC 动态（含充放电效率）、SOC 上下限、充电功率上限、
        放电功率上限、电网输电功率上限、日循环次数上限、日末 SOC 回到初始值

基线策略：固定谷时充电（低谷/深谷时段满功率充电，高峰/尖峰时段放电）。

每个时段标注分时电价类型（深谷/低谷/平段/高峰/尖峰），
并给出"充电是否落在谷段 / 放电是否落在峰段"的符合性标识。
"""
from datetime import datetime, timedelta
from typing import List, Tuple
import numpy as np
from scipy.optimize import linprog

from ..config import TOU_PERIODS, TOU_LABELS, CHARGE_GOOD, DISCHARGE_GOOD, tou_type_of


def _annotate(ts: datetime, action: str) -> dict:
    tou = tou_type_of(ts, TOU_PERIODS)
    if action == "charge":
        match = "good" if tou in CHARGE_GOOD else ("neutral" if tou == "flat" else "bad")
    elif action == "discharge":
        match = "good" if tou in DISCHARGE_GOOD else ("neutral" if tou == "flat" else "bad")
    else:
        match = "idle"
    return {"tou": tou, "tou_label": TOU_LABELS[tou], "tou_match": match}


def optimize_dispatch(prices: List[dict], params: dict) -> Tuple[List[dict], dict]:
    """LP 优化。prices: [{ts, price_retail}]。返回 (schedule, summary)。"""
    n = len(prices)
    if n == 0:
        return [], {}
    dt_h = (datetime.fromisoformat(prices[1]["ts"]) - datetime.fromisoformat(prices[0]["ts"])
            ).total_seconds() / 3600.0 if n > 1 else 1.0
    p = np.array([pt["price_retail"] for pt in prices])  # 元/kWh

    C = params["battery_capacity_kwh"]
    Pc = min(params["max_charge_power_kw"], params["grid_power_limit_kw"])
    Pd = params["max_discharge_power_kw"]
    eta_c = params["charge_efficiency"]
    eta_d = params["discharge_efficiency"]
    s_lo, s_hi = params["soc_min"] * C, params["soc_max"] * C
    s0 = params["soc_init"] * C
    max_cycles = params.get("max_daily_cycles", 2.0)

    # 变量 x = [c_0..c_{n-1}, d_0..d_{n-1}, s_0..s_n]，共 3n+1 个
    c_obj = np.concatenate([p * dt_h, -p * dt_h, np.zeros(n + 1)])  # 最小化成本

    # SOC 动态等式：s_{t+1} - s_t - eta_c*dt*c_t + (dt/eta_d)*d_t = 0
    A_eq = np.zeros((n + 2, 3 * n + 1))
    b_eq = np.zeros(n + 2)
    for t in range(n):
        A_eq[t, 2 * n + t] = -1.0        # -s_t
        A_eq[t, 2 * n + t + 1] = 1.0     # +s_{t+1}
        A_eq[t, t] = -eta_c * dt_h       # -eta_c*dt*c_t
        A_eq[t, n + t] = dt_h / eta_d    # +dt/eta_d*d_t
    A_eq[n, 2 * n] = 1.0
    b_eq[n] = s0                          # s_0 = 初始 SOC
    A_eq[n + 1, 2 * n + n] = 1.0
    b_eq[n + 1] = s0                      # 日末 SOC 回到初始（跨日可比）

    # 日循环次数上限：Σ c_t·dt ≤ max_cycles·C
    A_ub = np.zeros((1, 3 * n + 1))
    A_ub[0, :n] = dt_h
    b_ub = np.array([max_cycles * C])

    bounds = ([(0, Pc)] * n + [(0, Pd)] * n + [(s_lo, s_hi)] * (n + 1))
    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"调度优化失败：{res.message}")

    x = res.x
    charge, discharge, soc = x[:n], x[n:2 * n], x[2 * n:]
    eps = 1e-4
    schedule = []
    for t, pt in enumerate(prices):
        ts = datetime.fromisoformat(pt["ts"])
        c, d = float(charge[t]), float(discharge[t])
        action = "charge" if c > eps else ("discharge" if d > eps else "idle")
        ann = _annotate(ts, action)
        schedule.append({
            "ts": pt["ts"], "action": action,
            "charge_kw": round(c, 2), "discharge_kw": round(d, 2),
            "soc_kwh": round(float(soc[t]), 2),
            "price": pt["price_retail"], **ann,
        })

    chg_kwh = float((charge * dt_h).sum())
    dis_kwh = float((discharge * dt_h).sum())
    revenue = float((p * (discharge - charge) * dt_h).sum())
    good_c = sum(1 for s in schedule if s["action"] == "charge" and s["tou_match"] == "good")
    good_d = sum(1 for s in schedule if s["action"] == "discharge" and s["tou_match"] == "good")
    n_c = sum(1 for s in schedule if s["action"] == "charge")
    n_d = sum(1 for s in schedule if s["action"] == "discharge")
    summary = {
        "revenue_yuan": round(revenue, 2),
        "charge_kwh": round(chg_kwh, 1),
        "discharge_kwh": round(dis_kwh, 1),
        "cycles": round(chg_kwh / C, 2) if C else 0,
        "charge_in_valley_ratio": round(good_c / n_c, 3) if n_c else None,
        "discharge_in_peak_ratio": round(good_d / n_d, 3) if n_d else None,
    }
    return schedule, summary


def baseline_dispatch(prices: List[dict], params: dict) -> Tuple[List[dict], dict]:
    """固定谷时策略：低谷/深谷满功率充电至 SOC 上限，高峰/尖峰放电至 SOC 下限。"""
    n = len(prices)
    if n == 0:
        return [], {}
    dt_h = (datetime.fromisoformat(prices[1]["ts"]) - datetime.fromisoformat(prices[0]["ts"])
            ).total_seconds() / 3600.0 if n > 1 else 1.0
    C = params["battery_capacity_kwh"]
    Pc = min(params["max_charge_power_kw"], params["grid_power_limit_kw"])
    Pd = params["max_discharge_power_kw"]
    eta_c, eta_d = params["charge_efficiency"], params["discharge_efficiency"]
    s_lo, s_hi = params["soc_min"] * C, params["soc_max"] * C
    soc = params["soc_init"] * C

    schedule = []
    for pt in prices:
        ts = datetime.fromisoformat(pt["ts"])
        tou = tou_type_of(ts, TOU_PERIODS)
        c = d = 0.0
        if tou in CHARGE_GOOD and soc < s_hi:
            c = min(Pc, (s_hi - soc) / (eta_c * dt_h))
            soc += eta_c * c * dt_h
        elif tou in DISCHARGE_GOOD and soc > s_lo:
            d = min(Pd, (soc - s_lo) * eta_d / dt_h)
            soc -= d * dt_h / eta_d
        action = "charge" if c > 1e-4 else ("discharge" if d > 1e-4 else "idle")
        ann = _annotate(ts, action)
        schedule.append({
            "ts": pt["ts"], "action": action,
            "charge_kw": round(float(c), 2), "discharge_kw": round(float(d), 2),
            "soc_kwh": round(float(soc), 2),
            "price": pt["price_retail"], **ann,
        })
    chg = sum(s["charge_kw"] for s in schedule) * dt_h
    dis = sum(s["discharge_kw"] for s in schedule) * dt_h
    revenue = sum(s["price"] * (s["discharge_kw"] - s["charge_kw"]) for s in schedule) * dt_h
    good_c = sum(1 for s in schedule if s["action"] == "charge" and s["tou_match"] == "good")
    good_d = sum(1 for s in schedule if s["action"] == "discharge" and s["tou_match"] == "good")
    n_c = sum(1 for s in schedule if s["action"] == "charge")
    n_d = sum(1 for s in schedule if s["action"] == "discharge")
    summary = {
        "revenue_yuan": round(float(revenue), 2),
        "charge_kwh": round(float(chg), 1),
        "discharge_kwh": round(float(dis), 1),
        "cycles": round(float(chg) / C, 2) if C else 0,
        "charge_in_valley_ratio": round(good_c / n_c, 3) if n_c else None,
        "discharge_in_peak_ratio": round(good_d / n_d, 3) if n_d else None,
    }
    return schedule, summary
