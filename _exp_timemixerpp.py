"""TimeMixer++ (PyPOTS) 原型实验：用真实山东现货数据训练，评估 24h 预测 MAE。

只加载 pypots.forecasting.timemixerpp，跳过 pypots 完整初始化（避免拉入全生态依赖）。
对比基准：当前 HistGradientBoosting 模型的验证 MAE（约 36~40 元/MWh）。
"""
import sys, types, os
import numpy as np

VENDOR = r"C:\Users\Administrator\Desktop\Kimi_Agent_山东电价预测系统\sd-epm\backend\pyvendor"
sys.path.insert(0, VENDOR)

# ---- 只加载 timemixerpp 的 bootstrap（跳过 pypots 顶层 __init__，避免拉入全生态依赖）----
PYPOTS = os.path.join(VENDOR, "pypots")  # pyvendor 中的 pypots（纯 python，适配 3.10）
pkg = types.ModuleType("pypots"); pkg.__path__ = [PYPOTS]; pkg.__package__ = "pypots"
sys.modules["pypots"] = pkg
fc = types.ModuleType("pypots.forecasting")
fc.__path__ = [os.path.join(PYPOTS, "forecasting")]; fc.__package__ = "pypots.forecasting"
sys.modules["pypots.forecasting"] = fc

# pypots.base 会 import torch.utils.tensorboard，用 no-op stub 绕过（避免二进制 tensorboard 依赖）
fake_tb = types.ModuleType("torch.utils.tensorboard")
class _SummaryWriter:
    def __init__(self, *a, **k): pass
    def add_scalar(self, *a, **k): pass
    def add_scalars(self, *a, **k): pass
    def close(self): pass
fake_tb.SummaryWriter = _SummaryWriter
sys.modules.setdefault("torch.utils.tensorboard", fake_tb)

from pypots.forecasting.timemixerpp import TimeMixerPP

# ---- GPU ----
import os
os.environ["CUDA_CACHE_PATH"] = r"C:\Users\Administrator\Desktop\Kimi_Agent_山东电价预测系统\sd-epm\backend\.cuda_cache"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import torch
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"使用设备: {DEVICE} {torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''}")

# ---- 读真实现货价（60min）----
sys.path.insert(0, r"C:\Users\Administrator\Desktop\Kimi_Agent_山东电价预测系统\sd-epm\backend")
from app.database import SessionLocal
from app.models import PriceRecord
import math

db = SessionLocal()
rows = (db.query(PriceRecord).filter(PriceRecord.interval_min == 60)
        .order_by(PriceRecord.ts).all())
db.close()
tss = [r.ts for r in rows]
spot = np.array([r.spot_price for r in rows], dtype=np.float64)
print(f"数据点: {len(spot)} ({rows[0].ts.date()} ~ {rows[-1].ts.date()})")

# ---- 多通道特征：现货价 + 日历特征（与 HGB 对齐的周期信息）----
def calendar_feats(ts):
    frac = (ts.hour * 60 + ts.minute) / 1440.0
    return [math.sin(2 * math.pi * frac), math.cos(2 * math.pi * frac),
            float(ts.weekday()), 1.0 if ts.weekday() >= 5 else 0.0, float(ts.month)]
feats = np.array([calendar_feats(t) for t in tss], dtype=np.float64)
series = np.column_stack([spot, feats])  # (n, 6)：第0列为现货价
N_CH = series.shape[1]
print(f"特征通道: {N_CH} (现货价+时分sin/cos+星期+周末+月份)")

# ---- 构建滑窗：n_steps 历史 -> n_pred_steps 未来 ----
n_steps, n_pred = 168, 24
X, y = [], []
for i in range(len(series) - n_steps - n_pred + 1):
    X.append(series[i:i + n_steps])
    y.append(series[i + n_steps:i + n_steps + n_pred])  # 全通道未来真值（日历已知）
X = np.asarray(X)
y = np.asarray(y)
print(f"样本: {X.shape}")

# ---- 时间切分：最后 ~30 天作验证（预测已知未来），其余训练 ----
n_val = 30 * 24
cut = len(series) - n_steps - n_val
if cut < len(X) * 0.3:
    cut = int(len(X) * 0.7)
tr_X, tr_y = X[:cut], y[:cut]
va_X, va_y = X[cut:], y[cut:]
print(f"train={len(tr_X)} val={len(va_X)}")

model = TimeMixerPP(
    n_steps=n_steps, n_features=N_CH, n_pred_steps=n_pred, n_pred_features=N_CH,
    term="short", n_layers=2, d_model=48, d_ffn=96, top_k=5,
    n_heads=2, n_kernels=3, dropout=0.05,
    downsampling_window=2, downsampling_layers=1,
    channel_mixing=True, channel_independence=True, use_norm=True,
    batch_size=128, epochs=40, patience=6, num_workers=0,
    device=DEVICE, saving_path=None, model_saving_strategy=None, verbose=True,
)
model.fit({"X": tr_X, "X_pred": tr_y}, val_set={"X": va_X, "X_pred": va_y})

results = model.predict({"X": va_X, "X_pred": va_y})
pred = np.asarray(results["forecasting"])[:, :, 0].reshape(len(va_X), n_pred)  # 现货价通道
mae = float(np.mean(np.abs(pred - va_y[:, :, 0])))
rmse = float(np.sqrt(np.mean((pred - va_y[:, :, 0]) ** 2)))
print(f"\nTimeMixer++(含日历特征) 验证 MAE = {mae:.2f} 元/MWh | RMSE = {rmse:.2f}")

# ---- 预测最后一段（数据末端之后 24h；现货未知填 NaN，日历通道已知）----
last_X = series[-n_steps:].reshape(1, n_steps, N_CH)
fut_cal = np.array([calendar_feats(tss[-1] + __import__('datetime').timedelta(hours=k))
                    for k in range(1, n_pred + 1)]).reshape(1, n_pred, N_CH - 1)
fut = np.full((1, n_pred, N_CH), np.nan)
fut[:, :, 1:] = fut_cal
res2 = model.predict({"X": last_X, "X_pred": fut})
fc = np.asarray(res2["forecasting"])[0, :, 0]
print(f"未来24h预测(元/MWh): {[round(float(v),1) for v in fc[:8]]} ...")
print(f"参考: 当前 HGB 模型验证 MAE ≈ 36~40 元/MWh")
