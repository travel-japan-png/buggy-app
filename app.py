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
        # スプレッドシートを読み込む
        raw_df = conn.read(ttl=0)
    except Exception as e:
        st.error("スプレッドシートの読み込みに失敗しました。")
        st.stop()

    # 在庫データの読み込み
    s2_stock, s1_stock = 3, 3 
    try:
        stock_df = conn.read(worksheet="在庫設定", ttl=0)
        if not stock_df.empty:
            s2_stock = int(stock_df.iloc[0]['2人乗り'])
            s1_stock = int(stock_df.iloc[0]['1人乗り'])
    except:
        pass

    df = raw_df.copy()
    
    # 必須列の存在確認と型変換
    # 計算に必要な列
    num_cols = ['大人人数', '小人人数', '総販売金額']
    for col in num_cols:
        if col not in df.columns: df[col] = 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    if 'チェックイン' not in df.columns: df['チェックイン'] = False
    df['チェックイン'] = df['チェックイン'].fillna(False).astype(bool)
    
    if '開始時間' not in df.columns: df['開始時間'] = ""
    if '顧客' not in df.columns: df['顧客'] = ""
    if 'ステータス' not in df.columns: df['ステータス'] = "予約確定"

    # 車両・人数計算ロジック
    def calc_logic(row):
        t = row['大人人数'] + row['小人人数']
        r = row['総販売金額']
        if t == 0: return 0, 0
        # (総額 - 保険料500円×人数) / 車両単価4000円
        d = max(0, int(round((r - (500 * t)) / 4000)))
        p = max(0, t - d)
        return d, p

    calc_res = df.apply(calc_logic, axis=1)
    df['_drivers'] = [x[0] for x in calc_res]
    df['_passengers'] = [x[1] for x in calc_res]
    
    df['使用車両'] = df.apply(lambda row: 
        (f"【2人】{int(row['_passengers'])}台 " if row['_passengers'] > 0 else "") + \
        (f"【1人】{max(0, int(row['_drivers'] - row['_passengers']))}台" if row['_drivers'] > row['_passengers'] else ""), axis=1)
    
    df['人数'] = df['大人人数'].astype(str) + "大 " + df['小人人数'].astype(str) + "小"
    df['_s2'] = df['_passengers']
    df['_s1'] = (df['_drivers'] - df['_passengers']).clip(lower=0)
    
    df.insert(0, '状況', "未受付")
    df.loc[df['チェックイン'] == True, '状況'] = "✅受付済"
    
    # 時間順ソート
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])
        
    return df, s2_stock, s1_stock

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

# UIで表示する列
display_cols = ['チェックイン', '開始時間', '顧客', '大人人数', '小人人数', '総販売金額', '使用車両']

# 編集用エディタ (placeholderを削除)
edited_df = st.data_editor(
    full_df[display_cols], 
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
    # 元の全データのうち、編集画面にある列を更新する
    # 1. まず編集画面の内容をコピー
    save_data = edited_df.copy()
    
    # 2. スプレッドシートにあるべき「ステータス」列などが消えないように補完
    if 'ステータス' not in save_data.columns:
        save_data['ステータス'] = "予約確定"
    
    # 3. 計算用の一時列を削除して保存
    final_save_df = save_data.drop(columns=['使用車両'], errors='ignore')
    
    try:
        conn.update(data=final_save_df)
        st.cache_data.clear()
        st.success("保存完了！")
        st.rerun()
    except Exception as e:
        st.error(f"保存に失敗しました。スプレッドシートの列名が変わっていないか確認してください。")

# --- 4. 時間帯別の稼働合計 ---
active_df = full_df[full_df['ステータス']


