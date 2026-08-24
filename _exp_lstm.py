"""LSTM 原型实验：用真实山东现货数据训练，评估 24h 预测 MAE（与 HGB / TimeMixer++ 同口径对比）。

- 数据：真实 60min 现货价（2026-01-01 ~ 08-19），n_steps=168 历史 -> 预测 n_pred=24
- 变体：单变量(仅现货价) / 6通道(现货价+日历特征)
- RevIN 逐窗标准化；MSE；Adam；验证集早停；GPU
"""
import os, sys, math, datetime as dt
import numpy as np
import torch
import torch.nn as nn

os.environ["CUDA_CACHE_PATH"] = r"C:\Users\Administrator\Desktop\Kimi_Agent_山东电价预测系统\sd-epm\backend\.cuda_cache"
torch.manual_seed(42)
np.random.seed(42)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print("设备:", DEVICE, torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")

sys.path.insert(0, r"C:\Users\Administrator\Desktop\Kimi_Agent_山东电价预测系统\sd-epm\backend")
from app.database import SessionLocal
from app.models import PriceRecord

db = SessionLocal()
rows = (db.query(PriceRecord).filter(PriceRecord.interval_min == 60)
        .order_by(PriceRecord.ts).all())
db.close()
tss = [r.ts for r in rows]
spot = np.array([r.spot_price for r in rows], dtype=np.float64)
print(f"数据点: {len(spot)} ({rows[0].ts.date()} ~ {rows[-1].ts.date()})")


def calendar_feats(ts):
    frac = (ts.hour * 60 + ts.minute) / 1440.0
    return [math.sin(2 * math.pi * frac), math.cos(2 * math.pi * frac),
            float(ts.weekday()), 1.0 if ts.weekday() >= 5 else 0.0, float(ts.month)]


def build_windows(channels):
    """channels: (n, n_ch)；返回 X(n,168,n_ch), y(n,24,n_ch)"""
    X, y = [], []
    for i in range(len(channels) - 168 - 24 + 1):
        X.append(channels[i:i + 168])
        y.append(channels[i + 168:i + 168 + 24])
    return np.asarray(X), np.asarray(y)


class LSTMForecaster(nn.Module):
    def __init__(self, n_features, n_pred, hidden=64, layers=2, dropout=0.1):
        super().__init__()
        self.n_pred = n_pred
        self.lstm = nn.LSTM(n_features, hidden, layers, batch_first=True, dropout=dropout)
        self.head = nn.Linear(hidden, n_pred * n_features)

    def forward(self, x):
        out, _ = self.lstm(x)           # (B, 168, H)
        h = out[:, -1]                  # 最后一步
        return self.head(h).reshape(-1, self.n_pred, x.shape[-1])


def train_lstm(tr_X, tr_y, va_X, va_y, epochs=50, patience=10, batch=128, lr=1e-3):
    n_ch = tr_X.shape[-1]

    # RevIN 逐窗标准化（按每个样本自己的均值/方差），预测后还原
    def revin(X, Y):
        m = X.mean(axis=1, keepdims=True)
        s = X.std(axis=1, keepdims=True) + 1e-5
        Xn = (X - m) / s
        Yn = (Y - m) / s
        return Xn, Yn, m, s

    def inv_revin(P, m, s):
        return P * s + m

    trXn, trYn, trm, trs = revin(tr_X, tr_y)
    vaXn, vaYn, vam, vas = revin(va_X, va_y)

    model = LSTMForecaster(n_ch, 24, hidden=96, layers=2, dropout=0.1).to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=3, factor=0.5)
    lossf = nn.MSELoss()
    trX = torch.tensor(trXn, dtype=torch.float32)
    trY = torch.tensor(trYn, dtype=torch.float32)
    vaX = torch.tensor(vaXn, dtype=torch.float32)
    vaY = torch.tensor(vaYn, dtype=torch.float32)
    best, best_mae, bad = None, 1e9, 0
    n = len(trX)
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            xb, yb = trX[idx].to(DEVICE), trY[idx].to(DEVICE)
            opt.zero_grad()
            loss = lossf(model(xb), yb)
            loss.backward()
            opt.step()
        # 验证 MAE（现货价通道，还原到原量纲）
        model.eval()
        with torch.no_grad():
            pred = inv_revin(model(vaX.to(DEVICE)).cpu().numpy(), vam, vas)
        mae = float(np.mean(np.abs(pred[:, :, 0] - va_y[:, :, 0])))
        sched.step(mae)
        if mae < best_mae:
            best_mae, bad, best = mae, 0, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best)
    return model, best_mae


def evaluate(desc, series):
    X, y = build_windows(series)
    cut = len(series) - 168 - 30 * 24
    if cut < len(X) * 0.3:
        cut = int(len(X) * 0.7)
    tr_X, tr_y = X[:cut], y[:cut]
    va_X, va_y = X[cut:], y[cut:]
    # 参照基线：持久性（用历史最后值平推24h）
    persist_mae = float(np.mean(np.abs(va_X[:, -1, 0][:, None] - va_y[:, :, 0])))
    model, _ = train_lstm(tr_X, tr_y, va_X, va_y)
    # 最终验证集 MAE（用验证集自身的逐窗均值/方差标准化并还原）
    va_m = va_X.mean(axis=1, keepdims=True)
    va_s = va_X.std(axis=1, keepdims=True) + 1e-5
    vaXn = (va_X - va_m) / va_s
    vaT = torch.tensor(vaXn, dtype=torch.float32)
    model.eval()
    with torch.no_grad():
        pred_norm = model(vaT.to(DEVICE)).cpu().numpy()
    pred = pred_norm * va_s + va_m
    mae = float(np.mean(np.abs(pred[:, :, 0] - va_y[:, :, 0])))
    rmse = float(np.sqrt(np.mean((pred[:, :, 0] - va_y[:, :, 0]) ** 2)))
    print(f"[{desc}] 验证 MAE = {mae:.2f} 元/MWh | RMSE = {rmse:.2f} | 持久性基线 MAE = {persist_mae:.2f}")
    return mae


# ---- 单变量：仅现货价 ----
spot_series = spot.reshape(-1, 1)
evaluate("LSTM 单变量", spot_series)

# ---- 6 通道：现货价 + 日历特征 ----
feats = np.array([calendar_feats(t) for t in tss], dtype=np.float64)
multi = np.column_stack([spot, feats])
evaluate("LSTM 6通道(含日历)", multi)

print("参考: HGB ≈ 36~40 | TimeMixer++ 单变量 73.9 / 含日历 79.2")
