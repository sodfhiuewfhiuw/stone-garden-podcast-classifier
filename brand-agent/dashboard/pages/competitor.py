"""
Competitor monitoring dashboard page.
Shows competitor post analytics, hashtag analysis, and AI insights.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from collections import Counter


def render():
    st.title("🔍 競品監控")
    st.caption("追蹤競品帳號的發文規律、互動表現與內容策略")

    try:
        from db.database import get_accounts, get_posts, get_latest_analysis
    except ImportError as e:
        st.error(f"資料庫載入失敗：{e}")
        return

    competitor_accounts = get_accounts(platform="threads", account_type="competitor")

    if not competitor_accounts:
        st.info("尚未設定競品帳號。請至「⚙️ 設定」頁面新增競品帳號。")
        return

    # Account selector
    account_names = [f"@{a['username']}" for a in competitor_accounts]
    selected_name = st.selectbox("選擇競品帳號", ["全部"] + account_names)

    if selected_name == "全部":
        selected_accounts = competitor_accounts
    else:
        username = selected_name.lstrip("@")
        selected_accounts = [a for a in competitor_accounts if a["username"] == username]

    # Date range
    days = st.slider("分析時間範圍（天）", min_value=7, max_value=90, value=30)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Collect posts
    all_posts = []
    for acc in selected_accounts:
        posts = get_posts(account_id=acc["id"], limit=200, since=since)
        for p in posts:
            p["account_username"] = acc["username"]
        all_posts.extend(posts)

    if not all_posts:
        st.info(f"過去 {days} 天內無競品貼文數據。請先執行數據抓取。")
        return

    df = pd.DataFrame(all_posts)
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df["engagement_rate"] = pd.to_numeric(df["engagement_rate"], errors="coerce").fillna(0)
    df["like_count"] = pd.to_numeric(df["like_count"], errors="coerce").fillna(0)
    df["comment_count"] = pd.to_numeric(df["comment_count"], errors="coerce").fillna(0)

    st.divider()

    # ── KPIs ──────────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("分析貼文數", len(df))
    with col2:
        st.metric("平均互動率", f"{df['engagement_rate'].mean():.2f}%")
    with col3:
        st.metric("平均按讚數", f"{df['like_count'].mean():.0f}")
    with col4:
        avg_posts_per_week = len(df) / (days / 7)
        st.metric("平均每週發文", f"{avg_posts_per_week:.1f} 篇")

    st.divider()

    # ── Engagement rate trend ─────────────────────────────────────────────────
    st.subheader("📈 互動率趨勢")
    if not df["published_at"].isna().all():
        df_trend = df.dropna(subset=["published_at"]).copy()
        df_trend["date"] = df_trend["published_at"].dt.date
        trend = df_trend.groupby(["date", "account_username"])["engagement_rate"].mean().reset_index()
        chart_data = trend.pivot(index="date", columns="account_username", values="engagement_rate")
        st.line_chart(chart_data)

    st.divider()

    # ── Post type distribution ────────────────────────────────────────────────
    st.subheader("📊 內容格式分析")
    col1, col2 = st.columns(2)

    with col1:
        type_counts = df["post_type"].value_counts()
        st.markdown("**發文格式分佈**")
        type_df = pd.DataFrame({"格式": type_counts.index, "數量": type_counts.values})
        st.bar_chart(type_df.set_index("格式"))

    with col2:
        type_er = df.groupby("post_type")["engagement_rate"].mean().sort_values(ascending=False)
        st.markdown("**各格式平均互動率**")
        st.bar_chart(type_er)

    st.divider()

    # ── Top posts ─────────────────────────────────────────────────────────────
    st.subheader("🏆 高互動貼文 Top 10")
    top_posts = df.nlargest(10, "engagement_rate")[
        ["account_username", "post_type", "content", "like_count",
         "comment_count", "engagement_rate", "published_at", "permalink"]
    ].copy()
    top_posts["content"] = top_posts["content"].str[:60] + "…"
    top_posts.columns = ["帳號", "格式", "內容預覽", "讚數", "留言數", "互動率(%)", "發布時間", "連結"]
    top_posts["互動率(%)"] = top_posts["互動率(%)"].round(3)
    st.dataframe(top_posts, use_container_width=True, hide_index=True)

    st.divider()

    # ── Hashtag analysis ─────────────────────────────────────────────────────
    st.subheader("#️⃣ Hashtag 分析")
    all_hashtags = []
    for _, row in df.iterrows():
        try:
            tags = json.loads(row.get("hashtags") or "[]")
            all_hashtags.extend(tags)
        except Exception:
            pass

    if all_hashtags:
        counter = Counter(all_hashtags)
        top_tags = counter.most_common(20)
        tag_df = pd.DataFrame(top_tags, columns=["Hashtag", "使用次數"])
        col1, col2 = st.columns([2, 1])
        with col1:
            st.bar_chart(tag_df.set_index("Hashtag"))
        with col2:
            st.dataframe(tag_df, hide_index=True, use_container_width=True)
    else:
        st.info("尚無 hashtag 數據")

    st.divider()

    # ── Best posting time heatmap ─────────────────────────────────────────────
    st.subheader("⏰ 發文時段分析")
    if not df["published_at"].isna().all():
        df_time = df.dropna(subset=["published_at"]).copy()
        df_time["hour"] = df_time["published_at"].dt.hour
        df_time["weekday"] = df_time["published_at"].dt.day_name()
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_zh = {"Monday": "週一", "Tuesday": "週二", "Wednesday": "週三",
                      "Thursday": "週四", "Friday": "週五", "Saturday": "週六", "Sunday": "週日"}
        df_time["weekday"] = df_time["weekday"].map(weekday_zh)

        hour_er = df_time.groupby("hour")["engagement_rate"].mean()
        st.markdown("**各時段平均互動率**")
        st.bar_chart(hour_er)

    st.divider()

    # ── AI Analysis ───────────────────────────────────────────────────────────
    st.subheader("🤖 AI 競品分析報告")

    latest_analysis = get_latest_analysis("competitor")
    if latest_analysis:
        try:
            data = json.loads(latest_analysis["result_json"])
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**機會缺口**")
                for opp in data.get("opportunities", []):
                    st.markdown(f"✅ {opp}")
                st.markdown("**高互動貼文特徵**")
                features = data.get("top_posts_features", {})
                st.markdown(f"- 主題：{', '.join(features.get('themes', []))}")
                st.markdown(f"- 格式：{', '.join(features.get('formats', []))}")
                st.markdown(f"- 語氣：{features.get('content_tone', '')}")
            with col2:
                st.markdown("**威脅點**")
                for threat in data.get("threats", []):
                    st.markdown(f"⚠️ {threat}")
                st.markdown("**整體摘要**")
                st.info(data.get("summary", ""))
            st.caption(f"分析時間：{latest_analysis['created_at'][:16]}")
        except Exception:
            st.markdown(latest_analysis.get("summary_text", ""))
    else:
        st.info("尚無 AI 分析報告。")

    if st.button("🔄 立即執行 AI 競品分析", key="run_competitor_analysis"):
        with st.spinner("分析中，請稍候（約 30-60 秒）…"):
            try:
                from analysis.claude_analyzer import analyze_competitors
                from db.database import save_analysis
                result = analyze_competitors(all_posts)
                save_analysis(
                    analysis_type="competitor",
                    result_json=json.dumps(result, ensure_ascii=False),
                    summary_text=result.get("summary", ""),
                )
                st.success("✅ 分析完成！請重新整理頁面查看結果。")
                st.rerun()
            except Exception as exc:
                st.error(f"分析失敗：{exc}")


if __name__ == "__main__":
    render()
