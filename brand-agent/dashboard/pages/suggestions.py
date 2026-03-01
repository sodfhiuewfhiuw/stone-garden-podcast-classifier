"""
AI Content Suggestions page.
Displays weekly content calendar, hashtag recommendations, and strategy notes.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import streamlit as st
import pandas as pd
from datetime import datetime


def render():
    st.title("💡 AI 內容建議")
    st.caption("由 Claude AI 根據競品分析與自家成效生成的每週內容策略")

    try:
        from db.database import get_latest_analysis
        from config.settings import AppSettings
    except ImportError as e:
        st.error(f"模組載入失敗：{e}")
        return

    # ── Weekly Content Calendar ───────────────────────────────────────────────
    st.subheader("📅 本週內容行事曆")

    latest_calendar = get_latest_analysis("content_calendar")
    if latest_calendar:
        try:
            data = json.loads(latest_calendar["result_json"])
            st.info(f"**本週主題方向：** {data.get('week_theme', '')}")

            posts = data.get("posts", [])
            if posts:
                df = pd.DataFrame(posts)
                display_cols = ["day", "platform", "post_type", "topic",
                                "content_direction", "best_posting_time", "expected_engagement"]
                col_names = {
                    "day": "星期",
                    "platform": "平台",
                    "post_type": "格式",
                    "topic": "主題",
                    "content_direction": "內容方向",
                    "best_posting_time": "發文時間",
                    "expected_engagement": "預期互動",
                }
                df = df[[c for c in display_cols if c in df.columns]].rename(columns=col_names)
                st.dataframe(df, use_container_width=True, hide_index=True)

                st.divider()
                st.markdown("**詳細貼文規劃**")
                for i, post in enumerate(posts):
                    with st.expander(f"📌 {post.get('day', '')} · {post.get('topic', '')}"):
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.markdown(f"**平台：** {post.get('platform', '')}")
                            st.markdown(f"**格式：** {post.get('post_type', '')}")
                            st.markdown(f"**內容方向：** {post.get('content_direction', '')}")
                            if post.get("notes"):
                                st.caption(f"備注：{post['notes']}")
                        with col2:
                            st.markdown(f"**建議發文時間：** {post.get('best_posting_time', '')}")
                            st.markdown(f"**預期互動：** {post.get('expected_engagement', '')}")
                            tags = post.get("suggested_hashtags", [])
                            if tags:
                                st.markdown("**建議 Hashtag：**")
                                st.code(" ".join(f"#{t}" for t in tags))

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**策略說明**")
                st.info(data.get("strategy_notes", ""))
            with col2:
                st.markdown("**本週內容支柱**")
                for pillar in data.get("content_pillars", []):
                    st.markdown(f"- {pillar}")

            st.caption(f"生成時間：{latest_calendar['created_at'][:16]}")

        except Exception as exc:
            st.error(f"解析行事曆數據時發生錯誤：{exc}")
    else:
        st.info("尚無內容行事曆。請點擊下方按鈕生成。")

    st.divider()

    # ── Generate / Refresh ────────────────────────────────────────────────────
    st.subheader("🔄 重新生成內容建議")

    col1, col2 = st.columns(2)
    with col1:
        brand_tone = st.text_area(
            "品牌語氣（可覆蓋設定頁的預設值）",
            value=AppSettings.brand_tone(),
            height=80,
        )
    with col2:
        post_target = st.number_input("每週目標發文數", min_value=1, max_value=14,
                                       value=int(AppSettings.get("post_target", "5")))

    if st.button("🚀 立即生成本週內容行事曆", type="primary", key="gen_calendar"):
        with st.spinner("Claude AI 分析中，請稍候（約 60-90 秒）…"):
            try:
                from analysis.content_advisor import run_full_weekly_analysis
                result = run_full_weekly_analysis(
                    brand_tone=brand_tone,
                    post_target=int(post_target),
                )
                st.success("✅ 分析完成！")
                st.rerun()
            except Exception as exc:
                st.error(f"生成失敗：{exc}")

    st.divider()

    # ── Hashtag Tool ──────────────────────────────────────────────────────────
    st.subheader("#️⃣ 單篇貼文 Hashtag 建議")
    st.caption("輸入您的貼文主題，AI 即時推薦最適合的 hashtag 組合")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        topic_input = st.text_input("貼文主題", placeholder="例：夏季新品上市、品牌故事分享")
    with col2:
        post_type_input = st.selectbox("貼文格式", ["圖文", "Reels", "輪播", "純文字"])
    with col3:
        platform_input = st.selectbox("平台", ["Instagram", "Threads", "兩者"])

    if st.button("✨ 生成 Hashtag 建議", key="gen_hashtag"):
        if not topic_input:
            st.warning("請先輸入貼文主題")
        else:
            with st.spinner("生成中…"):
                try:
                    from analysis.content_advisor import suggest_hashtags
                    result = suggest_hashtags(
                        topic=topic_input,
                        post_type=post_type_input,
                        platform=platform_input,
                        brand_tone=brand_tone,
                    )
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success("✅ Hashtag 建議生成完成")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.markdown("**品牌 Hashtag**")
                            st.code(" ".join(f"#{t}" for t in result.get("brand_hashtags", [])))
                        with col2:
                            st.markdown("**主題 Hashtag**")
                            st.code(" ".join(f"#{t}" for t in result.get("topic_hashtags", [])))
                        with col3:
                            st.markdown("**熱門話題 Hashtag**")
                            st.code(" ".join(f"#{t}" for t in result.get("trending_hashtags", [])))

                        st.markdown("**完整推薦組合（複製使用）**")
                        all_tags = " ".join(f"#{t}" for t in result.get("all_hashtags", []))
                        st.code(all_tags)
                        st.caption(f"選擇邏輯：{result.get('reasoning', '')}")
                except Exception as exc:
                    st.error(f"生成失敗：{exc}")

    st.divider()

    # ── Previous Analyses ─────────────────────────────────────────────────────
    st.subheader("📚 歷史 AI 分析")
    with st.expander("查看最新競品分析摘要"):
        latest_comp = get_latest_analysis("competitor")
        if latest_comp:
            try:
                data = json.loads(latest_comp["result_json"])
                st.markdown(f"**分析時間：** {latest_comp['created_at'][:16]}")
                st.info(data.get("summary", ""))
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**機會缺口**")
                    for o in data.get("opportunities", []):
                        st.markdown(f"- {o}")
                with col2:
                    st.markdown("**威脅點**")
                    for t in data.get("threats", []):
                        st.markdown(f"- {t}")
            except Exception:
                st.text(latest_comp.get("summary_text", ""))
        else:
            st.info("尚無競品分析數據")

    with st.expander("查看最新成效分析摘要"):
        latest_own = get_latest_analysis("own_account")
        if latest_own:
            try:
                data = json.loads(latest_own["result_json"])
                st.markdown(f"**分析時間：** {latest_own['created_at'][:16]}")
                overall = data.get("overall_performance", {})
                st.info(overall.get("insights", ""))
                st.markdown("**改善行動**")
                for item in data.get("action_items", []):
                    priority = item.get("priority", "")
                    icon = "🔴" if priority == "高" else "🟡" if priority == "中" else "🟢"
                    st.markdown(f"{icon} {item.get('action', '')}")
            except Exception:
                st.text(latest_own.get("summary_text", ""))
        else:
            st.info("尚無成效分析數據")


if __name__ == "__main__":
    render()
