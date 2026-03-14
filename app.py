import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_autorefresh import st_autorefresh

# --- 1. 基本設定 & 自動更新 ---
st.set_page_config(page_title="バギーツアー管理", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

conn = st.connection("gsheets", type=GSheetsConnection)

def load_and_calculate():
    try:
        raw_df = conn.read(ttl=0)
    except Exception as e:
        st.error(f"スプレッドシートの読み込みに失敗しました: {e}")
        st.stop()

    s2_stock, s1_stock = 3, 3 
    try:
        stock_df = conn.read(worksheet="在庫設定", ttl=0)
        if not stock_df.empty:
            s2_stock = int(stock_df.iloc[0]['2人乗り'])
            s1_stock = int(stock_df.iloc[0]['1人乗り'])
    except:
        pass

    df = raw_df.copy()
    
    # 必須列の型変換と補完
    num_cols = ['大人人数', '小人人数', '総販売金額']
    for col in num_cols:
        if col not in df.columns: df[col] = 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    if 'チェックイン' not in df.columns: df['チェックイン'] = False
    df['チェックイン'] = df['チェックイン'].fillna(False).astype(bool)
    if '開始時間' not in df.columns: df['開始時間'] = ""
    if '顧客' not in df.columns: df['顧客'] = ""
    if 'ステータス' not in df.columns: df['ステータス'] = "予約確定"

    # 車両計算ロジック（エラー回避を強化）
    def calc_logic(row):
        try:
            t = int(row['大人人数']) + int(row['小人人数'])
            r = int(row['総販売金額'])
            if t <= 0: return 0, 0
            # 運転手台数 = (総額 - 保険500*人数) / 4000
            d = max(0, int(round((r - (500 * t)) / 4000)))
            p = max(0, t - d)
            return d, p
        except:
            return 0, 0

    # 計算実行
    calc_results = df.apply(calc_logic, axis=1)
    
    # リスト内包表記でのエラーを避けるため、安全に列を作成
    df['_s2'] = [x[1] for x in calc_results]
    df['_s1'] = [max(0, x[0] - x[1]) for x in calc_results]
    
    df['使用車両'] = df.apply(lambda row: 
        (f"【2人】{int(row['_s2'])}台 " if row['_s2'] > 0 else "") + \
        (f"【1人】{int(row['_s1'])}台" if row['_s1'] > 0 else ""), axis=1)
    
    df['人数'] = df['大人人数'].astype(str) + "大 " + df['小人人数'].astype(str) + "小"
    
    df.insert(0, '状況', "未受付")
    df.loc[df['チェックイン'] == True, '状況'] = "✅受付済"
    
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])
        
    return df, s2_stock, s1_stock

# 読み込み実行
full_df, stock_2s, stock_1s = load_and_calculate()

# --- 2. メイン表示 ---
col_t1, col_t2 = st.columns([3, 1])
with col_t1:
    st.title("🚜 バギーツアー受付・車両管理")
with col_t2:
    st.write("") 
    if st.button("🔄 最新の情報に更新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.sidebar.header("⚙️ 車両在庫")
st.sidebar.metric("2人乗り在庫", f"{stock_2s} 台")
st.sidebar.metric("1人乗り在庫", f"{stock_1s} 台")

# --- 3. 予約編集・チェックイン ---
st.subheader("📋 予約編集・チェックイン")
display_cols = ['チェックイン', '開始時間', '顧客', '大人人数', '小人人数', '総販売金額', '使用車両']

edited_df = st.data_editor(
    full_df[display_cols], 
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "チェックイン": st.column_config.CheckboxColumn("チェックイン", width="small"),
        "大人人数": st.column_config.NumberColumn("大人", min_value=0, step=1),
        "小人人数": st.column_config.NumberColumn("小人", min_value=0, step=1),
        "総販売金額": st.column_config.NumberColumn("総額", min_value=0, format="%d"),
        "使用車両": st.column_config.TextColumn("車両(自動)", disabled=True),
    },
    key="editor",
    hide_index=True
)

if st.button("💾 変更を保存して全員に共有", type="primary", use_container_width=True):
    save_data = edited_df.copy()
    # 不要な列を削除して保存
    if '使用車両' in save_data.columns:
        save_data = save_data.drop(columns=['使用車両'])
    # ステータス補完
    if 'ステータス' not in save_data.columns:
        save_data['ステータス'] = "予約確定"
        
    try:
        conn.update(data=save_data)
        st.cache_data.clear()
        st.success("保存完了！")
        st.rerun()
    except Exception as e:
        st.error(f"保存に失敗しました: {e}")

# --- 4. 時間帯別の稼働合計 ---
active_df = full_df[full_df['ステータス'] != 'キャンセル'].copy()
st.divider()
st.subheader("📊 時間帯別の稼働合計")

target_times = ["9:00", "9:30", "10:00", "10:30", "14:00", "14:30", "15:00"]
summary = active_df.groupby("開始時間").agg({"_s2": "sum", "_s1": "sum"})

cols = st.columns(len(target_times))
for i, time in enumerate(target_times):
    s2_req, s1_req = 0, 0
    for idx in summary.index:
        if str(idx).strip() == time:
            s2_req = int(summary.loc[idx, '_s2'])
            s1_req = int(summary.loc[idx, '_s1'])
            break
    
    s1_overflow = max(0, s1_req - stock_1s)
    final_s1, final_s2 = s1_req - s1_overflow, s2_req + s1_overflow
    
    with cols[i]:
        st.write(f"🕒 **{time}**")
        s2_color = "normal" if final_s2 <= stock_2s else "inverse"
        st.metric("2人", f"{final_s2}/{stock_2s}", delta=int(stock_2s - final_s2), delta_color=s2_color)
        st.metric("1人", f"{final_s1}/{stock_1s}")

# --- 5. 現場用リスト ---
st.subheader("🔍 現場用・当日車両割当リスト")
final_view_cols = ['状況', '開始時間', '顧客', '人数', '使用車両']
if not active_df.empty:
    def highlight_rows(row):
        return ['background-color: #e6f3ff' if row['状況'] == "✅受付済" else '' for _ in row]
    st.dataframe(active_df[final_view_cols].style.apply(highlight_rows, axis=1), use_container_width=True, hide_index=True)
