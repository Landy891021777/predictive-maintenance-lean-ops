"""即時判讀：拉動感測器，當場看模型怎麼判。

這一頁跑的是**真的模型**，不是預先算好的結果重播。
權重來自 vae_model.pth，以純 NumPy 重算（build/verify_numpy_path.py 已驗證
這條路徑能逐格重現 model_validation.md 的 85% 與混淆矩陣）。

=== 狀態管理（踩過坑，別改壞）===
滑桿一旦帶了 key，Streamlit 在後續 rerun 就**只認 session_state 裡的值**，
`value=` 參數完全失效。所以「載入真實讀數」不能只更新底層陣列——必須在 on_click
回呼裡直接寫入每一根滑桿的 key（回呼在 widget 建立前執行，所以寫得進去）。
否則按鈕看起來沒反應：陣列被更新了，但下一行的 st.slider 立刻用舊值蓋回去。
"""

from __future__ import annotations

import io

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from core.data import (
    get_detector,
    load_demo_fleet,
    load_generalization,
    load_meta,
    load_support_scatter,
    load_test_readings,
    load_validation,
)
from core.new_engine import STATUS_LABEL, UploadError, assess_readings, parse_upload, summarise_engines
from core.ui import MEASURED, integrity_note, metric_card, page_header

KEY_SENSORS = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]
OTHER_VARYING = [6, 20, 21]
EDITABLE = KEY_SENSORS + OTHER_VARYING

STATE_KEY = "sensor_values"      # 完整 21 維讀數（含不可調的常數感測器）
LOADED_KEY = "loaded_row"        # 最後一次載入的原始讀數，用來判斷是否被手動調整過
LABEL_KEY = "loaded_label"


def _bounds(meta: dict, s: int) -> tuple[float, float, float]:
    stat = meta["sensor_stats"][f"s_{s}"]
    return float(stat["slider_min"]), float(stat["slider_max"]), float(stat["slider_step"])


def _apply_reading(row: np.ndarray, meta: dict, label: str) -> None:
    """把一筆 21 維讀數寫進 session_state，包含每一根滑桿的 key。"""
    row = np.asarray(row, dtype=np.float64).copy()
    st.session_state[STATE_KEY] = row
    st.session_state[LOADED_KEY] = row.copy()
    st.session_state[LABEL_KEY] = label
    for s in EDITABLE:
        lo, hi, _ = _bounds(meta, s)
        # 範圍已涵蓋訓練集 ∪ 測試集全距，clip 只是保險，正常不會生效
        st.session_state[f"sl_{s}"] = float(np.clip(row[s - 1], lo, hi))


def _load_preset(sensors, unit, cycle, meta: dict, u: int, c: int) -> None:
    hit = np.where((unit == u) & (cycle == c))[0]
    if len(hit):
        _apply_reading(sensors[hit[0]], meta, f"ENG-{u:03d} · cycle {c}")


def _current_vector() -> np.ndarray:
    """從 session_state 組出要送進模型的 21 維向量。"""
    v = np.asarray(st.session_state[STATE_KEY], dtype=np.float64).copy()
    for s in EDITABLE:
        v[s - 1] = st.session_state[f"sl_{s}"]
    return v


def _sensor_slider(meta: dict, s: int) -> None:
    lo, hi, step = _bounds(meta, s)
    stat = meta["sensor_stats"][f"s_{s}"]
    # 不傳 value=：這根滑桿的值完全由 session_state[f"sl_{s}"] 決定
    st.slider(
        f"Sensor {s}",
        min_value=lo, max_value=hi, step=step,
        key=f"sl_{s}",
        help=f"訓練資料 p01–p99：{stat['p01']:.4g} – {stat['p99']:.4g}",
    )


def render() -> None:
    page_header(
        "即時判讀",
        "調整感測器讀數或載入真實引擎，模型會立刻判讀健康狀態；"
        "也可以導入一批新引擎，看模型在沒見過的資料上表現如何、什麼時候不該被信任。",
        "Architected a VAE-based fault-detection framework in Python",
    )
    t1, t2 = st.tabs(["單筆讀數", "導入新引擎"])
    with t1:
        _single_reading_tab()
    with t2:
        _new_engine_tab()


