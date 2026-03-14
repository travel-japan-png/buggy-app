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
        st.error(f"メインシートの読み込みに失敗: {e}")
        st.stop()

    # 在庫設定の読み込み（時間帯別）
    # デフォルト値（シートがない場合用）
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
        st.warning("「在庫設定」シートが読み込めないため一律3台で計算します。")

    df = raw_df.copy()
    
    # 必須列の型変換
    num_cols = ['大人人数', '小人人数', '総販売金額']
    for col in num_cols:
        if col not in df.columns: df[col] = 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    if 'チェックイン' not in df.columns: df['チェックイン'] = False
    df['チェックイン'] = df['チェックイン'].fillna(False).astype(bool)
    if '開始時間' not in df.columns: df['開始時間'] = ""
    if 'ステータス' not in df.columns: df['ステータス'] = "予約確定"

    # 車両計算
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
    df['_s2_req'] = [x[1] for x in calc_results] # 2人乗りの必要数
    df['_s1_req'] = [max(0, x[0] - x[1]) for x in calc_results] # 1人乗りの必要数
    
    df['使用車両'] = df.apply(lambda row: 
        (f"【2人】{int(row['_s2_req'])}台 " if row['_s2_req'] > 0 else "") + \
        (f"【1人】{int(row['_s1_req'])}台" if row['_s1_req'] > 0 else ""), axis=1)
    
    df['人数'] = df['大人人数'].astype(str) + "大 " + df['小人人数'].astype(str) + "小"
    df.insert(0, '状況', "未受付")
    df.loc[df['チェックイン'] == True, '状況'] = "✅受付済"
    
    return df, time_stocks

full_df, time_stocks = load_and_calculate()

# --- 2. メイン表示 ---
st.title("🚜 バギーツアー受付・車両管理")

if st.button("🔄 最新の情報に更新"):
    st.cache_data.clear()
    st.rerun()

# --- 3. 予約編集 ---
st.subheader("📋 予約編集・チェックイン")
display_cols = ['チェックイン', '開始時間', '顧客', '大人人数', '小人人数', '総販売金額', '使用車両']
edited_df = st.data_editor(full_df[display_cols], num_rows="dynamic", use_container_width=True, hide_index=True)

if st.button("💾 変更を保存", type="primary"):
    save_data = edited_df.drop(columns=['使用車両'], errors='ignore')
    save_data['ステータス'] = "予約確定"
    conn.update(data=save_data)
    st.cache_data.clear()
    st.rerun()

# --- 4. 時間帯別の稼働合計 (可変在庫対応) ---
active_df = full_df[full_df['ステータス'] != 'キャンセル'].copy()
st.divider()
st.subheader("📊 時間帯別の在庫状況")

target_times = ["9:00", "9:30", "10:00", "10:30", "14:00", "14:30", "15:00"]
summary = active_df.groupby("開始時間").agg({"_s2_req": "sum", "_s1_req": "sum"})

cols = st.columns(len(target_times))
for i, time in enumerate(target_times):
    # その時間の在庫数を取得
    stock_2s, stock_1s = time_stocks.get(time, [3, 3])
    
    # 必要数を取得
    req_2s, req_1s = 0, 0
    for idx in summary.index:
        if str(idx).strip() == time:
            req_2s = int(summary.loc[idx, '_s2_req'])
            req_1s = int(summary.loc[idx, '_s1_req'])
            break
    
    # 1人乗り不足分を2人乗りでカバーする計算
    overflow_1s = max(0, req_1s - stock_1s)
    final_1s = req_1s - overflow_1s
    final_2s = req_2s + overflow_1s
    
    with cols[i]:
        st.write(f"🕒 **{time}**")
        # 在庫オーバーで赤文字
        s2_color = "normal" if final_2s <= stock_2s else "inverse"
        st.metric("2人乗り", f"{final_2s}/{stock_2s}", delta=int(stock_2s - final_2s), delta_color=s2_color)
        st.metric("1人乗り", f"{final_1s}/{stock_1s}")

# --- 5. 当日リスト ---
st.subheader("🔍 当日車両割当リスト")
final_view_cols = ['状況', '開始時間', '顧客', '人数', '使用車両']
st.dataframe(active_df[final_view_cols], use_container_width=True, hide_index=True)
