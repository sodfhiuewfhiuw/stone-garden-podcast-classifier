"""
Brand Content Strategy Agent — Streamlit Dashboard Main App
Integrates all pages via sidebar navigation.
"""

import sys
import os

# Make brand-agent importable from within dashboard/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st

st.set_page_config(
    page_title="品牌內容策略助手",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize DB on first run
try:
    from db.database import init_db
    init_db()
except Exception:
    pass


# ── Sidebar Navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎯 品牌內容策略助手")
    st.caption("Brand Content Strategy Agent")
    st.divider()

    page = st.radio(
        "導覽",
        options=[
            "📊 總覽",
            "🔍 競品監控",
            "📸 IG 成效分析",
            "💡 AI 內容建議",
            "⚙️ 設定",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    # Quick data fetch buttons
    st.markdown("**快速操作**")

    if st.button("🔄 立即抓取數據", use_container_width=True):
        with st.spinner("資料抓取中…"):
            try:
                from config.settings import Secrets, AppSettings
                from collectors.threads_api import ThreadsCollector, fetch_and_store_own, fetch_and_store_competitor
                from collectors.instagram_api import InstagramCollector, fetch_and_store_ig
                from db.database import get_accounts

                results = []

                # Threads own
                threads_token = Secrets.threads_token()
                if threads_token:
                    collector = ThreadsCollector(threads_token)
                    count = fetch_and_store_own(collector)
                    results.append(f"Threads 自家：{count} 篇")

                # Threads competitors
                if threads_token:
                    competitor_accounts = AppSettings.competitor_accounts()
                    for acc in competitor_accounts:
                        if acc.get("user_id"):
                            count = fetch_and_store_competitor(
                                collector, acc["username"], acc["user_id"]
                            )
                            results.append(f"競品 @{acc['username']}：{count} 篇")

                # Instagram
                ig_token = Secrets.ig_token()
                ig_id = Secrets.ig_account_id()
                if ig_token and ig_id:
                    ig_collector = InstagramCollector(ig_token, ig_id)
                    count = fetch_and_store_ig(ig_collector)
                    results.append(f"Instagram：{count} 篇")

                if results:
                    st.success("✅ " + " | ".join(results))
                else:
                    st.warning("請先至設定頁面完成帳號連接")
            except Exception as exc:
                st.error(f"抓取失敗：{exc}")

    st.divider()
    st.caption("v1.0 · Claude Sonnet 4.6")
    st.caption("© 2026 品牌策略助手")


# ── Page Routing ──────────────────────────────────────────────────────────────
if page == "📊 總覽":
    from dashboard.pages.overview import render
    render()

elif page == "🔍 競品監控":
    from dashboard.pages.competitor import render
    render()

elif page == "📸 IG 成效分析":
    from dashboard.pages.instagram import render
    render()

elif page == "💡 AI 內容建議":
    from dashboard.pages.suggestions import render
    render()

elif page == "⚙️ 設定":
    from dashboard.pages.settings import render
    render()
