"""
Instagram own-account performance analysis page.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone


def render():
    st.title("📸 Instagram 成效分析")
    st.caption("自家帳號貼文成效、觸及率趨勢與最佳發文時段")

    try:
        from db.database import get_accounts, get_posts, get_metrics, get_latest_analysis
    except ImportError as e:
        st.error(f"資料庫載入失敗：{e}")
        return

    own_accounts = get_accounts(platform="instagram", account_type="own")
    threads_own = get_accounts(platform="threads", account_type="own")
    all_own = own_accounts + threads_own

    if not all_own:
        st.info("尚未設定自家帳號。請至「⚙️ 設定」頁面完成帳號連接。")
        return

    # Account selector
    account_map = {f"@{a['username']} ({a['platform']})": a for a in all_own}
    selected_label = st.selectbox("選擇帳號", list(account_map.keys()))
    selected_account = account_map[selected_label]

    days = st.slider("分析時間範圍（天）", min_value=7, max_value=90, value=30)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    posts = get_posts(account_id=selected_account["id"], limit=200, since=since)
    metrics = get_metrics(account_id=selected_account["id"], days=days)

    if not posts and not metrics:
        st.info(f"過去 {days} 天內無數據。請先執行數據抓取。")
        return

    # ── Account KPIs ──────────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4 = st.columns(4)

    follower_count = selected_account.get("follower_count", 0)
    follower_delta = 0
    if metrics and len(metrics) >= 2:
        follower_delta = metrics[0].get("follower_count", 0) - metrics[-1].get("follower_count", 0)

    df_posts = pd.DataFrame(posts) if posts else pd.DataFrame()
    avg_er = df_posts["engagement_rate"].mean() if not df_posts.empty else 0
    total_reach = df_posts["reach"].sum() if not df_posts.empty and "reach" in df_posts.columns else 0

    with col1:
        st.metric("粉絲數", f"{follower_count:,}", delta=f"+{follower_delta}" if follower_delta else None)
    with col2:
        st.metric("分析貼文數", len(posts))
    with col3:
        st.metric("平均互動率", f"{avg_er:.2f}%")
    with col4:
        st.metric("總觸及人數", f"{int(total_reach):,}")

    st.divider()

    # ── Metrics trend ─────────────────────────────────────────────────────────
    if metrics:
        st.subheader("📈 粉絲與觸及趨勢")
        df_m = pd.DataFrame(metrics)
        df_m["metric_date"] = pd.to_datetime(df_m["metric_date"])
        df_m = df_m.sort_values("metric_date")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**粉絲成長**")
            st.line_chart(df_m.set_index("metric_date")["follower_count"])
        with col2:
            if "total_reach" in df_m.columns:
                st.markdown("**每日觸及人數**")
                st.line_chart(df_m.set_index("metric_date")["total_reach"])

    st.divider()

    # ── Post type comparison ──────────────────────────────────────────────────
    if not df_posts.empty:
        st.subheader("📊 內容格式成效比較")
        df_posts["engagement_rate"] = pd.to_numeric(df_posts["engagement_rate"], errors="coerce").fillna(0)
        df_posts["like_count"] = pd.to_numeric(df_posts["like_count"], errors="coerce").fillna(0)

        col1, col2 = st.columns(2)
        with col1:
            type_er = df_posts.groupby("post_type")["engagement_rate"].mean().sort_values(ascending=False)
            st.markdown("**各格式平均互動率**")
            st.bar_chart(type_er)
        with col2:
            type_count = df_posts["post_type"].value_counts()
            st.markdown("**各格式發文數量**")
            st.bar_chart(type_count)

        st.divider()

        # ── Best posting time ─────────────────────────────────────────────────
        st.subheader("⏰ 最佳發文時段")
        df_posts["published_at"] = pd.to_datetime(df_posts["published_at"], utc=True, errors="coerce")
        df_time = df_posts.dropna(subset=["published_at"]).copy()
        if not df_time.empty:
            df_time["hour"] = df_time["published_at"].dt.hour
            df_time["weekday"] = df_time["published_at"].dt.day_name()
            weekday_zh = {
                "Monday": "週一", "Tuesday": "週二", "Wednesday": "週三",
                "Thursday": "週四", "Friday": "週五", "Saturday": "週六", "Sunday": "週日"
            }
            df_time["weekday_zh"] = df_time["weekday"].map(weekday_zh)

            col1, col2 = st.columns(2)
            with col1:
                hour_er = df_time.groupby("hour")["engagement_rate"].mean()
                st.markdown("**最佳發文時段（依互動率）**")
                st.bar_chart(hour_er)
                best_hour = int(hour_er.idxmax())
                st.success(f"🏆 黃金發文時間：{best_hour:02d}:00")
            with col2:
                day_er = df_time.groupby("weekday_zh")["engagement_rate"].mean()
                st.markdown("**最佳發文星期**")
                st.bar_chart(day_er)

        st.divider()

        # ── Top posts ─────────────────────────────────────────────────────────
        st.subheader("🏆 最佳貼文 Top 10")
        top_posts = df_posts.nlargest(10, "engagement_rate")[
            ["post_type", "content", "like_count", "comment_count",
             "reach", "engagement_rate", "published_at", "permalink"]
        ].copy()
        top_posts["content"] = top_posts["content"].str[:60] + "…"
        top_posts.columns = ["格式", "內容預覽", "讚數", "留言數", "觸及", "互動率(%)", "發布時間", "連結"]
        top_posts["互動率(%)"] = top_posts["互動率(%)"].round(3)
        st.dataframe(top_posts, use_container_width=True, hide_index=True)

    st.divider()

    # ── AI own account analysis ───────────────────────────────────────────────
    st.subheader("🤖 AI 成效分析報告")
    latest = get_latest_analysis("own_account")
    if latest:
        try:
            data = json.loads(latest["result_json"])
            overall = data.get("overall_performance", {})
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**整體評估**")
                st.info(overall.get("insights", ""))
                st.markdown("**具體改善行動**")
                for item in data.get("action_items", []):
                    priority = item.get("priority", "")
                    action = item.get("action", "")
                    icon = "🔴" if priority == "高" else "🟡" if priority == "中" else "🟢"
                    st.markdown(f"{icon} **{priority}優先**：{action}")
            with col2:
                st.markdown("**最佳發文時段建議**")
                opt_times = data.get("optimal_posting_times", {})
                st.markdown(f"- 最佳天：{', '.join(opt_times.get('best_days', []))}")
                st.markdown(f"- 最佳時段：{', '.join(opt_times.get('best_hours', []))}")
                st.markdown(f"- 推論依據：{opt_times.get('reasoning', '')}")
            st.caption(f"分析時間：{latest['created_at'][:16]}")
        except Exception:
            st.markdown(latest.get("summary_text", ""))
    else:
        st.info("尚無 AI 分析報告。")

    if st.button("🔄 立即執行 AI 成效分析", key="run_own_analysis"):
        with st.spinner("分析中，請稍候…"):
            try:
                from analysis.claude_analyzer import analyze_own_account
                from db.database import save_analysis, get_metrics as gm
                result = analyze_own_account(posts, metrics)
                save_analysis(
                    analysis_type="own_account",
                    result_json=json.dumps(result, ensure_ascii=False),
                    summary_text=result.get("overall_performance", {}).get("insights", ""),
                )
                st.success("✅ 分析完成！請重新整理頁面。")
                st.rerun()
            except Exception as exc:
                st.error(f"分析失敗：{exc}")


if __name__ == "__main__":
    render()
