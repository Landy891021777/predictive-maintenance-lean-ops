"""
產生 AI 助理（RAG）用的文件庫。

=== 誠信設計 ===
六類文件分兩種性質，每個片段都帶標記，網頁上一律顯示：

  🟢 measured   專案真實文件與實測結果（模型卡、精實改善與效益）
                以最終數字重新整理；原始草稿 DMAIC.md / value-stream-map.md
                含架構調整前的過期數字，不直接收錄
  🟡 simulated  模擬的現場文件（維修手冊、處置 SOP、維修工單、交接紀錄）
                CMAPSS 沒有這類文件，因此是模擬的；但文件中出現的所有
                引擎編號、cycle、判讀結果、感測器範圍，全部從真實資料計算

模擬文件刻意不使用真實剩餘壽命（RUL）—— 現場文件不可能知道答案。
真實 RUL 只出現在模型卡的評估段落。

資料相關的數字（感測器範圍、引擎事件、評估指標、清理統計、耗時）都由本腳本從資料即時算出；
模型架構（21→64→2）與資料集規模等固定事實則直接寫入。

輸出：07-demo-app/assets/corpus/
  chunks.json   檢索用片段（id / 文件 / 章節 / 性質 / 內文 / 來源 / 涉及引擎）
  docs/*.md     每份文件的完整可讀版（網頁文件瀏覽與 GitHub 閱讀用）

執行：py -3 07-demo-app/build/build_corpus.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

APP = Path(__file__).resolve().parent.parent
REPO = APP.parent
sys.path.insert(0, str(APP))
from core.cleaning import naive_pivot, run_pipeline  # noqa: E402

NASA_DIR = Path(r"C:\Users\User\Desktop\kaggle 專案\nasa專案")
OUT = APP / "assets" / "corpus"
OUTPUTS = REPO / "01-core-model" / "outputs"
LIFECYCLE = REPO / "02-automation-vba" / "sample-data" / "lifecycle"

MEASURED, SIMULATED = "measured", "simulated"

# SOP 分級門檻（事先訂定，未針對測試資料調整）
WINDOW = 10
L2_MIN, L3_MIN = 3, 7

# 感測器名稱與單位：NASA CMAPSS 公開文件（Saxena et al., 2008）
SENSORS = {
    1: ("T2", "風扇入口總溫", "°R"),
    2: ("T24", "低壓壓縮機（LPC）出口總溫", "°R"),
    3: ("T30", "高壓壓縮機（HPC）出口總溫", "°R"),
    4: ("T50", "低壓渦輪（LPT）出口總溫", "°R"),
    5: ("P2", "風扇入口壓力", "psia"),
    6: ("P15", "旁通道總壓", "psia"),
    7: ("P30", "高壓壓縮機出口總壓", "psia"),
    8: ("Nf", "風扇實際轉速", "rpm"),
    9: ("Nc", "核心實際轉速", "rpm"),
    10: ("epr", "引擎壓力比（P50/P2）", "—"),
    11: ("Ps30", "高壓壓縮機出口靜壓", "psia"),
    12: ("phi", "燃油流量與 Ps30 之比", "pps/psi"),
    13: ("NRf", "修正風扇轉速", "rpm"),
    14: ("NRc", "修正核心轉速", "rpm"),
    15: ("BPR", "旁通比", "—"),
    16: ("farB", "燃燒室油氣比", "—"),
    17: ("htBleed", "引氣焓值", "—"),
    18: ("Nf_dmd", "需求風扇轉速", "rpm"),
    19: ("PCNfR_dmd", "需求修正風扇轉速", "rpm"),
    20: ("W31", "高壓渦輪冷卻引氣流量", "lbm/s"),
    21: ("W32", "低壓渦輪冷卻引氣流量", "lbm/s"),
}

SENSOR_GROUPS = [
    ("2.1", "溫度類感測器", [2, 3, 4]),
    ("2.2", "壓力類感測器", [6, 7, 11]),
    ("2.3", "轉速類感測器", [8, 9, 13, 14]),
    ("2.4", "流量與比值類感測器", [12, 15, 17, 20, 21]),
]

CHUNKS: list[dict] = []


def add(doc: str, doc_title: str, section: str, kind: str, text: str,
        source: str, engines: list[str] | None = None) -> None:
    n = sum(1 for c in CHUNKS if c["doc"] == doc) + 1
    CHUNKS.append({
        "id": f"{doc}-{n:02d}",
        "doc": doc,
        "doc_title": doc_title,
        "section": section,
        "kind": kind,
        "text": text.strip(),
        "source": source,
        "engines": sorted(set(engines or [])),
    })


def eng(u: int) -> str:
    return f"ENG-{int(u):03d}"


# ===========================================================================
# 資料準備
# ===========================================================================

def load_facts() -> dict:
    cols = ["unit", "cycle", "set1", "set2", "set3"] + [f"s_{i}" for i in range(1, 22)]
    train = pd.read_csv(NASA_DIR / "train_FD001.txt", sep=r"\s+", header=None, names=cols)
    train["RUL"] = train.groupby("unit")["cycle"].transform("max") - train["cycle"]

    sensor = {}
    for i in range(1, 22):
        s = train[f"s_{i}"]
        const = s.std() < 1e-9
        sensor[i] = {
            "constant": bool(const),
            "p01": float(s.quantile(0.01)), "p50": float(s.median()),
            "p99": float(s.quantile(0.99)),
            "r": None if const else float(np.corrcoef(s, train["RUL"])[0, 1]),
        }

    preds = pd.read_csv(OUTPUTS / "model_predictions.csv", encoding="utf-8-sig")
    preds = preds.sort_values(["unit_number", "time_cycles"]).reset_index(drop=True)
    preds["W"] = (preds["PredictedStatus"] == "Warning").astype(int)
    preds["w_recent"] = (preds.groupby("unit_number")["W"]
                         .transform(lambda x: x.rolling(WINDOW, min_periods=1).sum()))

    g = preds.groupby("unit_number")
    traj = pd.DataFrame({
        "last_cycle": g["time_cycles"].max(),
        "n_readings": g.size(),
        "n_warning": g["W"].sum(),
        "first_warning": preds[preds.W == 1].groupby("unit_number")["time_cycles"].min(),
        "l2_cycle": preds[preds.w_recent >= L2_MIN].groupby("unit_number")["time_cycles"].min(),
        "l3_cycle": preds[preds.w_recent >= L3_MIN].groupby("unit_number")["time_cycles"].min(),
        "last_status": g["PredictedStatus"].last(),
        "last_distance": g["NearestDistance"].last(),
    })

    # cycle → 匯出日期（與自動化頁使用的同一份模擬 SAP 匯出檔）
    clean = run_pipeline(LIFECYCLE).clean
    clean["unit"] = clean["EquipmentID"].str[4:].astype(int)
    date_of = {(int(u), int(c)): d.isoformat()
               for u, c, d in zip(clean["unit"], clean["Cycle"], clean["ExportDate"])}

    validation = pd.read_csv(OUTPUTS / "model_validation.csv", encoding="utf-8-sig")
    meta = json.loads((APP / "assets" / "meta.json").read_text(encoding="utf-8"))
    runlog = run_pipeline(LIFECYCLE).log
    naive = naive_pivot(LIFECYCLE)
    import openpyxl
    wb = openpyxl.load_workbook(REPO / "03-rpa-power-automate" / "outbox" / "DailyHealthReport_20260711.xlsm",
                                read_only=True, data_only=True)
    rpa = {k: val for k, val in wb["Summary"].iter_rows(min_row=2, max_row=10, max_col=2, values_only=True) if k}
    wb.close()

    return dict(sensor=sensor, preds=preds, traj=traj, date_of=date_of,
                validation=validation, meta=meta, runlog=runlog, naive=naive,
                rpa_seconds=float(rpa["Elapsed seconds"]))


# ===========================================================================
# 🟡 文件一：維修手冊
# ===========================================================================

def build_manual(f: dict) -> None:
    doc, title = "manual", "渦扇引擎健康監測維修手冊（模擬）"
    src = "感測器名稱與單位依 NASA CMAPSS 公開文件；正常範圍與退化趨勢由 train_FD001 實際計算"

    add(doc, title, "1. 適用範圍與使用說明", SIMULATED, f"""
