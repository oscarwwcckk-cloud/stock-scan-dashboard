# -*- coding: utf-8 -*-
"""深色飛書風格樣式 + Plotly helpers。

配色與 chart helpers 移植自 futu-dashboard/dashboard.py(檔頭色票 + 圖表慣例)。
全暗色 CSS 復刻飛書卡片外觀,在 dashboard.py 入口與各頁 apply_dark_theme() 呼叫一次。
"""
import streamlit as st

# ── 配色(照範例圖:橘/藍/綠 + 深色底)────────────────────────────────
BG    = "#14171F"   # 頁面底色
CARD  = "#1E222B"   # 卡片底色
GRID  = "#2A2F3A"   # 格線
TXT   = "#FFFFF0"   # 文字(象牙白 ivory)
SUB   = "#E8E4D0"   # 次要文字(淡象牙白)
ORANGE = "#F5A623"
BLUE   = "#5B8FF9"
GREEN  = "#2DD4A7"
RED    = "#F5455C"
TEAL   = "#39C5CF"

# Plotly 圖表設定:一律隱藏右上角工具列;所有圖:滾輪縮放、取消雙擊還原
PLOTLY_CFG = {"displayModeBar": False, "scrollZoom": True, "doubleClick": False}
PLOTLY_CFG_LINE = PLOTLY_CFG


def _name_hover(fig):
    """讓 hover 卡片顯示「名稱:數值」。unified 線型圖已自動顯示名稱,略過。"""
    if fig.layout.hovermode == "x unified":
        return fig
    for t in fig.data:
        tt = t.type
        if tt == "pie":
            t.hovertemplate = "%{label}:%{value} (%{percent})<extra></extra>"
        elif tt == "heatmap":
            continue  # 已用自訂 text 呈現
        elif tt == "histogram":
            t.hovertemplate = (t.name or "count") + ":%{y}<extra></extra>"
        elif tt in ("bar", "scatter", "scattergl"):
            horiz = getattr(t, "orientation", None) == "h"
            val = "%{x}" if horiz else "%{y}"
            lbl = t.name or ("%{y}" if horiz else "%{x}")
            if t.hovertemplate:
                ht = t.hovertemplate
                if not ht.startswith(lbl):
                    ht = lbl + ":" + ht
                if "<extra>" not in ht:
                    ht += "<extra></extra>"
                t.hovertemplate = ht
            else:
                t.hovertemplate = lbl + ":" + val + "<extra></extra>"
    return fig


def _pan_zoom(fig):
    """圖內拖曳=平移(dragmode=pan);滾輪=縮放;拖曳 x/y 軸=重縮該軸。"""
    fig.update_layout(dragmode="pan")
    fig.update_xaxes(fixedrange=False)
    fig.update_yaxes(fixedrange=False)
    return fig


def _chart_cfg(fig):
    """所有圖統一互動 + hover。回傳要傳給 st.plotly_chart 的 config。"""
    _name_hover(fig)
    _pan_zoom(fig)
    return PLOTLY_CFG


def line_hover(fig):
    """線型圖統一呈現:x-unified 資訊卡 + 細的半透明十字線。"""
    fig.update_layout(
        hovermode="x unified",
        hoverlabel=dict(bgcolor=CARD, font=dict(color=TXT, size=10),
                        bordercolor=GRID, namelength=-1))
    spike = dict(showspikes=True, spikethickness=1, spikedash="dot",
                 spikecolor="rgba(232,228,208,0.45)")
    fig.update_xaxes(spikemode="across", spikesnap="cursor", **spike)
    fig.update_yaxes(**spike)
    return fig


def kpi_card(label, value, sub="", value_color=None):
    """一張深色 KPI 卡(用 st.markdown HTML)。value_color 可選 ORANGE/GREEN/RED 等。"""
    vc = value_color or TXT
    st.markdown(
        f'<div class="kpi"><div class="lbl">{label}</div>'
        f'<div class="val" style="color:{vc}">{value}</div>'
        f'<div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )


def apply_dark_theme():
    """注入全域深色 CSS。在 dashboard.py 入口與各頁頂端呼叫(幂等)。"""
    st.markdown(f"""
<style>
  .stApp {{ background:{BG}; }}
  section[data-testid="stSidebar"] {{ background:{CARD}; }}
  #MainMenu, footer {{ visibility:hidden; }}
  header[data-testid="stHeader"] {{ background:transparent !important; }}
  [data-testid="stToolbar"] {{ background:transparent !important; }}
  [data-testid="stDecoration"] {{ display:none !important; }}
  .stApp, .stApp p, .stApp span, .stApp label, .stApp div,
  h1,h2,h3,h4,h5,h6, .stMarkdown, .stCaption,
  section[data-testid="stSidebar"] * {{ color:{TXT}; }}
  .stApp .stCaption, [data-testid="stCaptionContainer"] {{ color:{SUB} !important; }}
  .block-container {{ padding-top:1.0rem; padding-bottom:1rem; max-width:1600px; }}

  /* KPI 卡 */
  .kpi {{ background:{CARD}; border-radius:14px; padding:14px 18px;
          border:1px solid {GRID}; min-height:112px; }}
  .kpi .lbl {{ color:{SUB}; font-size:13px; margin-bottom:4px; line-height:1.2; }}
  .kpi .val {{ color:{TXT}; font-size:23px; font-weight:700; line-height:1.15;
               white-space:nowrap; }}
  .kpi .sub {{ font-size:12px; margin-top:4px; line-height:1.2; }}

  .tile {{ background:{CARD}; border-radius:14px; padding:14px 16px 4px 16px;
           border:1px solid {GRID}; margin-bottom:14px; }}
  .tile h4 {{ color:{TXT}; font-size:15px; margin:0 0 2px 0; font-weight:600; }}

  /* 側欄按鈕:深底象牙白字(深色主題下看得清) */
  section[data-testid="stSidebar"] .stButton button {{
      background:{GRID} !important; border:1px solid #3A414F !important;
      color:{TXT} !important; padding:5px 8px !important; }}
  section[data-testid="stSidebar"] .stButton button * {{
      color:{TXT} !important; -webkit-text-fill-color:{TXT} !important;
      font-size:12px !important; }}
  section[data-testid="stSidebar"] .stButton button:hover {{
      border-color:{BLUE} !important; background:#333A47 !important; }}

  /* 分頁列(深色飛書風):底線分隔、選中象牙白+主色底線 */
  [data-testid="stTabs"] [data-baseweb="tab-list"] {{
      gap:6px; border-bottom:1px solid {GRID}; }}
  [data-testid="stTabs"] [data-baseweb="tab"] {{
      background:transparent; padding:6px 14px; }}
  [data-testid="stTabs"] [data-baseweb="tab"] p {{
      color:{SUB} !important; font-size:15px; font-weight:600; }}
  [data-testid="stTabs"] [aria-selected="true"] p {{
      color:{TXT} !important; }}
  [data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
      background:{BLUE}; }}

  /* 手機版:並排欄位改上下堆疊 */
  @media (max-width:900px) {{
      [data-testid="stHorizontalBlock"] {{ flex-direction:column; }}
      [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
          width:100% !important; flex:1 1 100% !important; }}
      .block-container {{ padding-left:0.6rem; padding-right:0.6rem; }}
  }}
</style>""", unsafe_allow_html=True)
