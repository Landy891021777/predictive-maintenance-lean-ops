"""
回歸測試：導入新引擎功能。不需要 API 金鑰，也不需要 NASA 原始資料（只用 repo 內的資產）。

  [A] 上傳格式：NASA 原始格式、有表頭 CSV、sensor_1 欄名、省略 unit/cycle、分號分隔
  [B] 錯誤處理：空檔、缺欄、非數值、欄數不對，都要回傳可讀的 UploadError 而不是崩潰
  [C] 不變量：超出適用範圍的讀數，最終狀態永遠不會是 Healthy
  [D] 示範機隊：可正常解析，且答案檔與資料的引擎一一對應
  [E] 範圍內的 FD001 讀數：檢查不改變原本的判讀（只影響超出範圍者）

執行：py -3 07-demo-app/build/verify_new_engine.py
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
from core.new_engine import (  # noqa: E402
    SENSOR_COLS, UploadError, assess_readings, guard, parse_upload, summarise_engines,
)

ASSETS = APP / "assets"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {name}" + (f"｜{detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    det = VaeDetector()
    gen = json.loads((ASSETS / "generalization.json").read_text(encoding="utf-8"))
    thr = gen["threshold"]

    r = np.load(ASSETS / "test_readings.npz")
    base = pd.DataFrame(r["sensors"], columns=SENSOR_COLS)
    base.insert(0, "cycle", r["cycle"].astype(int))
    base.insert(0, "unit", r["unit"].astype(int))
    sample = base[base["unit"].isin([1, 2])].reset_index(drop=True)

    print("[A] 上傳格式")
    nasa_txt = "\n".join(
        " ".join([str(u), str(c), "0.0", "0.0", "100.0"] + [f"{v:.4f}" for v in row])
        for u, c, row in zip(sample["unit"], sample["cycle"], sample[SENSOR_COLS].values)
    ).encode()
    df = parse_upload(nasa_txt)
    check("NASA 原始格式（26 欄、無表頭）", len(df) == len(sample) and df["unit"].nunique() == 2, f"{len(df)} 列")

    df = parse_upload(sample.to_csv(index=False).encode())
    check("有表頭 CSV（s_1…s_21）", len(df) == len(sample))

    alt_cols = sample[SENSOR_COLS].rename(columns=lambda c: "Sensor_" + c[2:])
    df = parse_upload(alt_cols.to_csv(index=False).encode())
    check("sensor_1 欄名、省略 unit 與 cycle", len(df) == len(sample) and df["unit"].nunique() == 1
          and df["cycle"].tolist() == list(range(1, len(sample) + 1)))

    df = parse_upload(sample.to_csv(index=False, sep=";").encode())
    check("分號分隔", len(df) == len(sample))

    print("\n[B] 錯誤處理")
    bad_inputs = {
        "空檔": b"",
        "缺感測器欄位": sample.drop(columns=["s_5", "s_9"]).to_csv(index=False).encode(),
        "含非數值": sample.astype({"s_3": str}).assign(s_3=lambda d: d["s_3"].where(d.index != 3, "N/A"))
                      .to_csv(index=False).encode(),
        "無表頭但欄數不對": b"1 1 0 0 100 " + b" ".join([b"1.0"] * 20),
        "非 UTF-8": "機台".encode("big5"),
    }
    for name, payload in bad_inputs.items():
        try:
            parse_upload(payload)
            check(name, False, "應該要報錯卻通過")
        except UploadError as e:
            check(name, True, str(e)[:40])
        except Exception as e:
            check(name, False, f"崩潰：{type(e).__name__}")

    print("\n[C] 不變量：超出範圍永不回報 Healthy")
    raw = np.array(["Healthy", "Warning", "Healthy", "Warning"])
    dist = np.array([thr * 0.5, thr * 0.5, thr * 2, thr * 2])
    status, in_range = guard(raw, dist, thr)
    check("guard 四種組合", status.tolist() == ["Healthy", "Warning", "Unknown", "Warning"], str(status.tolist()))

    for fleet in ["FD003", "FD002"]:
        df = parse_upload((ASSETS / "demo_fleets" / f"{fleet}_demo.csv").read_bytes())
        res = assess_readings(det, df, thr)
        leaked = int(((~res["in_range"]) & (res["status"] == "Healthy")).sum())
        check(f"{fleet} 示範機隊 {len(res):,} 筆", leaked == 0, f"超出範圍卻回報 Healthy：{leaked} 筆")

    print("\n[D] 示範機隊與答案檔")
    answers = json.loads((ASSETS / "demo_fleets" / "answers.json").read_text(encoding="utf-8"))
    for fleet in ["FD003", "FD002"]:
        df = parse_upload((ASSETS / "demo_fleets" / f"{fleet}_demo.csv").read_bytes())
        summary = summarise_engines(assess_readings(det, df, thr))
        units = sorted(summary["unit"], key=int)
        check(f"{fleet} 引擎與答案一一對應", units == sorted(answers[fleet]["true_rul"], key=int),
              f"{len(units)} 台，快故障 {sum(v == 'Warning' for v in answers[fleet]['true_label'].values())} 台")

    print("\n[E] FD001 範圍內讀數不受影響")
    res = assess_readings(det, base, thr)
    changed = int((res["in_range"] & (res["status"] != res["raw_status"])).sum())
    out_share = float((~res["in_range"]).mean())
    check("範圍內判讀未被改動", changed == 0, f"FD001 超出範圍比例 {out_share:.1%}（門檻為第 99 百分位，應約 1%）")

    print("\n" + ("✅ 全部通過" if not failures else f"❌ {len(failures)} 項失敗：{failures}"))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