本手冊適用於本機隊 100 台渦扇引擎（ENG-001 至 ENG-100）的健康監測與維修作業。
機隊運轉條件為單一飛行條件（海平面），主要失效模式為高壓壓縮機（HPC）性能衰退，
對應 NASA CMAPSS FD001 資料集的設定。

每台引擎每個運轉週期（cycle）回傳一筆讀數，共 21 個感測器。其中 {sum(v['constant'] for v in f['sensor'].values())} 個感測器在本機隊全程為定值、不具監測價值，
其餘感測器的正常範圍與退化趨勢見第 2 章。健康狀態由 VAE 模型自動判讀（見第 3 章），
判為 Warning 時依《異常處置 SOP》分級處理。
""", "本手冊為模擬文件；運轉條件與失效模式依 CMAPSS FD001 資料集說明")

    for sec, name, ids in SENSOR_GROUPS:
        lines = []
        for i in ids:
            code, cn, unit = SENSORS[i]
            s = f["sensor"][i]
            r = s["r"]
            if abs(r) < 0.2:
                trend = "與退化程度幾乎無關，僅作輔助參考"
            else:
                strength = "明顯" if abs(r) >= 0.6 else "中度"
                direction = "上升" if r < 0 else "下降"
                trend = f"引擎越接近故障，讀數{strength}{direction}（與剩餘壽命相關係數 {r:+.2f}）"
            lines.append(
                f"- Sensor {i}（{code}，{cn}，單位 {unit}）：正常範圍 {s['p01']:.4g} – {s['p99']:.4g}"
                f"（中位數 {s['p50']:.4g}）；{trend}。"
            )
        add(doc, title, f"{sec} {name}", SIMULATED,
            f"本節列出{name}的定義、正常範圍與退化趨勢。\n" + "\n".join(lines), src)

    consts = [i for i, s in f["sensor"].items() if s["constant"]]
    add(doc, title, "2.5 不具監測價值的定值感測器", SIMULATED,
        "以下感測器在本機隊全程為定值，無法反映健康變化，巡檢時不需判讀：\n" +
        "\n".join(f"- Sensor {i}（{SENSORS[i][0]}，{SENSORS[i][1]}）" for i in consts) +
        "\n模型輸入仍包含這些欄位以維持 21 維格式，但它們對判讀沒有貢獻。", src)

    strong = sorted((i for i, s in f["sensor"].items() if s["r"] is not None and abs(s["r"]) >= 0.6),
                    key=lambda i: -abs(f["sensor"][i]["r"]))
    add(doc, title, "2.6 高壓壓縮機衰退的典型徵兆", SIMULATED,
        "高壓壓縮機（HPC）性能衰退時，最具代表性的感測器變化（依與剩餘壽命的相關程度排序）：\n" +
        "\n".join(
            f"- Sensor {i}（{SENSORS[i][0]}，{SENSORS[i][1]}）"
            f"{'上升' if f['sensor'][i]['r'] < 0 else '下降'}（r = {f['sensor'][i]['r']:+.2f}）"
            for i in strong) +
        "\n單一感測器偏離正常範圍不一定代表故障；應以模型綜合判讀與連續讀數趨勢為準。", src)

    m = f["meta"]
    add(doc, title, "3. 健康狀態自動判讀原理", SIMULATED, f"""
