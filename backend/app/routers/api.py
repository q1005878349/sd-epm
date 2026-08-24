"""全部 REST API 路由。"""
from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PriceRecord, ForecastRun, DispatchPlan, BacktestResult, WeatherRecord
from ..config import TOU_PERIODS, TOU_LABELS, tou_type_of
from ..services import sync as sync_svc
from ..services.params import get_params, update_params
from ..services.forecast import run_forecast, predict_for_date
from ..services.dispatch import optimize_dispatch, baseline_dispatch
from ..services.backtest import run_backtest

router = APIRouter(prefix="/api")


# ---------- 数据同步 ----------
@router.post("/sync")
def sync_all(db: Session = Depends(get_db)):
    return sync_svc.sync_all(db)


@router.post("/sync/prices")
def sync_prices(days: int = 120, interval_min: int = 60, db: Session = Depends(get_db)):
    return {"written": sync_svc.sync_prices(db, days=days, interval_min=interval_min)}


# ---------- 价格查询 ----------
@router.get("/prices")
def get_prices(day: date = Query(None), interval_min: int = 60,
               db: Session = Depends(get_db)):
    """某一天的现货价与工商业电价。不传 day 时返回最新一天。"""
    q = db.query(PriceRecord).filter(PriceRecord.interval_min == interval_min)
    if day is None:
        latest = q.order_by(PriceRecord.ts.desc()).first()
        if not latest:
            raise HTTPException(404, "没有价格数据，请先同步")
        day = latest.ts.date()
    start = datetime.combine(day, datetime.min.time())
    rows = q.filter(PriceRecord.ts >= start,
                    PriceRecord.ts < start + timedelta(days=1)) \
            .order_by(PriceRecord.ts).all()
    return {
        "date": day.isoformat(), "interval_min": interval_min,
        "points": [{
            "ts": r.ts.isoformat(sep=" "),
            "spot": r.spot_price, "retail": r.retail_price,
            "tou": tou_type_of(r.ts, TOU_PERIODS),
            "tou_label": TOU_LABELS[tou_type_of(r.ts, TOU_PERIODS)],
            "source": r.source,
        } for r in rows],
    }


@router.get("/prices/latest")
def latest_price(interval_min: int = 60, db: Session = Depends(get_db)):
    r = (db.query(PriceRecord).filter(PriceRecord.interval_min == interval_min)
         .order_by(PriceRecord.ts.desc()).first())
    if not r:
        raise HTTPException(404, "没有价格数据")
    return {"ts": r.ts.isoformat(sep=" "), "spot": r.spot_price,
            "retail": r.retail_price, "source": r.source,
            "tou_label": TOU_LABELS[tou_type_of(r.ts, TOU_PERIODS)]}


# ---------- 预测 ----------
class ForecastRequest(BaseModel):
    horizon: str = "24h"       # "24h" | "1h"
    interval_min: int = 60     # 60 | 15


@router.post("/forecast")
def create_forecast(req: ForecastRequest, db: Session = Depends(get_db)):
    if req.horizon not in ("24h", "1h"):
        raise HTTPException(400, "horizon 仅支持 24h / 1h")
    if req.interval_min not in (60, 15):
        raise HTTPException(400, "interval_min 仅支持 60 / 15")
    try:
        points, mae = run_forecast(db, req.horizon, req.interval_min)
    except ValueError as e:
        raise HTTPException(400, str(e))
    run = ForecastRun(horizon=req.horizon, interval_min=req.interval_min,
                      mae=mae, points=points)
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "created_at": run.created_at.isoformat(sep=" "),
            "horizon": run.horizon, "interval_min": run.interval_min,
            "mae": mae, "points": points}


@router.get("/forecast/latest")
def latest_forecast(horizon: str = "24h", interval_min: int = 60,
                    db: Session = Depends(get_db)):
    run = (db.query(ForecastRun)
           .filter(ForecastRun.horizon == horizon,
                   ForecastRun.interval_min == interval_min)
           .order_by(ForecastRun.id.desc()).first())
    if not run:
        raise HTTPException(404, "还没有预测结果，请先运行预测")
    return {"id": run.id, "created_at": run.created_at.isoformat(sep=" "),
            "horizon": run.horizon, "interval_min": run.interval_min,
            "mae": run.mae, "points": run.points}


# ---------- 调度 ----------
class DispatchRequest(BaseModel):
    interval_min: int = 60
    forecast_id: Optional[int] = None  # 不指定则现场做一次 24h 预测


