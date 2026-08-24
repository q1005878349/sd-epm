"""法定节假日适配器：timor.tech 公开 API（免费、无需密钥）。

网络不可用时回退到内置的节假日列表，保证离线可用。
"""
from datetime import date, datetime
from typing import Dict
import httpx

# 内置回退列表（2025-2026 主要假期，近似）
_BUILTIN = {
    "2025-01-01": ("元旦", True),
    "2025-01-28": ("除夕", True), "2025-01-29": ("春节", True),
    "2025-01-30": ("春节", True), "2025-01-31": ("春节", True),
    "2025-02-01": ("春节", True), "2025-02-02": ("春节", True),
    "2025-02-03": ("春节", True), "2025-02-04": ("春节", True),
    "2025-04-04": ("清明节", True), "2025-04-05": ("清明节", True),
    "2025-04-06": ("清明节", True),
    "2025-05-01": ("劳动节", True), "2025-05-02": ("劳动节", True),
    "2025-05-03": ("劳动节", True), "2025-05-04": ("劳动节", True),
    "2025-05-05": ("劳动节", True),
    "2025-05-31": ("端午节", True), "2025-06-01": ("端午节", True),
    "2025-06-02": ("端午节", True),
    "2025-10-01": ("国庆节", True), "2025-10-02": ("国庆节", True),
    "2025-10-03": ("国庆节", True), "2025-10-04": ("国庆节", True),
    "2025-10-05": ("国庆节", True), "2025-10-06": ("中秋节", True),
    "2025-10-07": ("国庆节", True), "2025-10-08": ("国庆节", True),
    "2026-01-01": ("元旦", True), "2026-01-02": ("元旦", True),
    "2026-01-03": ("元旦", True),
    "2026-02-16": ("除夕", True), "2026-02-17": ("春节", True),
    "2026-02-18": ("春节", True), "2026-02-19": ("春节", True),
    "2026-02-20": ("春节", True), "2026-02-21": ("春节", True),
    "2026-02-22": ("春节", True), "2026-02-23": ("春节", True),
    "2026-04-04": ("清明节", True), "2026-04-05": ("清明节", True),
    "2026-04-06": ("清明节", True),
    "2026-05-01": ("劳动节", True), "2026-05-02": ("劳动节", True),
    "2026-05-03": ("劳动节", True), "2026-05-04": ("劳动节", True),
    "2026-05-05": ("劳动节", True),
    "2026-06-19": ("端午节", True), "2026-06-20": ("端午节", True),
    "2026-06-21": ("端午节", True),
    "2026-09-25": ("中秋节", True), "2026-09-26": ("中秋节", True),
    "2026-09-27": ("中秋节", True),
    "2026-10-01": ("国庆节", True), "2026-10-02": ("国庆节", True),
    "2026-10-03": ("国庆节", True), "2026-10-04": ("国庆节", True),
    "2026-10-05": ("国庆节", True), "2026-10-06": ("国庆节", True),
    "2026-10-07": ("国庆节", True),
}


def fetch_holidays(year: int) -> Dict[date, dict]:
    """返回 {date: {"name":..., "is_offday":...}}。优先在线 API，失败回退内置。"""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"https://timor.tech/api/holiday/year/{year}")
            r.raise_for_status()
            payload = r.json()
            out = {}
            for dstr, info in (payload.get("holiday") or {}).items():
                d = datetime.strptime(dstr, "%Y-%m-%d").date()
                out[d] = {"name": info.get("name", ""), "is_offday": bool(info.get("holiday", True))}
            if out:
                return out
    except Exception:
        pass
    return {datetime.strptime(k, "%Y-%m-%d").date(): {"name": v[0], "is_offday": v[1]}
            for k, v in _BUILTIN.items() if k.startswith(str(year))}