每筆讀數由 VAE（變分自編碼器）模型自動判讀為 Healthy 或 Warning：
1. 21 個感測值經 MinMaxScaler 正規化
2. VAE encoder 將讀數壓縮為 2 維潛空間座標
3. 在 {m['support_size']:,} 筆歷史訓練讀數中找出潛空間距離最近的一筆（1-NN）
4. 若該筆歷史讀數當時的剩餘壽命 ≤ {m['support_cut_rul']:.0f} cycles，判為 Warning，否則為 Healthy

「最近距離」越大，代表這筆讀數越不像任何已知的歷史讀數，可作為判讀信心的參考。
模型特性是偏向寧可誤報、不要漏判，因此 Warning 需經覆核（見《異常處置 SOP》）。
""", "判讀規則與 01-core-model/scoring/score_engines.py 相同；本手冊為模擬文件")

    add(doc, title, "4. 定期巡檢項目", SIMULATED, """
不論模型判讀結果為何，每台引擎仍需執行定期巡檢，以涵蓋模型可能漏判的情況：
- 每 50 cycles：目視檢查壓縮機葉片、確認感測器接線與讀值合理性
- 每 100 cycles：比對 Sensor 4、Sensor 11、Sensor 7 與正常範圍，記錄趨勢
- 任何 cycle 若有感測器讀值超出第 2 章正常範圍 25% 以上，視為感測器異常，先排除儀器問題再判讀健康狀態
巡檢結果記錄於交接班紀錄。
""", "巡檢週期與項目為模擬的作業規範")


# ===========================================================================
# 🟡 文件二：異常處置 SOP
# ===========================================================================

def build_sop(f: dict) -> None:
    doc, title = "sop", "異常處置標準作業程序（SOP，模擬）"
    t, v = f["traj"], f["validation"]

    add(doc, title, "1. 目的與分級原則", SIMULATED, f"""
本 SOP 規範模型判讀為 Warning 時的處置流程。分級不看單一讀數，而看**最近 {WINDOW} 筆讀數中的 Warning 筆數**，
理由是單筆讀數容易受雜訊影響，連續趨勢才能反映真實退化：
- L1 觀察：最近 {WINDOW} 筆中有 1–{L2_MIN - 1} 筆 Warning
- L2 排程檢查：最近 {WINDOW} 筆中有 {L2_MIN}–{L3_MIN - 1} 筆 Warning
- L3 停機檢查：最近 {WINDOW} 筆中有 {L3_MIN} 筆以上 Warning
""", "分級門檻為模擬 SOP 事先訂定，未針對資料調整")

    add(doc, title, "2. L1 觀察：處置步驟", SIMULATED, """
1. 於交接班紀錄登記引擎編號、cycle 與最近距離
2. 不開立工單，不影響運轉排程
3. 下一班次確認 Warning 是否持續；若升級至 L2 則依第 3 節處理
4. 若同一引擎 L1 反覆出現但始終未達 L2，於週會提出討論
""", "模擬的作業流程")

    add(doc, title, "3. L2 排程檢查：處置步驟", SIMULATED, """
1. 開立「排程檢查」工單，處置時限 72 小時內
2. 調閱該引擎最近 50 筆讀數，確認溫度類（Sensor 2/3/4）與壓力類（Sensor 7/11）是否呈退化趨勢
3. 覆核是否為誤報：模型偏向寧可誤報，L2 中有相當比例並非真正退化
4. 覆核確認退化 → 安排下一次停機窗口檢查高壓壓縮機；確認非退化 → 註記為誤報並結案
""", "模擬的作業流程")

    add(doc, title, "4. L3 停機檢查：處置步驟", SIMULATED, """
1. 立即通報維運主管，開立「停機檢查」工單，處置時限 24 小時內
2. 安排引擎退出運轉，執行高壓壓縮機內視鏡檢查
3. 檢查結果登錄於工單；更換零件或返修需主管簽核
4. 復機後前 20 cycles 列為加強監測，每班次回報判讀結果
""", "模擬的作業流程")

    n_l2, n_l3 = int(t["l2_cycle"].notna().sum()), int(t["l3_cycle"].notna().sum())
    add(doc, title, "5. 為什麼要看連續讀數：誤報與漏判的處理", SIMULATED, f"""
模型在單筆讀數上的特性是寧可誤報、不要漏判：以每台引擎最後一筆讀數評估，
Warning 的召回率 93.9%、精確率 70.5%（見模型卡）。因此：
- 誤報較多 → L2 必須人工覆核，不直接停機
- 仍有漏判 → 定期巡檢（維修手冊第 4 章）不可省略

