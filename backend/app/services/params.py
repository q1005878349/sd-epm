"""系统参数读写（持久化到 system_params 表）。"""
import copy
from sqlalchemy.orm import Session
from ..models import SystemParams
from ..config import DEFAULT_PARAMS


def get_params(db: Session) -> dict:
    row = db.query(SystemParams).first()
    if not row:
        payload = copy.deepcopy(DEFAULT_PARAMS)
        db.add(SystemParams(payload=payload))
        db.commit()
        return payload
    merged = copy.deepcopy(DEFAULT_PARAMS)
    merged.update(row.payload or {})
    return merged


def update_params(db: Session, patch: dict) -> dict:
    current = get_params(db)
    for k, v in patch.items():
        if k in DEFAULT_PARAMS:
            current[k] = v
    row = db.query(SystemParams).first()
    row.payload = current
    db.commit()
    return current
