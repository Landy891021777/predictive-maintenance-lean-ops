"""
驗證：線上要跑的那條純 NumPy 推論路徑，必須重現 model_validation.md 的實測結果。

這支腳本不碰 PyTorch，只用 07-demo-app/assets/ 裡的資產，走 core/model.py，
對 test_FD001 每台引擎的最後一個 cycle 做判讀，然後和 RUL_FD001 的真實答案比對。

期望值（來自 01-core-model/outputs/model_validation.md，實測）：
    Accuracy = 0.8500
    混淆矩陣 = [[54, 13],   實際 Healthy → 預測 Healthy / Warning
                [ 2, 31]]   實際 Warning → 預測 Healthy / Warning

對不上就 exit 非 0，代表 app 會顯示與驗證報告不同的結果，不可上線。

執行：py -3 07-demo-app/build/verify_numpy_path.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.model import VaeDetector  # noqa: E402

NASA_DIR = Path(r"C:\Users\User\Desktop\kaggle 專案\nasa專案")
ASSETS = Path(__file__).resolve().parent.parent / "assets"

EXPECTED_ACC = 0.85
EXPECTED_CM = np.array([[54, 13], [2, 31]])
SUPPORT_QUANTILE = 0.33


def main() -> int:
    det = VaeDetector()

    r = np.load(ASSETS / "test_readings.npz")
    unit, cycle, sensors = r["unit"], r["cycle"], r["sensors"]

    # 每台引擎的最後一個 cycle（CMAPSS 標準評估法：RUL_FD001 只給那一點的答案）
    order = np.lexsort((cycle, unit))
    unit_s, cycle_s, sensors_s = unit[order], cycle[order], sensors[order]
    last_idx = np.searchsorted(unit_s, np.unique(unit_s), side="right") - 1
    X_last = sensors_s[last_idx]

    status, _, _ = det.classify_batch(X_last)

    rul_true = np.loadtxt(NASA_DIR / "RUL_FD001.txt")
    test_cut = float(np.quantile(rul_true, SUPPORT_QUANTILE))
    truth = np.where(rul_true > test_cut, "Healthy", "Warning")

    acc = float((status == truth).mean())
    cm = np.array([
        [int(((truth == "Healthy") & (status == "Healthy")).sum()),
         int(((truth == "Healthy") & (status == "Warning")).sum())],
        [int(((truth == "Warning") & (status == "Healthy")).sum()),
         int(((truth == "Warning") & (status == "Warning")).sum())],
    ])

    print(f"引擎數            {len(X_last)}")
    print(f"真實標籤分界 RUL  {test_cut:.1f}")
    print(f"Accuracy          {acc:.4f}  (期望 {EXPECTED_ACC:.4f})")
    print("混淆矩陣          預測H  預測W")
    print(f"  實際 Healthy      {cm[0,0]:4d}  {cm[0,1]:4d}")
    print(f"  實際 Warning      {cm[1,0]:4d}  {cm[1,1]:4d}")

    warning_recall = cm[1, 1] / cm[1].sum()
    warning_precision = cm[1, 1] / cm[:, 1].sum()
    healthy_precision = cm[0, 0] / cm[:, 0].sum()
    healthy_recall = cm[0, 0] / cm[0].sum()
    print(f"\nWarning  precision {warning_precision:.4f}  recall {warning_recall:.4f}")
    print(f"Healthy  precision {healthy_precision:.4f}  recall {healthy_recall:.4f}")

    ok = abs(acc - EXPECTED_ACC) < 1e-9 and np.array_equal(cm, EXPECTED_CM)
    print("\n" + ("✅ [A] 與 model_validation.md 完全一致"
                  if ok else "❌ [A] 與驗證報告不一致，不可上線"))

    # ---------- [B] 全量逐筆比對 model_predictions.csv ----------
    import pandas as pd

    csv_path = (Path(__file__).resolve().parents[2]
                / "01-core-model" / "outputs" / "model_predictions.csv")
    stored = pd.read_csv(csv_path, encoding="utf-8-sig")

    status_all, mu_all, dist_all = det.classify_batch(sensors)
    same_status = int((status_all == stored["PredictedStatus"].values).sum())
    z1_diff = float(np.abs(mu_all[:, 0] - stored["LatentZ1"].values).max())
    z2_diff = float(np.abs(mu_all[:, 1] - stored["LatentZ2"].values).max())
    d_diff = float(np.abs(dist_all - stored["NearestDistance"].values).max())

    print(f"\n[B] 全量逐筆比對（{len(stored):,} 筆）")
    print(f"    判讀一致          {same_status:,}/{len(stored):,}")
    print(f"    LatentZ1 最大誤差 {z1_diff:.2e}   LatentZ2 {z2_diff:.2e}")
    print(f"    最近距離最大誤差  {d_diff:.2e}（僅供參考，見下方說明）")

    # 判讀與潛空間座標必須一致；「最近距離」則刻意不設嚴格門檻。
    #
    # 原因：support set 的 embedding 在這裡由 NumPy 重算，與當初 score_engines.py 用
    # PyTorch 算出的版本每個座標差約 7e-7。健康樣本在潛空間中極為密集，一筆讀數到最近
    # 點的距離常只有 0.001–0.004，此時 14,441 個點中有大量點幾乎等距，7e-7 的擾動就足以
    # 讓「最近的是哪一個點」換人。換到的點標籤相同，所以判讀不受影響，但回報的距離會差
    # 到 1e-4 量級。（已確認本檔的距離計算與 torch.cdist 的精確模式
    # compute_mode="donot_use_mm_for_euclid_dist" 完全一致。）
    ok_b = same_status == len(stored) and max(z1_diff, z2_diff) < 1e-5
    print("✅ [B] 判讀與潛空間座標與 model_predictions.csv 逐筆一致"
          if ok_b else "❌ [B] 與既有預測檔不一致")

    return 0 if (ok and ok_b) else 1


if __name__ == "__main__":
    raise SystemExit(main())
