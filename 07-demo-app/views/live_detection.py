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

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from core.data import (
    get_detector,
    load_meta,
    load_support_scatter,
    load_test_readings,
    load_validation,
)
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
        "調整下方任一顆感測器，模型會立刻重新判讀這台引擎的健康狀態。"
        "也可以直接載入某台真實引擎在某個 cycle 的實際讀數，看它從健康一路走向警告。",
        "Architected a VAE-based fault-detection framework in Python",
    )

    det = get_detector()
    meta = load_meta()
    v = load_validation()
    unit, cycle, sensors = load_test_readings()

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
            b1.button("載入這筆讀數", use_container_width=True,
                      on_click=_load_preset, args=(sensors, unit, cycle, meta, u, c))
            b2.button("載入最後一個 cycle", use_container_width=True,
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

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        if verdict.status == "Warning":
            st.error("### ⚠️ Warning\n建議安排檢查")
        else:
            st.success("### ✅ Healthy\n可繼續運轉")
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
        st.altair_chart((base + here).properties(height=380), use_container_width=True)
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
