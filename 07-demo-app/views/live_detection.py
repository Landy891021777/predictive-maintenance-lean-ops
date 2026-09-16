"""即時判讀：拉動感測器，當場看模型怎麼判。

這一頁跑的是**真的模型**，不是預先算好的結果重播。
權重來自 vae_model.pth，以純 NumPy 重算（build/verify_numpy_path.py 已驗證
這條路徑能逐格重現 model_validation.md 的 85% 與混淆矩陣）。
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

KEY = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]
OTHER_VARYING = [6, 20, 21]
STATE_KEY = "sensor_values"


def _init_state(meta: dict, sensors: np.ndarray, unit: np.ndarray, cycle: np.ndarray) -> None:
    if STATE_KEY not in st.session_state:
        # 預設載入 ENG-001 的第一個 cycle（全新引擎，應判為 Healthy）
        first = np.where((unit == 1) & (cycle == 1))[0][0]
        st.session_state[STATE_KEY] = sensors[first].astype(float).copy()
        st.session_state["loaded_label"] = "ENG-001 · cycle 1"


def _load_preset(sensors, unit, cycle, u: int, c: int) -> None:
    hit = np.where((unit == u) & (cycle == c))[0]
    if len(hit):
        st.session_state[STATE_KEY] = sensors[hit[0]].astype(float).copy()
        st.session_state["loaded_label"] = f"ENG-{u:03d} · cycle {c}"


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
    _init_state(meta, sensors, unit, cycle)

    # ---------- 載入真實讀數 ----------
    with st.container(border=True):
        st.markdown("**載入真實引擎讀數**")
        c1, c2, c3 = st.columns([2, 2, 3])
        engines = np.unique(unit)
        with c1:
            u = st.selectbox("引擎", engines, format_func=lambda x: f"ENG-{x:03d}")
        with c2:
            cycles = cycle[unit == u]
            c = st.slider("Cycle", int(cycles.min()), int(cycles.max()), int(cycles.min()))
        with c3:
            st.write("")
            b1, b2 = st.columns(2)
            b1.button("載入這筆讀數", use_container_width=True,
                      on_click=_load_preset, args=(sensors, unit, cycle, int(u), int(c)))
            b2.button("載入最後一個 cycle", use_container_width=True,
                      on_click=_load_preset,
                      args=(sensors, unit, cycle, int(u), int(cycles.max())))
        st.caption(f"目前載入：**{st.session_state['loaded_label']}**"
                   "（手動調整滑桿後即偏離原始讀數）")

    # ---------- 感測器輸入 ----------
    stats = meta["sensor_stats"]
    values = st.session_state[STATE_KEY]

    st.markdown("#### 感測器輸入")
    st.caption("以下 12 顆是本案的特徵選擇（見 `航太維修專案 背景.md`）；模型內部仍吃全部 21 顆。")
    cols = st.columns(3)
    for i, s in enumerate(KEY):
        name = f"s_{s}"
        stat = stats[name]
        lo, hi = float(stat["p01"]), float(stat["p99"])
        span = hi - lo
        with cols[i % 3]:
            values[s - 1] = st.slider(
                f"Sensor {s}",
                min_value=round(lo - span * 0.25, 4),
                max_value=round(hi + span * 0.25, 4),
                value=float(np.clip(values[s - 1], lo - span * 0.25, hi + span * 0.25)),
                step=round(span / 200, 6) or 0.001,
                key=f"sl_{s}",
                help=f"訓練資料 p01–p99：{lo:.4g} – {hi:.4g}",
            )

    with st.expander("其餘 9 顆感測器"):
        cols2 = st.columns(3)
        for i, s in enumerate(OTHER_VARYING):
            name = f"s_{s}"
            stat = stats[name]
            lo, hi = float(stat["p01"]), float(stat["p99"])
            span = hi - lo or 1.0
            with cols2[i % 3]:
                values[s - 1] = st.slider(
                    f"Sensor {s}",
                    min_value=round(lo - span * 0.25, 4),
                    max_value=round(hi + span * 0.25, 4),
                    value=float(np.clip(values[s - 1], lo - span * 0.25, hi + span * 0.25)),
                    step=round(span / 200, 6) or 0.001,
                    key=f"sl_{s}",
                )
        st.caption(
            "以下 6 顆在 FD001 全程為定值，沒有資訊量，因此不提供調整："
            + "、".join(meta["constant_sensors"])
        )

    st.session_state[STATE_KEY] = values

    # ---------- 判讀 ----------
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
        st.caption("灰底散點為 support set（抽樣 4,000 點），藍色菱形是目前這筆讀數的位置。")

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
