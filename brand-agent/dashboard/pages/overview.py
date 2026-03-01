"""
Overview dashboard page.
Shows high-level KPIs, recent activity, and weekly trend summary.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone


def render():
    st.title("📊 總覽")
    st.caption(f"最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    try:
        from db.database import get_accounts, get_posts, get_metrics, get_latest_analysis
    except ImportError as e:
        st.error(f"資料庫載入失敗：{e}")
        return

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    own_accounts = get_accounts(account_type="own")
    competitor_accounts = get_accounts(account_type="competitor")

    col1, col2, col3, col4 = st.columns(4)

    total_followers = sum(a.get("follower_count", 0) for a in own_accounts)
    total_competitors = len(competitor_accounts)

    # Gather own posts from last 7 days
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    own_posts_7d = []
    for acc in own_accounts:
        own_posts_7d.extend(get_posts(account_id=acc["id"], limit=100, since=week_ago))

    avg_er = (
        sum(p.get("engagement_rate", 0) for p in own_posts_7d) / len(own_posts_7d)
        if own_posts_7d else 0
    )

    with col1:
        st.metric("粉絲數", f"{total_followers:,}", help="自家帳號總粉絲數")
    with col2:
        st.metric("本週發文數", len(own_posts_7d), help="過去 7 天發文數量")
    with col3:
        st.metric("平均互動率", f"{avg_er:.2f}%", help="過去 7 天貼文平均互動率")
    with col4:
        st.metric("監控競品數", total_competitors, help="目前監控中的競品帳號")

    st.divider()

    # ── Follower trend ────────────────────────────────────────────────────────
    if own_accounts:
        st.subheader("📈 粉絲趨勢（近 30 天）")
        all_metrics = []
        for acc in own_accounts:
            metrics = get_metrics(account_id=acc["id"], days=30)
            for m in metrics:
                m["account"] = acc.get("username", "")
                all_metrics.append(m)

        if all_metrics:
            df = pd.DataFrame(all_metrics)
            df["metric_date"] = pd.to_datetime(df["metric_date"])
            df = df.sort_values("metric_date")
            chart_data = df.pivot_table(
                index="metric_date", columns="account",
                values="follower_count", aggfunc="first"
            )
            st.line_chart(chart_data)
        else:
            st.info("尚無粉絲趨勢數據。請先完成設定並執行一次數據抓取。")
    else:
        st.info("尚未設定自家帳號。請至「⚙️ 設定」頁面完成帳號連接。")

    st.divider()

    # ── AI Weekly Summary ─────────────────────────────────────────────────────
    st.subheader("🤖 AI 週報摘要")
    latest_summary = get_latest_analysis("weekly_report")
    if latest_summary:
        import json
        try:
            data = json.loads(latest_summary["result_json"])
            st.info(f"**{data.get('executive_summary', '')}**")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**本週亮點**")
                for h in data.get("week_highlights", []):
                    st.markdown(f"- {h}")
            with col2:
                st.markdown("**下週重點**")
                for f in data.get("next_week_focus", []):
                    st.markdown(f"- {f}")
            st.caption(f"生成時間：{latest_summary['created_at'][:16]}")
        except Exception:
            st.markdown(latest_summary.get("summary_text", ""))
    else:
        st.info("尚無 AI 週報。系統會在每週一自動生成，您也可以至「💡 AI 內容建議」頁面手動觸發。")

    st.divider()

    # ── Recent Posts ──────────────────────────────────────────────────────────
    st.subheader("📝 最新貼文")
    all_recent_posts = []
    for acc in own_accounts:
        posts = get_posts(account_id=acc["id"], limit=5)
        for p in posts:
            p["account"] = acc.get("username", "")
        all_recent_posts.extend(posts)

    all_recent_posts.sort(key=lambda x: x.get("published_at", ""), reverse=True)

    if all_recent_posts:
        for post in all_recent_posts[:5]:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    content_preview = (post.get("content") or "（無文字內容）")[:80]
                    st.markdown(f"**@{post['account']}** · {post.get('post_type', '').upper()}")
                    st.caption(content_preview)
                with col2:
                    st.metric("❤️ 讚", post.get("like_count", 0))
                with col3:
                    st.metric("💬 留言", post.get("comment_count", 0))
                with col4:
                    st.metric("📊 互動率", f"{post.get('engagement_rate', 0):.2f}%")
                st.divider()
    else:
        st.info("尚無貼文數據。")


if __name__ == "__main__":
    render()
