import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_autorefresh import st_autorefresh

# --- 1. 基本設定 & スマホ向けCSS注入 ---
st.set_page_config(page_title="バギー現場管理", layout="wide")

# スマホでボタンをより大きく見せるためのカスタムCSS
st.markdown("""
    <style>
    /* 保存ボタンなどのメインボタンを太く大きく */
    .stButton > button {
        height: 3em;
        font-size: 1.2rem !important;
        font-weight: bold !important;
        border-radius: 10px;
        margin-bottom: 10px;
    }
    /* データエディタのセレクトボックスをタップしやすく */
    .stDataEditor div[data-testid="stTable"] {
        font-size: 1.1rem;
    }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=180000, key="datarefresh")
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. キャッシュ機能 (API制限対策) ---
@st.cache_data(ttl=60)
def get_raw_data():
    return conn.read(ttl=0)

@st.cache_data(ttl=300)
def get_stock_config():
    default_stock = {
        "9:00": [3, 3], "9:30": [3, 3], "10:00": [3, 3], "10:30": [3, 3],
        "14:00": [3, 3], "14:30": [3, 3], "15:00": [3, 3]
    }
    time_stocks = default_stock.copy()
    try:
        stock_df = conn.read(worksheet="在庫設定", ttl=0)
        if not stock_df.empty:
            for _, row in stock_df.iterrows():
                t_str = str(row['開始時間']).strip()
                time_stocks[t_str] = [int(row['2人乗り']), int(row['1人乗り'])]
    except:
        pass
    return time_stocks

def load_and_calculate():
    try:
        raw_df = get_raw_data()
    except Exception as e:
        if "429" in str(e):
            st.error("⚠️ 制限中：1分待って再起動してください")
            st.stop()
        st.error(f"読み込み失敗: {e}")
        st.stop()

    time_stocks = get_stock_config()
    df = raw_df.copy()
    
    if '状況' not in df.columns: df['状況'] = "未受付"
    df['状況'] = df['状況'].fillna("未受付")

    num_cols = ['大人人数', '小人人数', '総販売金額']
    for col in num_cols:
        if col not in df.columns: df[col] = 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    if '開始時間' not in df.columns: df['開始時間'] = ""
    if 'ステータス' not in df.columns: df['ステータス'] = "予約確定"

    def calc_logic(row):
        try:
            t = int(row['大人人数']) + int(row['小人人数'])
            r = int(row['総販売金額'])
            if t <= 0: return 0, 0
            d = max(0, int(round((r - (500 * t)) / 4000)))
            p = max(0, t - d)
            return d, p
        except: return 0, 0

    calc_results = df.apply(calc_logic, axis=1)
    df['_s2_req'] = [x[1] for x in calc_results]
    df['_s1_req'] = [max(0, x[0] - x[1]) for x in calc_results]
    
    df['使用車両'] = df.apply(lambda row: 
        (f"2人:{int(row['_s2_req'])} " if row['_s2_req'] > 0 else "") + \
        (f"1人:{int(row['_s1_req'])}" if row['_s1_req'] > 0 else ""), axis=1)
    
    df['人数'] = df['大人人数'].astype(str) + "大" + df['小人人数'].astype(str) + "小"
    
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])
        
    return df, time_stocks

full_df, time_stocks = load_and_calculate()

# --- 3. スマホ特化ヘッダー ---
st.title("🚜 現場管理")

# 更新ボタンを横幅いっぱいに
if st.button("🔄 最新に更新", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# --- 4. 予約編集 (タップ領域を確保) ---
st.subheader("📋 受付・編集")

display_edit_cols = ['状況', '開始時間', '顧客', '大人人数', '小人人数', '総販売金額', '使用車両']
status_options = ["未受付", "✅受付済", "🏁集合済"]

edited_df = st.data_editor(
    full_df[display_edit_cols], 
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "状況": st.column_config.SelectboxColumn("状況", options=status_options, width="medium"),
        "大人人数": st.column_config.NumberColumn("大", min_value=0, step=1, width="small"),
        "小人人数": st.column_config.NumberColumn("小", min_value=0, step=1, width="small"),
        "使用車両": st.column_config.TextColumn("車両", disabled=True),
    },
    key="editor",
    hide_index=True
)

# 最重要の保存ボタンをさらに強調
if st.button("💾 変更を保存して全員に共有", type="primary", use_container_width=True):
    save_data = edited_df.copy()
    if '使用車両' in save_data.columns:
        save_data = save_data.drop(columns=['使用車両'])
    if 'ステータス' not in save_data.columns:
        save_data['ステータス'] = "予約確定"
    try:
        conn.update(data=save_data)
        st.cache_data.clear()
        st.success("保存完了！")
        st.rerun()
    except Exception as e:
        st.error("保存失敗。少し待ってから再試行してください")

# --- 5. 時間帯別サマリー (スマホで見やすい2列表示) ---
st.divider()
st.subheader("📊 在庫")

target_times = ["9:00", "9:30", "10:00", "10:30", "14:00", "14:30", "15:00"]
active_df = full_df[full_df['ステータス'] != 'キャンセル'].copy()
summary = active_df.groupby("開始時間").agg({"_s2_req": "sum", "_s1_req": "sum"})

# スマホだと1列になりがちなので、あえて2列ずつ配置
for i in range(0, len(target_times), 2):
    row_cols = st.columns(2)
    for j in range(2):
        if i + j < len(target_times):
            time = target_times[i+j]
            stock_2s, stock_1s = time_stocks.get(time, [3, 3])
            req_2s, req_1s = 0, 0
            for idx in summary.index:
                if str(idx).strip() == time:
                    req_2s = int(summary.loc[idx, '_s2_req'])
                    req_1s = int(summary.loc[idx, '_s1_req'])
                    break
            overflow = max(0, req_1s
