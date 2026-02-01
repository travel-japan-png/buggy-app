import streamlit as st
import pandas as pd
import io

# --- 1. 合言葉チェック (以前のものを継続) ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "your-password-123":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("パスワードが違います")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- 2. 基本設定 ---
st.set_page_config(page_title="バギーツアー管理くん", layout="wide")
st.title("🚜 バギーツアー車両管理・編集ツール")

# サイドバー：在庫管理
st.sidebar.header("本日の車両在庫")
stock_2s = st.sidebar.number_input("2人乗り在庫 (台)", value=3, min_value=0)
stock_1s = st.sidebar.number_input("1人乗り在庫 (台)", value=3, min_value=0)

# --- 3. 計算・並べ替え関数 ---
def calculate_details(df):
    df = df.copy()
    # 必要な列が欠けていれば作成
    required_cols = ['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    # 数値型へ変換（文字が混じっていても0にする）
    df['大人人数'] = pd.to_numeric(df['大人人数'], errors='coerce').fillna(0)
    df['小人人数'] = pd.to_numeric(df['小人人数'], errors='coerce').fillna(0)
    df['総販売金額'] = pd.to_numeric(df['総販売金額'], errors='coerce').fillna(0)
    
    # 開始時間で並べ替え
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])

    # 連立方程式
    total_count = df['大人人数'] + df['小人人数']
    df['運転手'] = ((df['総販売金額'] - (500 * total_count)) / 4000).apply(lambda x: int(x) if x > 0 else 0)
    df['同乗者'] = (total_count - df['運転手']).apply(lambda x: int(x) if x > 0 else 0)
    
    df['2人乗り割当'] = df['同乗者']
    df['1人乗り割当'] = (df['運転手'] - df['同乗者']).clip(lower=0)
    
    df['判定'] = "✅ OK"
    mask_error = (df['運転手'] < df['同乗者']) & (total_count > 0)
    df.loc[mask_error, '判定'] = "⚠️ 運転手不足！"
    df.loc[(total_count > 0) & (df['総販売金額'] == 0), '判定'] = "❓ 金額未入力"
    df.loc[total_count == 0, '判定'] = "-"
    
    return df

# --- 4. メイン処理：CSV読み込み ---
uploaded_file = st.file_uploader("Trunk ToolsのCSVをアップロード", type="csv")

# データのベースを作成
if uploaded_file is not None:
    # 読み込みエラーを防ぐため複数のエンコーディングを試す
    bytes_data = uploaded_file.getvalue()
    try:
        raw_df = pd.read_csv(io.BytesIO(bytes_data), encoding='cp932')
    except:
        raw_df = pd.read_csv(io.BytesIO(bytes_data), encoding='utf-8-sig') # BOM付きUTF-8対応
    
    # 読み込んだデータの列名を整理（余計なスペースなどを消す）
    raw_df.columns = raw_df.columns.str.strip()
    base_df = raw_df
else:
    base_df = pd.DataFrame(columns=['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス'])

# --- 5. 編集エディタ ---
st.subheader("📋 予約リストの編集・追加")
edited_df = st.data_editor(
    base_df[['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']],
    num_rows="dynamic",
    use_container_width=True,
    key="editor"
)

# --- 6. 結果の表示 ---
if not edited_df.empty:
    res_df = calculate_details(edited_df)
    active_df = res_df[res_df['ステータス'] != 'キャンセル']

    st.divider()
    st.subheader("📊 時間帯別の稼働状況")
    summary = active_df.groupby("開始時間").agg({"2人乗り割当": "sum", "1人乗り割当": "sum"})
    
    if not summary.empty:
        cols = st.columns(3)
        for i, time in enumerate(summary.index):
            s2, s1 = summary.loc[time, '2人乗り割当'], summary.loc[time, '1人乗り割当']
            with cols[i % 3]:
                st.write(f"### 🕒 {time}")
                st.metric("2人乗り", f"{int(s2)} / {stock_2s}", delta=int(stock_2s - s2))
                st.metric("1人乗り", f"{int(s1)} / {stock_1s}", delta=int(stock_1s - s1))
    
    st.subheader("🔍 割り当て詳細")
    st.dataframe(res_df.style.apply(lambda row: ['background-color: #ffcccc' if "⚠️" in str(row['判定']) else '' for _ in row], axis=1), use_container_width=True)
