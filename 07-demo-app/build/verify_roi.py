"""
回歸測試：效益計算必須與 roi-validation.xlsx 及專案歷史數字一致。

  [A] 預設值讀自 roi-validation.xlsx，算出校準版結果：年省約 120 小時、ROI 約 200%、回本約 80 工作天
  [B] 以舊版樂觀假設（3 人 × 每天 3 次）重算，須重現當初的 539 小時 / ROI 1,248%
  [C] value-driver：取整 96% / 81% → 84.0% / 36.7%；未取整 96.43% / 80.60% → 85.7% / 35.3%
  [D] Healthy 類 precision / recall 由 model_validation.csv 混淆矩陣重算

執行：py -3 07-demo-app/build/verify_roi.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
from core.roi import compute, error_reduction, load_defaults  # noqa: E402

failures: list[str] = []


def check(name: str, got: float, want: float, tol: float, fmt: str = "{:.4g}") -> None:
    ok = abs(got - want) <= tol
    print(f"  {'✅' if ok else '❌'} {name}：{fmt.format(got)}（期望 {fmt.format(want)}）")
    if not ok:
        failures.append(name)


def main() -> int:
    d = load_defaults()
    print(f"[A] 預設值（讀自 roi-validation.xlsx）：{d}")
    r = compute(d)
    check("單次省時（秒）", r.saved_s, 898.4, 1e-9)
    check("年省工時", r.annual_hours, 119.787, 0.001, "{:.3f}")
    check("年省成本 NT$", r.annual_ntd, 59893.3, 1, "{:,.1f}")
    check("導入成本 NT$", r.cost_ntd, 20000, 1e-9, "{:,.0f}")
    check("回本工作天", r.payback_days, 80.1, 0.05, "{:.1f}")
    check("首年 ROI", r.roi, 1.9947, 0.001, "{:.2%}")

    print("\n[B] 舊版樂觀假設（3 人 × 每天 3 次）")
    old = compute(d.with_(people=3, runs_per_day=3))
    check("年省工時", old.annual_hours, 539.04, 0.01, "{:.1f}")
    check("首年 ROI", old.roi, 12.476, 0.001, "{:.0%}")

    print("\n[C] value-driver 降幅")
    check("維護成本（取整 96% vs 75%）", error_reduction(0.75, 0.96), 0.84, 1e-9, "{:.1%}")
    check("停機（取整 81% vs 70%）", error_reduction(0.70, 0.81), 0.3667, 1e-4, "{:.1%}")
    check("維護成本（未取整 54/56）", error_reduction(0.75, 54 / 56), 0.8571, 1e-4, "{:.1%}")
    check("停機（未取整 54/67）", error_reduction(0.70, 54 / 67), 0.3532, 1e-4, "{:.1%}")

    print("\n[D] Healthy 類指標由混淆矩陣重算")
    v = pd.read_csv(APP.parent / "01-core-model" / "outputs" / "model_validation.csv", encoding="utf-8-sig")
    hh = int(((v.TrueLabel == "Healthy") & (v.PredictedStatus == "Healthy")).sum())
    pred_h = int((v.PredictedStatus == "Healthy").sum())
    true_h = int((v.TrueLabel == "Healthy").sum())
    check(f"Precision(Healthy) = {hh}/{pred_h}", hh / pred_h, 0.9643, 1e-4, "{:.4f}")
    check(f"Recall(Healthy) = {hh}/{true_h}", hh / true_h, 0.8060, 1e-4, "{:.4f}")

    print("\n" + ("✅ 全部通過" if not failures else f"❌ {len(failures)} 項失敗：{failures}"))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
