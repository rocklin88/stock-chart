"""
每日抓取股價、成交量，計算 KD (9,3,3) 與均線，
輸出互動式網頁 index.html（下拉選單切換股票）。

安裝：pip install -r requirements.txt
執行：python stock_kd_chart.py
結果：同資料夾產生 index.html，雙擊即可用瀏覽器開啟
"""
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from plotly.subplots import make_subplots

# ===== 設定區 =====
SYMBOLS = {                 # 代號: 顯示名稱（上市 .TW，上櫃 .TWO）
    "2330.TW": "台積電",
    "2317.TW": "鴻海",
    "2454.TW": "聯發科",
}
PERIOD = "6mo"              # 抓取區間
OUTPUT = "index.html"
SAVE_CSV = True             # 是否另存各股 CSV 到 data/
# ==================

UP, DOWN = "#e53935", "#2e7d32"   # 台股習慣：紅漲綠跌


def calc_kd(df, n=9):
    """台股常用 KD：RSV 9 日，K、D 以 1/3 權重平滑，初始值 50。"""
    low_n = df["Low"].rolling(n).min()
    high_n = df["High"].rolling(n).max()
    rsv = (df["Close"] - low_n) / (high_n - low_n) * 100
    k, d = 50.0, 50.0
    ks, ds = [], []
    for v in rsv:
        if pd.isna(v):
            ks.append(None)
            ds.append(None)
            continue
        k = 2 / 3 * k + 1 / 3 * v
        d = 2 / 3 * d + 1 / 3 * k
        ks.append(k)
        ds.append(d)
    df["K"], df["D"] = ks, ds
    return df


def fetch(symbol):
    df = yf.download(symbol, period=PERIOD, auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):  # 新版 yfinance 欄位處理
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    if df.empty:
        return df
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    return calc_kd(df)


def signal(df):
    """K 上穿 D 且 K<30 為黃金交叉；K 下穿 D 且 K>70 為死亡交叉。"""
    kd = df.dropna(subset=["K", "D"])
    if len(kd) < 2:
        return "資料不足"
    k0, d0 = kd["K"].iloc[-2], kd["D"].iloc[-2]
    k1, d1 = kd["K"].iloc[-1], kd["D"].iloc[-1]
    if k0 < d0 and k1 > d1 and k1 < 30:
        return "低檔黃金交叉"
    if k0 > d0 and k1 < d1 and k1 > 70:
        return "高檔死亡交叉"
    return "無明顯訊號"


def make_title(sym, name, df):
    last = df.iloc[-1]
    return (
        f"{name} {sym}　收盤 {last['Close']:.2f}　"
        f"K={last['K']:.1f} D={last['D']:.1f}　{signal(df)}"
    )


def main():
    data = {}
    for sym, name in SYMBOLS.items():
        df = fetch(sym)
        if df.empty:
            print(f"{sym}: 抓不到資料，略過")
            continue
        data[sym] = (name, df)
        if SAVE_CSV:
            os.makedirs("data", exist_ok=True)
            df.to_csv(f"data/{sym}.csv")
    if not data:
        raise SystemExit("沒有任何資料，未產生網頁")

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.55, 0.20, 0.25],
    )

    # 每檔股票 6 條線：K線、MA5、MA20、成交量、K、D
    traces_per_stock = 6
    for i, (sym, (name, df)) in enumerate(data.items()):
        show = i == 0
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name="K線",
            increasing_line_color=UP, decreasing_line_color=DOWN,
            visible=show), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["MA5"], name="MA5",
            line=dict(color="orange", width=1), visible=show), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["MA20"], name="MA20",
            line=dict(color="royalblue", width=1), visible=show), row=1, col=1)
        colors = [UP if c >= o else DOWN for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"], name="成交量",
            marker_color=colors, visible=show), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["K"], name="K",
            line=dict(color="red", width=1.3), visible=show), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["D"], name="D",
            line=dict(color="blue", width=1.3), visible=show), row=3, col=1)

    # 下拉選單：切換股票
    total = traces_per_stock * len(data)
    buttons = []
    for i, (sym, (name, df)) in enumerate(data.items()):
        vis = [False] * total
        for j in range(traces_per_stock):
            vis[i * traces_per_stock + j] = True
        buttons.append(dict(
            label=f"{name} {sym}", method="update",
            args=[{"visible": vis}, {"title": {"text": make_title(sym, name, df)}}],
        ))

    # 去除週末與休市日的空白
    all_dates = pd.DatetimeIndex(sorted(set().union(*[d.index for _, d in data.values()])))
    full = pd.date_range(all_dates.min(), all_dates.max(), freq="D")
    missing = [d.strftime("%Y-%m-%d") for d in full.difference(all_dates)]

    first_sym, (first_name, first_df) = next(iter(data.items()))
    updated = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    fig.update_layout(
        title={"text": make_title(first_sym, first_name, first_df)},
        updatemenus=[dict(
            buttons=buttons, direction="down", x=0.0, y=1.12,
            xanchor="left", yanchor="top",
        )],
        annotations=[dict(
            text=f"更新時間：{updated}（資料來源：Yahoo Finance，僅供參考）",
            x=1, y=-0.08, xref="paper", yref="paper",
            xanchor="right", showarrow=False, font=dict(size=11, color="gray"),
        )],
        height=800,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.04, x=1, xanchor="right"),
        margin=dict(t=110, b=60),
    )
    fig.update_xaxes(rangebreaks=[dict(values=missing)])
    fig.update_yaxes(title_text="價格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    fig.update_yaxes(title_text="KD", range=[0, 100], row=3, col=1)
    for level in (20, 80):
        fig.add_hline(y=level, line_dash="dash", line_color="gray",
                      line_width=0.8, row=3, col=1)

    # include_plotlyjs="cdn"：檔案小，需要網路載入 plotly.js
    fig.write_html(OUTPUT, include_plotlyjs="cdn", full_html=True,
                   config={"displaylogo": False, "responsive": True})
    print(f"已產生 {OUTPUT}（{len(data)} 檔股票）")


if __name__ == "__main__":
    main()