在本機隊的判讀紀錄中，依本 SOP 分級：共 {n_l2} 台引擎曾觸發 L2、{n_l3} 台曾觸發 L3。
""", "觸發台數由 01-core-model/outputs/model_predictions.csv 依本 SOP 門檻實際計算")

    add(doc, title, "6. 通報與權責", SIMULATED, """
- L1：當班技術員記錄即可
- L2：當班技術員開立工單，維修工程師 72 小時內覆核
- L3：當班技術員立即通報維運主管，主管核准停機；維修工程師 24 小時內完成檢查
- 所有工單結案需填寫：處置結果、是否為誤報、是否更換零件
""", "模擬的權責分工")


# ===========================================================================
# 🟡 文件三：維修工單
# ===========================================================================

def build_work_orders(f: dict) -> None:
    doc, title = "work_orders", "維修工單紀錄（模擬）"
    t, date_of = f["traj"], f["date_of"]
    rng = random.Random(42)
    src = "工單號與處置文字為模擬；引擎編號、觸發 cycle、Warning 筆數、最後判讀皆取自 model_predictions.csv"

    opened = t[t["l2_cycle"].notna()].sort_values("l2_cycle")
    for n, (u, r) in enumerate(opened.iterrows(), start=1):
        wo = f"MWO-2026-{n:04d}"
        l2c = int(r["l2_cycle"])
        l3c = None if pd.isna(r["l3_cycle"]) else int(r["l3_cycle"])
        level = "L3 停機檢查" if l3c else "L2 排程檢查"
        lines = [
            f"工單編號：{wo}",
            f"引擎：{eng(u)}",
            f"目前等級：{level}",
            f"開單：cycle {l2c}（匯出日 {date_of.get((u, l2c), '—')}），"
            f"最近 {WINDOW} 筆讀數中出現 {L2_MIN} 筆以上 Warning，觸發 L2 排程檢查",
        ]
        if l3c:
            lines.append(f"升級：cycle {l3c}（匯出日 {date_of.get((u, l3c), '—')}），"
                         f"最近 {WINDOW} 筆中達 {L3_MIN} 筆以上 Warning，升級為 L3 停機檢查")
        lines += [
            f"首次出現 Warning：cycle {int(r['first_warning'])}",
            f"整個觀測期共 {int(r['n_readings'])} 筆讀數，其中 {int(r['n_warning'])} 筆判為 Warning",
            f"最後一筆讀數：cycle {int(r['last_cycle'])}，判讀 {r['last_status']}，"
            f"最近距離 {r['last_distance']:.4f}",
            f"指派：維修工程師 ME-{rng.randint(1, 6):02d}",
            f"狀態：追蹤中（資料集至 cycle {int(r['last_cycle'])} 結束，未提供後續維修結果）",
        ]
        if r["last_status"] == "Healthy":
            lines.append("備註：最後一筆讀數判為 Healthy，但趨勢分級已觸發工單，"
                         "依 SOP 仍需完成檢查，不可因單筆讀數恢復而結案。")
        add(doc, title, f"{wo} {eng(u)}", SIMULATED, "\n".join(lines), src, [eng(u)])

    never = t[t["l2_cycle"].isna()]
    add(doc, title, "工單總覽", SIMULATED, f"""
依《異常處置 SOP》分級，本機隊 100 台引擎中：
- 共開立 {len(opened)} 張工單（曾觸發 L2 排程檢查）
- 其中 {int(opened['l3_cycle'].notna().sum())} 張升級為 L3 停機檢查
- {len(never)} 台引擎從未觸發 L2，未開立工單
最早開單的是 {eng(opened.index[0])}（cycle {int(opened.iloc[0]['l2_cycle'])}）。
""", src, [eng(opened.index[0])])

    ids = [eng(u) for u in never.index]
    add(doc, title, "未開立工單的引擎清單", SIMULATED,
        f"以下 {len(ids)} 台引擎在整個觀測期間從未觸發 L2，因此沒有工單"
        f"（其中曾出現零星 Warning、僅達 L1 觀察的有 {int(never['first_warning'].notna().sum())} 台）：\n"
        + "、".join(ids), src, ids)


# ===========================================================================
# 🟡 文件四：交接班紀錄
# ===========================================================================

def build_shift_logs(f: dict) -> None:
    doc, title = "shift_logs", "交接班紀錄（模擬）"
    t, date_of, preds = f["traj"], f["date_of"], f["preds"]
    src = "交接內容的文字為模擬；提及的引擎、cycle、事件皆取自 model_predictions.csv 與 SOP 分級計算"

    events = []
    for u, r in t.iterrows():
        if pd.notna(r["l3_cycle"]):
            c = int(r["l3_cycle"])
            events.append((date_of.get((u, c)), u, c, "L3"))
        if pd.notna(r["l2_cycle"]):
            c = int(r["l2_cycle"])
            events.append((date_of.get((u, c)), u, c, "L2"))
        if pd.notna(r["first_warning"]):
            c = int(r["first_warning"])
            events.append((date_of.get((u, c)), u, c, "L1"))

    ev = pd.DataFrame(events, columns=["date", "unit", "cycle", "level"]).dropna()
    for date in sorted(ev["date"].unique()):
        day = ev[ev["date"] == date]
        for shift, parity in [("日班", 1), ("夜班", 0)]:
            part = day[day["unit"] % 2 == parity]
            l3 = part[part.level == "L3"].sort_values("cycle")
            l2 = part[part.level == "L2"].sort_values("cycle")
            l1 = part[part.level == "L1"]
            lines = [f"日期：{date}　班別：{shift}"]
            if len(l3):
                shown = l3.head(5)
                lines.append("【需立即處理】以下引擎升級 L3，已通報主管安排停機檢查：" +
                             "、".join(f"{eng(x.unit)}（cycle {x.cycle}）" for x in shown.itertuples()))
                if len(l3) > 5:
                    lines.append(f"另有 {len(l3) - 5} 台同樣升級 L3，詳見工單清單。")
            if len(l2):
                shown = l2.head(5)
                lines.append("新開排程檢查工單（L2）：" +
                             "、".join(f"{eng(x.unit)}（cycle {x.cycle}）" for x in shown.itertuples()))
                if len(l2) > 5:
                    lines.append(f"另有 {len(l2) - 5} 台觸發 L2，已開單。")
            if len(l1):
                lines.append(f"今日有 {len(l1)} 台引擎首次出現單筆 Warning，列入 L1 觀察，"
                             f"例如 {'、'.join(eng(x) for x in sorted(l1.unit)[:4])}。")
            if len(lines) == 1:
                lines.append("本班次無新增異常事件，例行巡檢正常。")
            lines.append("交接提醒：L2 工單請下一班確認是否為誤報，模型偏向寧可誤報。")
            engines = [eng(x) for x in list(l3.head(5).unit) + list(l2.head(5).unit)]
            add(doc, title, f"{date} {shift}", SIMULATED, "\n".join(lines), src, engines)

    # 兩台「最後一筆被漏判」的引擎，現場紀錄會怎麼寫
    v = f["validation"]
    missed = v[(v.TrueLabel == "Warning") & (v.PredictedStatus == "Healthy")]
    for eid in missed["EquipmentID"]:
        u = int(eid[4:])
        r = t.loc[u]
        last = int(r["last_cycle"])
        tail = preds[(preds.unit_number == u) & (preds.time_cycles > last - WINDOW)]
        n_tail = int((tail.PredictedStatus == "Warning").sum())
        lvl = "L3" if pd.notna(r["l3_cycle"]) else "L2"
        add(doc, title, f"特記事項 {eid}", SIMULATED, f"""