def _single_reading_tab() -> None:
    det = get_detector()
    meta = load_meta()
    v = load_validation()
    unit, cycle, sensors = load_test_readings()
    threshold = load_generalization()["threshold"]

    if STATE_KEY not in st.session_state:
        first = np.where((unit == 1) & (cycle == 1))[0][0]
        _apply_reading(sensors[first], meta, "ENG-001 · cycle 1")

    # ---------- 載入真實讀數 ----------
    with st.container(border=True):
        st.markdown("**載入真實引擎讀數**")
        c1, c2, c3 = st.columns([2, 2, 3])
        engines = np.unique(unit)
        with c1:
            u = int(st.selectbox("引擎", engines, format_func=lambda x: f"ENG-{x:03d}"))
        with c2:
            cycles = cycle[unit == u]
            c = int(st.slider("Cycle", int(cycles.min()), int(cycles.max()), int(cycles.min())))
        with c3:
            st.write("")
            b1, b2 = st.columns(2)
            b1.button("載入這筆讀數", width="stretch",
                      on_click=_load_preset, args=(sensors, unit, cycle, meta, u, c))
            b2.button("載入最後一個 cycle", width="stretch",
                      on_click=_load_preset,
                      args=(sensors, unit, cycle, meta, u, int(cycles.max())))

        values = _current_vector()
        edited = not np.allclose(values, st.session_state[LOADED_KEY], rtol=0, atol=1e-9)
        st.caption(
            f"目前載入：**{st.session_state[LABEL_KEY]}**"
            + ("　·　⚠️ 已手動調整，已偏離原始讀數" if edited else "　·　未經調整的真實讀數")
        )

    # ---------- 感測器輸入 ----------
    st.markdown("#### 感測器輸入")
    st.caption("以下 12 顆是本案的特徵選擇（見 `航太維修專案 背景.md`）；模型內部仍吃全部 21 顆。")
    cols = st.columns(3)
    for i, s in enumerate(KEY_SENSORS):
        with cols[i % 3]:
            _sensor_slider(meta, s)

    with st.expander("其餘 9 顆感測器"):
        cols2 = st.columns(3)
        for i, s in enumerate(OTHER_VARYING):
            with cols2[i % 3]:
                _sensor_slider(meta, s)
        st.caption(
            "以下 6 顆在 FD001 全程為定值，沒有資訊量，因此不提供調整："
            + "、".join(meta["constant_sensors"])
        )

    # ---------- 判讀 ----------
    values = _current_vector()
    verdict = det.classify(values)

    st.divider()
    st.markdown("#### 模型判讀結果")

    in_range = verdict.nearest_distance <= threshold
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        if verdict.status == "Warning":
            st.error("### ⚠️ Warning\n建議安排檢查")
        elif in_range:
            st.success("### ✅ Healthy\n可繼續運轉")
        else:
            st.warning("### ❔ 無法確認\n超出模型適用範圍")
    if not in_range:
        st.caption(
            f"⚠️ 這筆讀數到最近訓練點的距離 {verdict.nearest_distance:.4f}，超過適用範圍門檻 {threshold:.4f}。"
            + ("模型原本判為 Healthy，但超出範圍時 Healthy 不可信，因此不宣告健康。"
               if verdict.status == "Healthy" else
               "超出範圍時模型的 Warning 仍可信（實測 17/17），因此照樣顯示。")
            + " 詳見「導入新引擎」分頁。"
        )
    with m2:
        metric_card("潛空間座標",
                    f"({verdict.latent[0]:.3f}, {verdict.latent[1]:.3f})",
                    "encoder 輸出的 mu，latent_dim = 2", MEASURED)
    with m3:
        metric_card("最近 support 距離", f"{verdict.nearest_distance:.4f}",
                    "到 14,441 個訓練點中最近那一點", MEASURED)
    with m4:
        metric_card("重建誤差 (MSE)", f"{verdict.reconstruction_error:.6f}",
                    "decode(mu) 與輸入的均方誤差", MEASURED)

    st.caption(
        f"判讀依據：最近的那個 support 點，其真實剩餘壽命為 **{verdict.neighbour_rul} cycles**"
        f"（分界 {meta['support_cut_rul']:.0f}：大於為 Healthy，小於等於為 Warning）。"
    )

    # ---------- 潛空間 ----------
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("#### 潛空間位置")
        scatter = load_support_scatter()
        base = (
            alt.Chart(scatter)
            .mark_circle(size=14, opacity=0.35)
            .encode(
                x=alt.X("z1:Q", title="latent z1"),
                y=alt.Y("z2:Q", title="latent z2"),
                color=alt.Color(
                    "狀態:N",
                    scale=alt.Scale(domain=["Healthy", "Warning"],
                                    range=["#2e9e5b", "#d6453d"]),
                ),
                tooltip=["狀態"],
            )
        )
        here = (
            alt.Chart(pd.DataFrame({"z1": [verdict.latent[0]], "z2": [verdict.latent[1]]}))
            .mark_point(size=320, shape="diamond", filled=True,
                        color="#1f6feb", stroke="white", strokeWidth=2)
            .encode(x="z1:Q", y="z2:Q")
        )
        st.altair_chart((base + here).properties(height=380), width="stretch")
        st.caption("散點為 support set（抽樣 4,000 點），藍色菱形是目前這筆讀數的位置。")

    with right:
        st.markdown("#### 這個模型怎麼判")
        st.markdown(
            f"""
1. 21 個原始感測值 → MinMaxScaler（用訓練集擬合的參數）
2. VAE encoder 壓成 **2 維** 潛空間座標 `mu`
3. 在 **{meta['support_size']:,}** 個訓練點裡找**最近的一點**（1-NN）
4. 取那一點的標籤：真實 RUL > **{meta['support_cut_rul']:.0f}** cycles → Healthy，否則 Warning

這是 few-shot 的作法：模型本身**沒有**被訓練成分類器，
它只學會把高維感測訊號壓成有結構的低維表徵；分類是在那個表徵空間裡用距離完成的。
故障樣本稀少時，這個作法比直接訓練分類器實際。
            """
        )
        st.markdown("#### 這個模型的已知取捨")
        st.markdown(
            f"""
在 {v.n_engines} 台引擎上：**漏判 {v.missed} 台、誤報 {v.false_alarms} 台**。

- Warning 的 recall = **{v.warning_recall:.1%}**（該抓的抓到了）
- Warning 的 precision = **{v.warning_precision:.1%}**（誤報偏多）

這是刻意的取捨：**誤報一次的代價是多做一次檢查，漏判一次的代價是引擎在空中故障。**
在預測性維護上，寧可誤報、不要漏判。
            """
        )

    integrity_note(
        "本頁的判讀為即時運算，非預錄結果。線上以純 NumPy 重算 VAE，"
        "與 PyTorch 原始模型的最大絕對誤差為 "
        f"{meta['numpy_vs_torch_max_abs_diff']:.1e}（float32 捨入層級）。"
    )


