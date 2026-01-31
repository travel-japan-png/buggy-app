import streamlit as st
import pandas as pd

# --- 基本設定 ---
st.set_page_config(page_title="バギーツアー車両割り当てくん", layout="wide")
st.title("🚜 バギーツアー車両割り当てシミュレーター")

# --- サイドバー：在庫管理 ---
st.sidebar.header("本日の車両在庫")
stock_2s = st.sidebar.number_input("2人乗り在庫 (台)", value=3)
stock_1s = st.sidebar.number_input("1人乗り在庫 (台)", value=3)

# --- ロジック関数 ---
def solve_and_allocate(row):
    try:
        total_count = int(row['大人人数']) + int(row['小人人数'])
        total_amount = int(row['総販売金額'])
        
        # 運転者(x)と同乗者(y)を連立方程式で算出
        # 4500x + 500y = Amount / x + y = Count
        drivers = int((total_amount - (500 * total_count)) / 4000)
        passengers = total_count - drivers
        
        # 1台に1人以上の運転手が必要（運転手 < 同乗者はエラー）
        if drivers < passengers:
            return drivers, passengers, 0, 0, "⚠️ 運転手不足！"
        
        # 割り当て: 同乗者の数だけ2人乗りが必要
        needed_2s = passengers
        # 残った運転者が1人乗りに乗る
        needed_1s = drivers - passengers
        
        return drivers, passengers, needed_2s, needed_1s, "✅ OK"
    except:
        return 0, 0, 0, 0, "❌ データ異常"

# --- メイン画面：CSVアップロード ---
uploaded_file = st.file_uploader("Trunk ToolsからエクスポートしたCSVを選択してください", type="csv")

if uploaded_file:
    # CSV読み込み（エンコーディングはTrunk Toolsに合わせて調整）
    try:
        df = pd.read_csv(uploaded_file, encoding='cp932')
    except:
        df = pd.read_csv(uploaded_file, encoding='utf-8')
    
    # 必要な列の抽出と計算
    results = []
    for _, row in df.iterrows():
        if row['ステータス'] == 'キャンセル': continue
        
        d, p, n2, n1, stat = solve_and_allocate(row)
        results.append({
            "開始時間": row['開始時間'],
            "顧客名": row['顧客'],
            "運転手": d,
            "同乗者": p,
            "2人乗り割当": n2,
            "1人乗り割当": n1,
            "判定": stat
        })
    
    res_df = pd.DataFrame(results)

    # --- 時間帯別サマリー ---
    st.subheader("📊 時間帯別の稼働状況")
    summary = res_df.groupby("開始時間").agg({
        "2人乗り割当": "sum",
        "1人乗り割当": "sum"
    })
    
    # 在庫オーバーをチェック
    summary['2人乗り状況'] = summary['2人乗り割当'].apply(lambda x: f"{x}/{stock_2s} {'⚠️不足' if x > stock_2s else 'OK'}")
    summary['1人乗り状況'] = summary['1人乗り割当'].apply(lambda x: f"{x}/{stock_1s} {'⚠️不足' if x > stock_1s else 'OK'}")
    st.table(summary[['2人乗り状況', '1人乗り状況']])

    # --- 詳細リスト ---
    st.subheader("📋 予約詳細と車両配置")
    
    # ステータスによって色を変える
    def highlight_status(val):
        color = 'red' if '⚠️' in val or '❌' in val else 'black'
        return f'color: {color}'

    st.dataframe(res_df.style.applymap(highlight_status, subset=['判定']))

else:
    st.info("CSVファイルをアップロードしてください。サイドバーで在庫数を変更できます。")