日期：{date_of.get((u, last), '—')}　特記事項
{eid} 最新一筆讀數（cycle {last}）判讀為 Healthy，有同仁詢問是否可以結案。
查閱紀錄：該引擎最近 {WINDOW} 筆讀數中仍有 {n_tail} 筆 Warning，且先前已觸發 {lvl}（工單追蹤中）。
依 SOP，單筆讀數恢復 Healthy 不可作為結案依據，維持原工單等級繼續檢查。
""", src, [eid])


# ===========================================================================
# 🟢 文件五：模型卡
# ===========================================================================

def build_model_card(f: dict) -> None:
    doc, title = "model_card", "VAE 異常偵測模型卡"
    m, v = f["meta"], f["validation"]
    truth, pred = v["TrueLabel"].values, v["PredictedStatus"].values
    cm = [[int(((truth == a) & (pred == b)).sum()) for b in ("Healthy", "Warning")]
          for a in ("Healthy", "Warning")]
    acc = float((truth == pred).mean())
    wp = cm[1][1] / (cm[0][1] + cm[1][1])
    wr = cm[1][1] / (cm[1][0] + cm[1][1])
    hp = cm[0][0] / (cm[0][0] + cm[1][0])
    hr = cm[0][0] / (cm[0][0] + cm[0][1])
    cut = float(np.quantile(v["TrueRUL"], 0.33))
    src = "01-core-model/outputs/model_validation.csv、07-demo-app/assets/meta.json（實測）"

    add(doc, title, "1. 模型概要", MEASURED, f"""
模型：變分自編碼器（VAE），架構 21 → 64 → 2（潛空間）→ 64 → 21，以 PyTorch 訓練。
資料：NASA CMAPSS FD001，訓練集 100 台引擎、20,631 筆讀數，21 個感測器。
用途：將每筆感測讀數判讀為 Healthy 或 Warning，作為自動化報表流程的判讀引擎。
方法：模型本身不是分類器，而是學習把高維感測訊號壓縮成有結構的 2 維表徵，
再以最近鄰（1-NN）在表徵空間中比對 {m['support_size']:,} 筆歷史讀數完成分類。
這種作法適合故障樣本稀少、標註不足的情境（few-shot）。
""", src)

    add(doc, title, "2. 判讀規則與參數", MEASURED, f"""
- 前處理：MinMaxScaler，以訓練集 70% 擬合（train_test_split, test_size=0.3, random_state=42）
- Support set：訓練集 70% 的 embedding，共 {m['support_size']:,} 點
- Support 標籤分界：訓練集剩餘壽命的 33% 分位數 = {m['support_cut_rul']:.1f} cycles
  （剩餘壽命 > 分界為 Healthy，≤ 分界為 Warning）
- 判讀：取潛空間中最近的 support 點標籤
""", src)

    add(doc, title, "3. 評估方法", MEASURED, f"""
評估對象：test_FD001 中每台引擎的最後一個 cycle，共 {len(v)} 台。
這是 CMAPSS 的標準評估法，因為 RUL_FD001 只提供最後那一點的真實剩餘壽命。
真實標籤分界：RUL_FD001 的 33% 分位數 = {cut:.1f} cycles。
兩個分界各自在自己的分佈上計算，互不洩漏。
逐筆判讀的 13,096 筆讀數（model_predictions.csv）不含真實答案，是模擬營運系統的輸出。
""", src)

    add(doc, title, "4. 評估結果", MEASURED, f"""