# ===========================================================================
# 導入新引擎
# ===========================================================================

SOURCE_FD003 = "示範：FD003 新機隊（同工況）"
SOURCE_FD002 = "示範：FD002 新機隊（不同工況）"
SOURCE_UPLOAD = "上傳自己的檔案"
STATUS_COLOURS = {"Healthy": "#2e9e5b", "Warning": "#d6453d", "Unknown": "#9a9a9a"}


@st.cache_data(show_spinner=False)
def _assess_bytes(raw: bytes, threshold: float):
    df = parse_upload(raw)
    readings = assess_readings(get_detector(), df, threshold)
    return readings, summarise_engines(readings)


def _engine_name(unit: str, demo: bool) -> str:
    return f"NEW-{int(unit):02d}" if demo else str(unit)


def _outcome(last_status: str, true_label: str) -> str:
    if true_label == "Warning":
        return {"Warning": "✅ 正確預警", "Unknown": "⚠️ 未宣告健康（實際快故障）",
                "Healthy": "❌ 誤判為健康"}[last_status]
    return {"Healthy": "✅ 正確判為健康", "Unknown": "⚠️ 無法確認（實際健康）",
            "Warning": "誤報"}[last_status]


def _template_csv() -> bytes:
    raw, _ = load_demo_fleet("FD003")
    return pd.read_csv(io.BytesIO(raw)).drop(
        columns=["setting_1", "setting_2", "setting_3"]).head(12).to_csv(index=False).encode("utf-8")


