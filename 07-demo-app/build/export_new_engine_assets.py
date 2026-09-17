"""
離線建置「導入新引擎」功能需要的資產，並評估模型換到其他工況時的表現。

=== 背景 ===
模型以 NASA CMAPSS FD001（1 種運轉條件、1 種失效模式）訓練。使用者問「導入新引擎也能判讀嗎」，
因此用同系列、附真實答案的 FD002 / FD003 / FD004 實測：
  - 直接換過去時，模型幾乎把快故障的引擎都判成 Healthy（FD004 只抓到 6/82 台）
  - 但「這筆讀數離訓練資料多遠」量得出來，可作為適用範圍檢查

=== 適用範圍檢查 ===
門檻 = FD001 測試集全部讀數「到最近 support 點距離」的第 99 百分位（事先依訓練工況訂定）。
超出門檻時：
  - 模型判 Warning → 照樣顯示 Warning
  - 模型判 Healthy → 不宣告健康，改為「無法確認」
不對稱規則的依據（四組資料、最後一筆讀數、超出門檻者）：
  判 Warning 17 台全部真的快故障；判 Healthy 495 台中 163 台其實快故障。
⚠️ 此規則是看過這四組資料的結果後歸納的，屬事後觀察；Warning 側樣本僅 17 台。

=== 評估協定（比照 FD001 的 85%）===
每台引擎取 test 檔最後一個 cycle；真實標籤以該資料集 RUL 檔的 33% 分位數為界。

=== 輸出（07-demo-app/assets/）===
  generalization.json          門檻、四組資料評估結果、適用範圍檢查分析
  demo_fleets/FD003_demo.csv   示範新機隊（同工況、多一種失效模式）
  demo_fleets/FD002_demo.csv   示範新機隊（六種運轉條件）
  demo_fleets/answers.json     示範機隊的真實剩餘壽命（僅供驗證展示）

執行：py -3 07-demo-app/build/export_new_engine_assets.py
需要：本機 NASA 原始資料（kaggle 專案/nasa專案/）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
from core.model import VaeDetector  # noqa: E402
from core.new_engine import SENSOR_COLS, assess_readings  # noqa: E402

NASA = Path(r"C:\Users\User\Desktop\kaggle 專案\nasa專案")
ASSETS = APP / "assets"
DEMO = ASSETS / "demo_fleets"
COLS = ["unit", "cycle", "setting_1", "setting_2", "setting_3"] + SENSOR_COLS
QUANTILE = 0.33
DEMO_SEED, DEMO_PER_CLASS = 7, 4

INFO = {
    "FD001": {"conditions": 1, "fault_modes": 1, "note": "訓練資料的工況"},
    "FD003": {"conditions": 1, "fault_modes": 2, "note": "同工況，多一種失效模式：風扇衰退"},
    "FD002": {"conditions": 6, "fault_modes": 1, "note": "六種運轉條件"},
    "FD004": {"conditions": 6, "fault_modes": 2, "note": "六種運轉條件、兩種失效模式"},
}


def load(name: str) -> tuple[pd.DataFrame, np.ndarray]:
    test = pd.read_csv(NASA / f"test_{name}.txt", sep=r"\s+", header=None, names=COLS)
    rul = np.loadtxt(NASA / f"RUL_{name}.txt")
    return test, rul


def main() -> None:
    det = VaeDetector()
    DEMO.mkdir(parents=True, exist_ok=True)

    # ---------- 1. 門檻 ----------
    fd001, _ = load("FD001")
    _, _, d001 = det.classify_batch(fd001[SENSOR_COLS].values.astype(np.float64))
    threshold = float(np.percentile(d001, 99))
    print(f"適用範圍門檻（FD001 測試集最近距離第 99 百分位）= {threshold:.4f}")

    # ---------- 2. 四組資料評估 ----------
    datasets, pooled = [], {"out_warning": 0, "out_warning_true": 0, "out_healthy": 0, "out_healthy_true": 0}
    for name in ["FD001", "FD003", "FD002", "FD004"]:
        test, rul = load(name)
        cut = float(np.quantile(rul, QUANTILE))

        readings = assess_readings(det, test, threshold)
        last = readings.groupby("unit").tail(1).sort_values("unit")
        truth = np.where(rul > cut, "Healthy", "Warning")
        raw, guarded, out = last["raw_status"].values, last["status"].values, ~last["in_range"].values

        tp = int(((truth == "Warning") & (raw == "Warning")).sum())
        fn = int(((truth == "Warning") & (raw == "Healthy")).sum())
        fp = int(((truth == "Healthy") & (raw == "Warning")).sum())

        # 加上適用範圍檢查後：真實快故障的引擎，被「錯誤宣告為 Healthy」的有幾台
        falsely_healthy_guarded = int(((truth == "Warning") & (guarded == "Healthy")).sum())

        row = {
            "name": name, **INFO[name],
            "engines": int(len(last)), "readings": int(len(readings)),
            "truth_cut_rul": cut,
            "accuracy": float((truth == raw).mean()),
            "warning_precision": tp / (tp + fp) if tp + fp else None,
            "warning_recall": tp / (tp + fn) if tp + fn else None,
            "true_warning": tp + fn, "caught": tp, "missed": fn, "false_alarms": fp,
            "predicted_warning_share": float((raw == "Warning").mean()),
            "readings_out_of_range_share": float((~readings["in_range"]).mean()),
            "last_out_of_range": int(out.sum()),
            "missed_flagged_out_of_range": int((out & (truth == "Warning") & (raw == "Healthy")).sum()),
            "guarded_unknown": int((guarded == "Unknown").sum()),
            "guarded_falsely_healthy": falsely_healthy_guarded,
        }
        datasets.append(row)

        pooled["out_warning"] += int((out & (raw == "Warning")).sum())
        pooled["out_warning_true"] += int((out & (raw == "Warning") & (truth == "Warning")).sum())
        pooled["out_healthy"] += int((out & (raw == "Healthy")).sum())
        pooled["out_healthy_true"] += int((out & (raw == "Healthy") & (truth == "Warning")).sum())

        print(f"{name}: acc {row['accuracy']:.1%}｜快故障抓到 {tp}/{tp + fn}｜"
              f"最後一筆超出範圍 {row['last_out_of_range']}/{row['engines']}｜"
              f"漏判中被標為超出範圍 {row['missed_flagged_out_of_range']}/{fn}｜"
              f"加檢查後仍被誤判健康 {falsely_healthy_guarded}/{tp + fn}")

    # FD002 各運轉條件的範圍內比例（證明檢查抓到的是工況差異）
    fd002, _ = load("FD002")
    r002 = assess_readings(det, fd002, threshold)
    cond = (fd002["setting_1"].round(0).astype(int).astype(str) + "k ft / Mach "
            + fd002["setting_2"].round(2).astype(str) + " / TRA "
            + fd002["setting_3"].round(0).astype(int).astype(str))
    by_cond = (r002.assign(cond=cond.values).groupby("cond")["in_range"].agg(["size", "mean"])
               .reset_index().rename(columns={"size": "readings", "mean": "in_range_share"}))
    by_cond = by_cond.sort_values("in_range_share", ascending=False)

    out = {
        "threshold": threshold,
        "threshold_definition": "FD001 測試集全部 13,096 筆讀數到最近 support 點距離的第 99 百分位",
        "datasets": datasets,
        "pooled_out_of_range_last_reading": pooled,
        "fd002_by_condition": by_cond.to_dict(orient="records"),
        "caveats": [
            "距離門檻依 FD001（訓練工況）事先訂定",
            "「超出範圍時 Warning 可信、Healthy 不可信」是看過 FD001–FD004 結果後歸納的，屬事後觀察",
            f"超出範圍且判 Warning 的樣本僅 {pooled['out_warning']} 台",
        ],
    }
    (ASSETS / "generalization.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n超出範圍的最後一筆：判 Warning {pooled['out_warning']} 台（真快故障 {pooled['out_warning_true']}）｜"
          f"判 Healthy {pooled['out_healthy']} 台（真快故障 {pooled['out_healthy_true']}）")

    # ---------- 3. 示範機隊（分層抽樣，不挑選）----------
    answers = {}
    rng = np.random.default_rng(DEMO_SEED)
    for name in ["FD003", "FD002"]:
        test, rul = load(name)
        cut = float(np.quantile(rul, QUANTILE))
        units = np.sort(test["unit"].unique())
        truth = pd.Series(np.where(rul > cut, "Healthy", "Warning"), index=units)
        picked = np.sort(np.concatenate([
            rng.choice(truth[truth == "Warning"].index.values, DEMO_PER_CLASS, replace=False),
            rng.choice(truth[truth == "Healthy"].index.values, DEMO_PER_CLASS, replace=False),
        ]))
        demo = test[test["unit"].isin(picked)].copy()
        # 重新編號成 NEW-01…，避免與 FD001 的 ENG-xxx 混淆
        remap = {u: i + 1 for i, u in enumerate(picked)}
        demo["unit"] = demo["unit"].map(remap)
        demo.to_csv(DEMO / f"{name}_demo.csv", index=False)
        answers[name] = {
            "truth_cut_rul": cut,
            "source_units": {str(remap[u]): int(u) for u in picked},
            "true_rul": {str(remap[u]): float(rul[u - 1]) for u in picked},
            "true_label": {str(remap[u]): truth[u] for u in picked},
        }
        size = (DEMO / f"{name}_demo.csv").stat().st_size / 1024
        print(f"示範機隊 {name}：原始引擎 {list(picked)} → NEW-01…NEW-{len(picked):02d}，"
              f"{len(demo):,} 筆讀數，{size:.0f} KB")

    (DEMO / "answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