Accuracy = {acc:.4f}
混淆矩陣（列為實際、欄為預測）：
- 實際 Healthy：預測 Healthy {cm[0][0]} 台、預測 Warning {cm[0][1]} 台（誤報）
- 實際 Warning：預測 Healthy {cm[1][0]} 台（漏判）、預測 Warning {cm[1][1]} 台
Warning 類：precision {wp:.4f}、recall {wr:.4f}
Healthy 類：precision {hp:.4f}、recall {hr:.4f}
模型偏向寧可誤報、不要漏判：誤報一次的代價是多做一次檢查，漏判一次的代價是引擎沒被預警就故障。
""", src)

    miss = v[(v.TrueLabel == "Warning") & (v.PredictedStatus == "Healthy")].sort_values("TrueRUL")
    lines = []
    for r in miss.itertuples():
        gap = cut - r.TrueRUL
        kind = ("標籤邊界效應：只比分界線內側少 %.1f 個 cycle，分位數稍微移動就不算錯" % gap
                if gap < 5 else
                "真正的漏判：離分界線 %.1f 個 cycle，讀數在潛空間中仍落在健康樣本附近" % gap)
        lines.append(f"- {r.EquipmentID}：最後 cycle {r.LastCycle}，真實剩餘壽命 {r.TrueRUL} cycles。{kind}。")
    fa = v[(v.TrueLabel == "Healthy") & (v.PredictedStatus == "Warning")]
    add(doc, title, "5. 已知錯誤：漏判與誤報", MEASURED,
        f"漏判 {len(miss)} 台（最後一筆讀數被判為 Healthy）：\n" + "\n".join(lines) +
        f"\n誤報 {len(fa)} 台：" + "、".join(fa["EquipmentID"]) + "。",
        src, list(miss["EquipmentID"]) + list(fa["EquipmentID"]))

    t = f["traj"]
    l2 = t[t["l2_cycle"].notna()]
    l3 = t[t["l3_cycle"].notna()]
    lab = v.assign(unit=v.EquipmentID.str[4:].astype(int)).set_index("unit")["TrueLabel"]
    n_true = int((lab == "Warning").sum())
    l2_hit = int((lab.loc[l2.index] == "Warning").sum())
    l3_hit = int((lab.loc[l3.index] == "Warning").sum())
    add(doc, title, "6. 補充觀察：看連續讀數而非單筆讀數", MEASURED, f"""
若不看最後一筆讀數，而是套用《異常處置 SOP》的趨勢分級（最近 {WINDOW} 筆中 Warning 筆數），
在同一份測試資料上觀察到：
- 真實標籤為 Warning 的 {n_true} 台引擎，有 {l2_hit} 台曾觸發 L2（≥{L2_MIN} 筆），包含上述兩台漏判引擎
- 觸發 L3（≥{L3_MIN} 筆）的 {len(l3)} 台中，{l3_hit} 台真實標籤為 Warning、{len(l3) - l3_hit} 台為 Healthy
限制：分級門檻雖為事先訂定，但此觀察與模型評估使用同一份測試資料，且比較的是「整個觀測期」
與「最後一筆」兩種不同的評估方式，屬事後觀察，未經獨立資料驗證，不應視為模型效能指標。
""", "由 model_predictions.csv 依 SOP 門檻計算，並對照 model_validation.csv 的真實標籤")

    add(doc, title, "7. 限制與部署", MEASURED, f"""
限制：
- 僅在 FD001（單一運轉條件、單一失效模式）上訓練；換到其他工況的實測表現見第 8 節
- 公開模擬資料集，無真實維修成本資料；成本效益（維護成本 −84%、停機 −36%）為情境推估
- 二分類是刻意的設計取捨：現場需要的是「要不要處理」的決策，而非精確的剩餘壽命數字
部署：
- 網站上的即時判讀以純 NumPy 重算 VAE，權重自 PyTorch 匯出
- NumPy 版與 PyTorch 版最大絕對誤差 {m['numpy_vs_torch_max_abs_diff']:.1e}，
  並驗證可逐格重現上述評估結果與 13,096 筆逐筆判讀
""", src)

    gen = json.loads((APP / "assets" / "generalization.json").read_text(encoding="utf-8"))
    ds = {d["name"]: d for d in gen["datasets"]}
    pool = gen["pooled_out_of_range_last_reading"]
    in_cond = [c for c in gen["fd002_by_condition"] if c["in_range_share"] > 0.5]
    lines = [
        f"- {n}（{ds[n]['note']}）：Accuracy {ds[n]['accuracy']:.1%}，快故障 {ds[n]['true_warning']} 台只抓到 "
        f"{ds[n]['caught']} 台；加上適用範圍檢查後，被誤判為健康的從 {ds[n]['missed']} 台降為 "
        f"{ds[n]['guarded_falsely_healthy']} 台"
        for n in ["FD003", "FD002", "FD004"]
    ]
    add(doc, title, "8. 換到其他工況的新引擎：實測表現與適用範圍檢查", MEASURED, f"""