def _new_engine_tab() -> None:
    gen = load_generalization()
    threshold = gen["threshold"]

    st.markdown(
        "模型是用 NASA CMAPSS **FD001**（單一運轉條件、單一失效模式）訓練的。"
        "導入一批沒看過的引擎時，除了判讀，還會做**適用範圍檢查**："
        "讀數離訓練資料太遠時，模型判的 Healthy 不可信，因此改標為「無法確認」，不宣告健康。"
    )

    source = st.radio("資料來源", [SOURCE_FD003, SOURCE_FD002, SOURCE_UPLOAD], horizontal=True)
    demo = source != SOURCE_UPLOAD
    answers = None

    if source == SOURCE_UPLOAD:
        c1, c2 = st.columns([3, 1])
        with c1:
            up = st.file_uploader(
                "上傳 CSV 或 TXT（NASA 原始格式，或含 s_1…s_21 欄位的表格；unit、cycle 可省略）",
                type=["csv", "txt"])
        with c2:
            st.write("")
            st.download_button("下載範本 CSV", _template_csv(), "new_engine_template.csv",
                               "text/csv", width="stretch")
        if up is None:
            st.info("尚未上傳檔案。可以先下載範本，看欄位格式。")
            return
        raw = up.getvalue()
    else:
        name = "FD003" if source == SOURCE_FD003 else "FD002"
        raw, answers = load_demo_fleet(name)
        info = next(d for d in gen["datasets"] if d["name"] == name)
        st.caption(
            f"從 NASA {name}（{info['note']}）以固定亂數種子分層抽樣 8 台：真實快故障 4 台、健康 4 台，"
            "未挑選對模型有利的引擎。重新編號為 NEW-01 起，避免與訓練機隊的 ENG-xxx 混淆。"
        )

    try:
        readings, summary = _assess_bytes(raw, threshold)
    except UploadError as e:
        st.error(f"檔案格式有問題：{e}")
        return

    last = summary["last_status"]
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("導入引擎", f"{len(summary)} 台", f"共 {len(readings):,} 筆讀數", None)
    with c2:
        metric_card("超出適用範圍的讀數", f"{(~readings['in_range']).mean():.0%}",
                    f"門檻：距離 > {threshold:.4f}", MEASURED)
    with c3:
        metric_card("最後一筆判 Warning", f"{int((last == 'Warning').sum())} 台", "建議安排檢查", MEASURED)
    with c4:
        metric_card("最後一筆無法確認", f"{int((last == 'Unknown').sum())} 台",
                    "超出範圍，不宣告健康", MEASURED)

    table = pd.DataFrame({
        "引擎": [_engine_name(u, demo) for u in summary["unit"]],
        "讀數": summary["readings"],
        "最後 cycle": summary["last_cycle"],
        "最後判讀": [STATUS_LABEL[s] for s in last],
        "觀測期間最高 SOP 等級": summary["sop_level"],
        "超出範圍比例": summary["out_of_range_share"] * 100,
    })
    if answers:
        table["真實剩餘壽命"] = [answers["true_rul"][u] for u in summary["unit"]]
        table["真實標籤"] = [answers["true_label"][u] for u in summary["unit"]]
        table["結果"] = [_outcome(s, answers["true_label"][u]) for s, u in zip(last, summary["unit"])]
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "超出範圍比例": st.column_config.ProgressColumn("超出範圍比例", format="%.0f%%",
                                                          min_value=0, max_value=100),
            "真實剩餘壽命": st.column_config.NumberColumn(format="%.0f cycles"),
        },
    )
    if answers:
        st.caption(
            f"真實答案由 NASA 提供，僅用於驗證，判讀過程不會讀取。"
            f"真實標籤分界：該資料集剩餘壽命的 33% 分位數 = {answers['truth_cut_rul']:.1f} cycles。"
        )

    # ---------- 單台軌跡 ----------
    names = [_engine_name(u, demo) for u in summary["unit"]]
    pick = st.selectbox("查看單台引擎的逐筆判讀", range(len(names)), format_func=lambda i: names[i])
    unit = summary["unit"].iloc[pick]
    d = readings[readings["unit"] == unit].assign(
        判讀=lambda x: x["status"].map({"Healthy": "Healthy", "Warning": "Warning", "Unknown": "無法確認"}),
        距離=lambda x: x["distance"].clip(lower=1e-4),
    )
    points = (
        alt.Chart(d).mark_circle(size=28)
        .encode(
            x=alt.X("cycle:Q", title="cycle"),
            y=alt.Y("距離:Q", title="到最近訓練點的距離（對數刻度）", scale=alt.Scale(type="log")),
            color=alt.Color("判讀:N", scale=alt.Scale(
                domain=["Healthy", "Warning", "無法確認"],
                range=[STATUS_COLOURS["Healthy"], STATUS_COLOURS["Warning"], STATUS_COLOURS["Unknown"]])),
            tooltip=["cycle", "判讀", alt.Tooltip("distance:Q", format=".4f")],
        )
    )
    rule = alt.Chart(pd.DataFrame({"y": [threshold]})).mark_rule(strokeDash=[6, 4], color="#555").encode(y="y:Q")
    st.altair_chart((points + rule).properties(height=320), width="stretch")
    st.caption("虛線是適用範圍門檻；虛線以上的讀數超出範圍，模型若判 Healthy 會改標為「無法確認」。")

    # ---------- 評估依據 ----------
    with st.expander("為什麼要做適用範圍檢查？模型換到其他資料集的實測表現"):
        rows = [{
            "資料集": d["name"], "差異": d["note"], "引擎": d["engines"],
            "Accuracy": f"{d['accuracy']:.1%}",
            "快故障抓到": f"{d['caught']}/{d['true_warning']}",
            "未加檢查：誤判為健康": f"{d['missed']}/{d['true_warning']}",
            "加了檢查：誤判為健康": f"{d['guarded_falsely_healthy']}/{d['true_warning']}",
        } for d in gen["datasets"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        p = gen["pooled_out_of_range_last_reading"]
        st.markdown(
            f"""
- **Accuracy 約 70% 是假象**：快故障的引擎只佔約三分之一，全部判 Healthy 也能拿到約 67%。
  該看的是「快故障抓到幾台」—— 換到 FD002、FD004 時幾乎都被判成 Healthy。
- **但超出範圍量得出來**：FD002 的六種運轉條件中，只有海平面那一種（與訓練資料相同）落在範圍內。
- **超出範圍時，Warning 可信、Healthy 不可信**：四組資料最後一筆超出範圍者，判 Warning 的
  {p['out_warning']} 台全部真的快故障；判 Healthy 的 {p['out_healthy']} 台中有 {p['out_healthy_true']} 台其實快故障。
            """
        )
        cond = pd.DataFrame(gen["fd002_by_condition"]).rename(
            columns={"cond": "FD002 運轉條件（高度／馬赫／油門）", "readings": "讀數", "in_range_share": "範圍內比例"})
        cond["範圍內比例"] = cond["範圍內比例"].map("{:.1%}".format)
        st.dataframe(cond, hide_index=True, width="stretch")
        st.caption("⚠️ 限制：" + "；".join(gen["caveats"]) + "。")