@router.post("/dispatch")
def create_dispatch(req: DispatchRequest, db: Session = Depends(get_db)):
    params = get_params(db)
    if req.forecast_id:
        run = db.query(ForecastRun).get(req.forecast_id)
        if not run:
            raise HTTPException(404, "预测结果不存在")
        points = run.points
        forecast_id = run.id
    else:
        try:
            points, mae = run_forecast(db, "24h", req.interval_min)
        except ValueError as e:
            raise HTTPException(400, str(e))
        run = ForecastRun(horizon="24h", interval_min=req.interval_min,
                          mae=mae, points=points)
        db.add(run)
        db.commit()
        db.refresh(run)
        forecast_id = run.id

    schedule, summary = optimize_dispatch(points, params)
    plan = DispatchPlan(forecast_id=forecast_id, interval_min=req.interval_min,
                        params_snapshot=params, schedule=schedule, summary=summary)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, "created_at": plan.created_at.isoformat(sep=" "),
            "forecast_id": forecast_id, "params": params,
            "schedule": schedule, "summary": summary}


@router.get("/dispatch/latest")
def latest_dispatch(db: Session = Depends(get_db)):
    plan = db.query(DispatchPlan).order_by(DispatchPlan.id.desc()).first()
    if not plan:
        raise HTTPException(404, "还没有调度计划，请先生成")
    return {"id": plan.id, "created_at": plan.created_at.isoformat(sep=" "),
            "forecast_id": plan.forecast_id, "params": plan.params_snapshot,
            "schedule": plan.schedule, "summary": plan.summary}


@router.get("/dispatch/for-date")
def dispatch_for_date(day: date = Query(...), interval_min: int = 60,
                      db: Session = Depends(get_db)):
    """某一天：真实/预测工商电价 + 两种口径的调度对比（用于充放着色对比）。

    - schedule_actual:    按该日实际价格（完美预见）+ 当前参数做 LP
    - schedule_predicted: 按"该日之前数据预测的价格"+ 当前参数做 LP（与回测一致，无未来信息）
    """
    params = get_params(db)
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    rows = (db.query(PriceRecord)
            .filter(PriceRecord.interval_min == interval_min,
                    PriceRecord.ts >= start, PriceRecord.ts < end)
            .order_by(PriceRecord.ts).all())
    if not rows:
        raise HTTPException(404, "该日期没有价格数据，请先同步")
    prices = [{"ts": r.ts.isoformat(sep=" "), "price_spot": r.spot_price,
               "price_retail": r.retail_price} for r in rows]

    # 口径一：按实际价格（完美预见）
    schedule_actual, summary_actual = optimize_dispatch(prices, params)

    # 口径二：按"当日之前数据"预测的价格
    forecast, schedule_predicted, summary_predicted = [], [], {}
    try:
        forecast = predict_for_date(db, day, interval_min)
        schedule_predicted, summary_predicted = optimize_dispatch(forecast, params)
    except (ValueError, RuntimeError):
        pass  # 该日前历史不足或优化失败：预测口径留空，仅展示实际口径

    return {
        "date": day.isoformat(), "interval_min": interval_min,
        "prices": [{"ts": p["ts"], "spot": p["price_spot"], "retail": p["price_retail"],
                    "tou": tou_type_of(datetime.fromisoformat(p["ts"]), TOU_PERIODS),
                    "tou_label": TOU_LABELS[tou_type_of(datetime.fromisoformat(p["ts"]), TOU_PERIODS)]}
                   for p in prices],
        "forecast": [{"ts": p["ts"], "price_spot": p["price_spot"],
                      "price_retail": p["price_retail"]} for p in forecast],
        "schedule_actual": schedule_actual, "summary_actual": summary_actual,
        "schedule_predicted": schedule_predicted, "summary_predicted": summary_predicted,
    }


# ---------- 回测 ----------
class BacktestRequest(BaseModel):
    start_date: date
    end_date: date
    interval_min: int = 60


@router.post("/backtest")
def create_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    if req.end_date < req.start_date:
        raise HTTPException(400, "end_date 不能早于 start_date")
    try:
        result = run_backtest(db, req.start_date, req.end_date, req.interval_min)
    except ValueError as e:
        raise HTTPException(400, str(e))
    row = BacktestResult(start_date=req.start_date, end_date=req.end_date,
                         interval_min=req.interval_min,
                         params_snapshot=get_params(db), result=result)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "created_at": row.created_at.isoformat(sep=" "), **result}


@router.get("/backtest/latest")
def latest_backtest(db: Session = Depends(get_db)):
    row = db.query(BacktestResult).order_by(BacktestResult.id.desc()).first()
    if not row:
        raise HTTPException(404, "还没有回测结果")
    return {"id": row.id, "created_at": row.created_at.isoformat(sep=" "),
            "start_date": row.start_date.isoformat(),
            "end_date": row.end_date.isoformat(), **row.result}


# ---------- 参数 ----------
@router.get("/params")
def read_params(db: Session = Depends(get_db)):
    return get_params(db)


@router.put("/params")
def write_params(patch: dict, db: Session = Depends(get_db)):
    return update_params(db, patch)


# ---------- 元信息 ----------
@router.get("/tou")
def get_tou():
    return {"periods": [{"start": s, "end": e, "type": t, "label": TOU_LABELS[t]}
                        for s, e, t in TOU_PERIODS],
            "labels": TOU_LABELS,
            "note": "分时时段为可配置近似值，请以山东省发改委最新政策为准"}