問題：導入新引擎也能判讀嗎？以同系列、附真實答案的 NASA FD002 / FD003 / FD004 實測（評估方式比照 FD001：每台最後一個 cycle）。
{chr(10).join(lines)}
Accuracy 約 70% 是假象：快故障只佔約三分之一，全部判 Healthy 也有約 67%。換工況時模型幾乎都判 Healthy，這是最危險的錯法。
適用範圍檢查：讀數到最近訓練點的距離超過 {gen['threshold']:.4f}（FD001 測試集第 99 百分位）即視為超出範圍。
FD002 六種運轉條件中，只有 {len(in_cond)} 種（{'、'.join(c['cond'] for c in in_cond)}，與訓練資料相同的海平面條件）落在範圍內。
超出範圍時：判 Warning 的 {pool['out_warning']} 台全部真的快故障，照樣顯示 Warning；判 Healthy 的 {pool['out_healthy']} 台中 {pool['out_healthy_true']} 台其實快故障，因此改標「無法確認」，不宣告健康。
限制：距離門檻依 FD001 事先訂定，但「Warning 可信、Healthy 不可信」的規則是看過這四組資料後歸納的事後觀察，且 Warning 側樣本僅 {pool['out_warning']} 台。
""", "07-demo-app/assets/generalization.json（build/export_new_engine_assets.py 以 NASA FD001–FD004 實測）")


# ===========================================================================
# 🟢 文件六：精實改善與效益
# ===========================================================================

def build_lean(f: dict) -> None:
    doc, title = "lean", "精實改善案與效益驗證"
    log = f["runlog"]

    add(doc, title, "1. 問題定義：兩層浪費", MEASURED, """
製造與維運現場有兩層浪費，本案兩層都處理，但主從分明：
- 第二層｜流程浪費（主角）：工程師每天手動下載 SAP-style 匯出檔、在 Excel 清理彙整、人工判讀、手動寄報表。
  解法為 VBA 巨集 + Power Automate Desktop（RPA）+ Power BI，效益可實測。
- 第一層｜實體浪費（技術亮點）：設備非計畫停機與過度保養。
  解法為 VAE 異常偵測模型自動判讀健康狀態，效益為情境推估。
方法論：Lean Six Sigma DMAIC（Define、Measure、Analyze、Improve、Control）。
""", "整理自 06-lean-lss/DMAIC.md 與根目錄 README.md（以最終版本為準）")

    add(doc, title, "2. 手動流程與浪費盤點", MEASURED, """
改善前的手動流程共 7 步：登入 SAP 匯出 CSV → Excel 匯入貼上 → 手動清理髒資料（去空白、去重、補缺）
→ 手動彙整（樞紐分析）→ 人工判讀健康 → 製作報表 → 手動寄 Email。
對應的七大浪費：Motion（反覆下載、複製貼上）、Waiting（等匯出、等彙整）、
Overprocessing（每天重做同樣清理）、Defects（人工修正出錯、判讀主觀）、
Underutilized talent（工程師時間耗在行政作業）。
實測手動完成一次清理彙整需 15 分鐘（碼錶計時）。
""", "整理自 06-lean-lss/value-stream-map.md 與 02-automation-vba/README.md；15 分鐘為碼錶實測")

    add(doc, title, "3. 自動化結果（實測）", MEASURED, f"""
VBA 巨集 CleanAndSummarize 一次處理 {log.files_read} 個匯出檔：
- 原始 {log.rows_read:,} 列 → 去除重複 {log.duplicates_removed:,} 列 → 乾淨 {log.clean_rows:,} 列
- 狀態大小寫正規化 {log.status_normalized:,} 筆，模型 Warning 共 {log.total_warnings:,} 筆
- 缺 NearestDistance {log.missing_distance:,} 筆、缺 MaintenanceCost {log.missing_cost:,} 筆
耗時兩次實測：Alt+F8 互動執行 1.6 秒、經 Power Automate 觸發 {f['rpa_seconds']:.3f} 秒，
相較手動 15 分鐘約快 500 倍（兩次分別為 {900 / 1.6:.0f} 倍與 {900 / f['rpa_seconds']:.0f} 倍）。
""", "02-automation-vba/README.md 與 03-rpa-power-automate/outbox 報表 Summary 分頁（實測）")

    nv = f["naive"]
    add(doc, title, "4. 手動作業的靜默錯誤", MEASURED, f"""
手動流程最大的風險不是慢，而是出錯時 Excel 不會報錯。若直接拿原始匯出檔做樞紐分析、
忘了 TRIM 與統一大小寫：
- 樞紐表會出現 {nv.machine_rows} 台機台（實際只有 100 台），同一台被拆成多列
- 狀態欄出現 {len(nv.status_categories)} 種寫法（{'、'.join(nv.status_categories)}）
- Warning 只數到 {nv.warning_rows_counted:,} 筆，實際為 {log.total_warnings:,} 筆
建立手動基線時真的發生過：Ctrl+H 的空白取代沒有生效，樞紐分析把前後有空白的機台代號當成另一台，且無任何錯誤訊息。
漏算 Warning 的代價可能是一台引擎的非計畫停機。
""", "07-demo-app 自動化頁直接對原始匯出檔計算；手動基線事件記錄於 02-automation-vba/README.md")

    manual, auto, per_day, people, days, rate, dev_h = 900, 1.6, 2, 1, 240, 500, 40
    saved_h = (manual - auto) * per_day * people * days / 3600
    saved_ntd = saved_h * rate
    cost = dev_h * rate
    roi = (saved_ntd - cost) / cost
    payback = cost / ((manual - auto) * per_day * people / 3600 * rate)
    add(doc, title, "5. ROI 效益試算", MEASURED, f"""
