import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_autorefresh import st_autorefresh

# --- 1. 合言葉チェック (リフレッシュ耐性版) ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    def password_entered():
        if st.session_state["password_input"] == "tomamubuggy":
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if not st.session_state.get("password_correct", False):
        st.title("🔒 認証が必要です")
        st.text_input("合言葉を入力してください", type="password", on_change=password_entered, key="password_input")
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("合言葉が違います")
        return False
    return True

if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not check_password():
    st.stop()

# --- 2. 基本設定 & 自動更新 ---
st.set_page_config(page_title="バギーツアー管理", layout="wide")
st_autorefresh(interval=180000, key="datarefresh") # 3分更新

# --- サイドバー：車両在庫の設定 ---
st.sidebar.header("⚙️ 本日の車両在庫設定")
st.sidebar.write("その日の稼働可能台数を入力してください")
stock_2s = st.sidebar.number_input("2人乗り在庫 (台)", min_value=0, value=3, step=1)
stock_1s = st.sidebar.number_input("1人乗り在庫 (台)", min_value=0, value=3, step=1)
st.sidebar.divider()
st.sidebar.caption("※ここで設定した台数を超えると、サマリー欄が赤く表示されます（delta機能）")

# メインタイトルと更新ボタン
col_t1, col_t2 = st.columns([3, 1])
with col_t1:
    st.title("🚜 車両割当 & 受付管理")
with col_t2:
    st.write("") 
    if st.button("🔄 最新の情報に更新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 3. データ読み込みと計算 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    df = conn.read(ttl=0)
    if 'チェックイン' not in df.columns:
        df['チェックイン'] = False
    df['チェックイン'] = df['チェックイン'].fillna(False).astype(bool)
    
    # 「チェックイン」列を左端に
    cols = ['チェックイン'] + [c for c in df.columns if c != 'チェックイン']
    df = df[cols]
    return df

def calculate_details(df):
    df = df.copy()
    for col in ['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']:
        if col not in df.columns: df[col] = ""

    df['大人人数'] = pd.to_numeric(df['大人人数'], errors='coerce').fillna(0).astype(int)
    df['小人人数'] = pd.to_numeric(df['小人人数'], errors='coerce').fillna(0).astype(int)
    
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])
    
    total = df['大人人数'] + df['小人人数']
    revenue = pd.to_numeric(df['総販売金額'], errors='coerce').fillna(0)
    drivers = ((revenue - (500 * total)) / 4000).apply(lambda x: int(x) if x > 0 else 0)
    passengers = (total - drivers).apply(lambda x: int(x) if x > 0 else 0)
    
    df['使用車両'] = passengers.apply(lambda x: f"【2人】{int(x)}台 " if x > 0 else "") + \
                     (drivers - passengers).clip(lower=0).apply(lambda x: f"【1人】{int(x)}台" if x > 0 else "")
    
    df['_s2'] = passengers
    df['_s1'] = (drivers - passengers).clip(lower=0)
    
    df.insert(0, '状況', "未受付")
    df.loc[df['チェックイン'] == True, '状況'] = "✅受付済"
    df.loc[(drivers < passengers) & (total > 0), '状況'] = "⚠️不足"
    
    return df

# --- 4. メイン表示 ---
df_raw = load_data()

st.subheader("📋 予約入力・受付編集")
edited_df = st.data_editor(
    df_raw,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "チェックイン": st.column_config.CheckboxColumn(
            "チェックイン",
            width="small",
            default=False
        )
    },
    key="editor"
)

if st.button("💾 変更を保存して全員に共有", type="primary", use_container_width=True):
    conn.update(data=edited_df)
    st.cache_data.clear()
    st.success("保存完了！")
    st.rerun()

# --- 5. 結果表示 ---
if not edited_df.empty:
    res_df = calculate_details(edited_df)
    active_df = res_df[res_df['ステータス'] != 'キャンセル'].copy()

    st.divider()
    st.subheader("📊 時間帯別の稼働合計")
    summary = active_df.groupby("開始時間").agg({"_s2": "sum", "_s1": "sum"})
    
    if not summary.empty:
        cols = st.columns(4)
        for i, time in enumerate(summary.index):
            if str(time).strip() in ["", "NaT"]: continue
            s2, s1 = summary.loc[time, '_s2'], summary.loc[time, '_s1']
            with cols[i % 4]:
                st.write(f"🕒 **{time}**")
                # 在庫に対する不足分を赤色で表示するdelta機能付き
                st.metric("2人乗り", f"{int(s2)} / {stock_2s}", delta=int(stock_2s - s2), delta_color="normal")
                st.metric("1人乗り", f"{int(s1)} / {stock_1s}", delta=int(stock_1s - s1), delta_color="normal")

    st.subheader("🔍 現場用・当日車両割当リスト")
    display_cols = ['状況', '開始時間', '顧客', '大人人数', '小人人数', '使用車両']
    
    if not active_df.empty:
        def highlight_rows(row):
            return ['background-color: #e6f3ff' if row['状況'] == "✅受付済" else '' for _ in row]
        
        st.dataframe(
            active_df[display_cols].style.apply(highlight_rows, axis=1),
            use_container_width=True,
            hide_index=True
        )

