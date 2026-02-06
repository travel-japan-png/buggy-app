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
    except Exception:
        st.error("データの読み込みに失敗しました。")
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
    for col in ['チェックイン', '開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']:
        if col not in df.columns:
            df[col] = False if col == 'チェックイン' else ""
    
    df['チェックイン'] = df['チェックイン'].fillna(False).astype(bool)
    df['大人人数'] = pd.to_numeric(df['大人人数'], errors='coerce').fillna(0).astype(int)
    df['小人人数'] = pd.to_numeric(df['小人人数'], errors='coerce').fillna(0).astype(int)
    df['総販売金額'] = pd.to_numeric(df['総販売金額'], errors='coerce').fillna(0).astype(int)
    
    # 車両・人数計算ロジック
    total_ppl = df['大人人数'] + df['小人人数']
    revenue = df['総販売金額']
    # 計算式: (総額 - 保険料500円×人数) / 車両単価4000円
    drivers = ((revenue - (500 * total_ppl)) / 4000).apply(lambda x: int(round(x)) if x > 0 else 0)
    passengers = (total_ppl - drivers).apply(lambda x: int(x) if x > 0 else 0)
    
    df['使用車両'] = passengers.apply(lambda x: f"【2人】{int(x)}台 " if x > 0 else "") + \
                     (drivers - passengers).clip(lower=0).apply(lambda x: f"【1人】{int(x)}台" if x > 0 else "")
    df['人数'] = df['大人人数'].astype(str) + "大 " + df['小人人数'].astype(str) + "小"
    df['_s2'] = passengers
    df['_s1'] = (drivers - passengers).clip(lower=0)
    
    df.insert(0, '状況', "未受付")
    df.loc[df['チェックイン'] == True, '状況'] = "✅受付済"
    
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])
        
    return df, s2_stock, s1_stock

full_df, stock_2s, stock_1s = load_and_calculate()

# --- 2. メイン画面表示 ---
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
st.caption("※「総販売金額」を変更して保存すると、車両台数が再計算されます。")

# 編集用列の定義（総販売金額を復活）
display_edit_cols = ['チェックイン', '開始時間', '顧客', '大人人数', '小人人数', '総販売金額', '使用車両']

edited_view = st.data_editor(
    full_df[display_edit_cols], 
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "チェックイン": st.column_config.CheckboxColumn("チェックイン", width="small"),
        "開始時間": st.column_config.TextColumn("開始時間"),
        "顧客": st.column_config.TextColumn("名前"),
        "大人人数": st.column_config.NumberColumn("大人", min_value=0, step=1),
        "小人人数": st.column_config.NumberColumn("小人", min_value=0, step=1),
        "総販売金額": st.column_config.NumberColumn("総額 (円)", min_value=0, format="%d"),
        "使用車両": st.column_config.TextColumn("計算上の車両", disabled=True),
    },
    key="editor",
    hide_index=True
)

if st.button("💾 変更を保存して全員に共有", type="primary", use_container_width=True):
    # 編集結果を全データに反映
    full_df['チェックイン'] = edited_view['チェックイン']
    full_df['開始時間'] = edited_view['開始時間']
    full_df['顧客'] = edited_view['顧客']
    full_df['大人人数'] = edited_view['大人人数']
    full_df['小人人数'] = edited_view['小人人数']
    full_df['総販売金額'] = edited_view['総販売金額']
    
    # 保存用列のみ抽出して更新
    save_cols = [c for c in full_df.columns if c not in ['状況', '使用車両', '人数', '_s2', '_s1']]
    conn.update(data=full_df[save_cols])
    st.cache_data.clear()
    st.success("保存完了！最新の金額に基づき再計算しました。")
    st.rerun()

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
        if str(idx) == time:
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
    
    st.dataframe(
        active_df[final_view_cols].style.apply(highlight_rows, axis=1),
        use_container_width=True,
        hide_index=True
    )