實測輸入（🟢）：手動單次 {manual} 秒、自動單次 {auto} 秒，單次省時 {manual - auto:.1f} 秒。
假設輸入（🟡，可替換）：每天 {per_day} 次、{people} 人、每年 {days} 工作天、人力成本 NT${rate}/小時、
一次性導入工時 {dev_h} 小時（含需求釐清、開發、測試、RPA 串接、看板、文件與訓練）。
結果：年省約 {saved_h:.0f} 小時、年省人力成本約 NT${saved_ntd:,.0f}；導入成本 NT${cost:,.0f}；
首年 ROI 約 {roi:.0%}；回本約 {payback:.0f} 個工作天。
唯一的實測值是單次省時；年省工時、ROI、回本天數都建立在使用量假設上。
使用量假設曾由 3 人 × 每天 3 次下修為 1 人 × 每天 2 次，因原假設使 ROI 高達 1,248%，不具可信度。
""", "06-lean-lss/build_roi.py 與 roi-validation.xlsx（校準版），本段依相同公式重算")

    add(doc, title, "6. 維護成本 −84% 與停機時間 −36% 的推導", MEASURED, """
這兩個數字是情境推估（🟡），不是實測。推導方式為 value-driver 公式，比較公開基準版本與本專案模型：
- 公開基準：推導採用 precision 75%、recall 70%，依據為原始 Kaggle notebook
  （wassimderbel/nasa-predictive-maintenance-rul）的分類段落；該段各模型（SVM、隨機森林、
  Naive Bayes、KNN）在測試集上的 macro precision 約 0.66–0.72、recall 約 0.65–0.71
- 本專案 VAE（Healthy 類實測）：precision 96.4%、recall 80.6%，推導時取整數 96%、81%
  （若以未取整的值計算，兩個降幅分別約為 86% 與 35%）
- 1 − Precision(Healthy)：25% → 4%，代表「判為健康、其實在衰退」的漏判比例下降 84.0%，
  對應非計畫故障造成的維護成本
- 1 − Recall(Healthy)：30% → 19%，代表「其實健康、卻被叫去檢修」的比例下降 36.7%（報告中記為 36%），對應不必要的停機
限制：公開基準是 3 分類（RUL ≤68 / 69–137 / >137）、在 7,221 筆上評估；本專案是 2 分類、
在 100 台引擎的最後一個 cycle 上評估，兩者評估方式不同。公開資料集沒有真實成本資料。
""", "推導整理自 01-core-model/docs/航太專案 量化效益對比與技術補充.xlsx；Healthy 類指標取自 model_validation.csv")

    add(doc, title, "7. Power Automate 流程與誠信聲明", MEASURED, """
實際採用的 Power Automate Desktop 流程 DailyHealthReport：開啟 Excel 執行無對話框巨集 CleanAndSummarizeSilent
→ 儲存關閉 → 取得當日日期 → 複製報表到 outbox → 重新命名為 DailyHealthReport_yyyyMMdd.xlsm → 桌面通知。
巨集另提供無對話框進入點，因為 RPA 遇到彈窗會卡住等人點擊。
誠信聲明：
- SAP 匯出檔為模擬（格式仿 SAP 匯出的髒資料），本專案未串接真實 SAP 系統
- 「從 SAP 下載」在流程中以複製檔案模擬；分發採存檔加桌面通知，未串接 Email
- Power Apps 僅完成設計稿（個人帳號無法部署）
- 雲端展示網站無法執行 VBA 與 Power Automate，網站上的清理為同一套規則的 Python 重現，已與 RPA 實際產出逐項驗證一致
""", "03-rpa-power-automate/README.md、screenshots/自動化流程.png、04-powerapps-design/README.md")


# ===========================================================================
# 輸出
# ===========================================================================

def write_outputs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "chunks.json").write_text(json.dumps(CHUNKS, ensure_ascii=False, indent=1), encoding="utf-8")

    docs_dir = OUT / "docs"
    docs_dir.mkdir(exist_ok=True)
    for doc in dict.fromkeys(c["doc"] for c in CHUNKS):
        items = [c for c in CHUNKS if c["doc"] == doc]
        badge = "🟢 真實專案文件" if items[0]["kind"] == MEASURED else "🟡 模擬文件（數值取自真實資料）"
        body = [f"# {items[0]['doc_title']}", "", f"> {badge}", ""]
        for c in items:
            body += [f"## {c['section']}", "", c["text"], "", f"*來源：{c['source']}*", ""]
        (docs_dir / f"{doc}.md").write_text("\n".join(body), encoding="utf-8")


def main() -> None:
    f = load_facts()
    build_manual(f)
    build_sop(f)
    build_work_orders(f)
    build_shift_logs(f)
    build_model_card(f)
    build_lean(f)
    write_outputs()

    print(f"共 {len(CHUNKS)} 個片段")
    for doc in dict.fromkeys(c["doc"] for c in CHUNKS):
        items = [c for c in CHUNKS if c["doc"] == doc]
        chars = sum(len(c["text"]) for c in items)
        print(f"  {items[0]['kind']:9s} {doc:12s} {len(items):3d} 片段  {chars:6,} 字")
    lens = [len(c["text"]) for c in CHUNKS]
    print(f"片段長度：最短 {min(lens)}、中位數 {int(np.median(lens))}、最長 {max(lens)} 字")


if __name__ == "__main__":
    main()
