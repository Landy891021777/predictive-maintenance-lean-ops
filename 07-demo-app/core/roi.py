"""
效益計算。公式與 06-lean-lss/build_roi.py 產生的 roi-validation.xlsx 完全相同，
預設值也直接從那份試算表讀取 —— 試算表是單一真相來源，網頁不另存一份數字。

=== 第二層：流程自動化 ROI（主角）===
  單次省時   = 手動耗時 − 自動耗時                              （🟢 兩者皆實測）
  年省工時   = 單次省時 × 每天次數 × 人數 × 年工作天 ÷ 3600      （🟡 後三者為假設）
  年省成本   = 年省工時 × 時薪
  導入成本   = 導入工時 × 時薪
  回本工作天 = 導入成本 ÷ (年省成本 ÷ 年工作天)
  首年 ROI   = (年省成本 − 導入成本) ÷ 導入成本

=== 第一層：設備健康效益（技術亮點，情境推估）===
value-driver：比較兩個模型的「錯誤比例」降幅
  漏判比例   = 1 − Precision(Healthy)   判為健康、其實在衰退   → 對應非計畫故障的維護成本
  過度維修   = 1 − Recall(Healthy)      其實健康、卻被叫去檢修 → 對應不必要的停機
  降幅       = (基準錯誤比例 − 本模型錯誤比例) ÷ 基準錯誤比例
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

ROI_XLSX = Path(__file__).resolve().parents[2] / "06-lean-lss" / "roi-validation.xlsx"

# roi-validation.xlsx 的輸入儲存格（見 build_roi.py）
_CELLS = {
    "manual_s": "B7", "auto_s": "B8", "runs_per_day": "B10", "people": "B11",
    "workdays": "B12", "hourly_ntd": "B14", "dev_hours": "B16",
}


@dataclass(frozen=True)
class RoiInputs:
    manual_s: float          # 🟢 碼錶實測
    auto_s: float            # 🟢 VBA Timer 實測
    runs_per_day: float      # 🟡
    people: float            # 🟡
    workdays: float          # 🟡
    hourly_ntd: float        # 🟡
    dev_hours: float         # 🟡

    def with_(self, **kw) -> "RoiInputs":
        return replace(self, **kw)


@dataclass(frozen=True)
class RoiResult:
    saved_s: float
    annual_hours: float
    annual_ntd: float
    cost_ntd: float
    payback_days: float
    net_first_year: float
    roi: float


def load_defaults(path: Path = ROI_XLSX) -> RoiInputs:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["ROI"]
    vals = {k: float(ws[c].value) for k, c in _CELLS.items()}
    wb.close()
    return RoiInputs(**vals)


def compute(i: RoiInputs) -> RoiResult:
    saved = i.manual_s - i.auto_s
    hours = saved * i.runs_per_day * i.people * i.workdays / 3600
    annual = hours * i.hourly_ntd
    cost = i.dev_hours * i.hourly_ntd
    payback = cost / (annual / i.workdays) if annual > 0 else float("inf")
    net = annual - cost
    roi = net / cost if cost > 0 else float("inf")
    return RoiResult(saved, hours, annual, cost, payback, net, roi)


def error_reduction(baseline_metric: float, model_metric: float) -> float:
    """value-driver 降幅：錯誤比例（1 − 指標）從基準降到本模型，降了幾成。"""
    base_err, model_err = 1 - baseline_metric, 1 - model_metric
    return (base_err - model_err) / base_err
