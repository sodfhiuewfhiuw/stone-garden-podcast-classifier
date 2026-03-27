"""
Content Advisor module.
Combines competitor analysis + own account data to generate:
- Weekly content calendar draft
- Post-level content suggestions
- Hashtag recommendations
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096


def _get_client() -> anthropic.Anthropic:
    from config.settings import Secrets
    api_key = Secrets.claude_api_key()
    if not api_key:
        raise ValueError("Claude API key not configured.")
    return anthropic.Anthropic(api_key=api_key)


CALENDAR_PROMPT = """你是一位資深品牌內容策略師，請根據以下資料生成下週的內容行事曆草稿。

## 競品分析摘要
{competitor_summary}

## 自家帳號成效分析
{own_summary}

## 品牌設定
- 品牌語氣：{brand_tone}
- 平台：Threads + Instagram
- 每週發文目標：{post_target} 篇

## 任務
生成下週（{week_start} 至 {week_end}）的完整內容行事曆。
每篇貼文需包含：主題、格式、內容方向、建議 hashtag 5-8 個、建議發文時間。

以 JSON 格式回覆：
{{
  "week_theme": "本週內容主題方向（一句話）",
  "posts": [
    {{
      "day": "星期幾（例：週一）",
      "date": "YYYY-MM-DD",
      "platform": "Threads" 或 "Instagram" 或 "兩者",
      "post_type": "圖文" 或 "Reels" 或 "輪播" 或 "純文字",
      "topic": "貼文主題",
      "content_direction": "內容方向與撰寫重點（50字）",
      "suggested_hashtags": ["hashtag1", "hashtag2"],
      "best_posting_time": "HH:MM",
      "expected_engagement": "高/中/低",
      "notes": "額外備注（可選）"
    }}
  ],
  "strategy_notes": "本週整體策略說明（100字）",
  "content_pillars": ["本週內容支柱1", "本週內容支柱2", "本週內容支柱3"]
}}"""


def generate_content_calendar(
    competitor_analysis: dict,
    own_analysis: dict,
    brand_tone: str = "專業且親切，用詞簡潔有力",
    post_target: int = 5,
    week_start: datetime = None,
) -> dict:
    """
    Generate a weekly content calendar draft.

    Args:
        competitor_analysis: Output from claude_analyzer.analyze_competitors()
        own_analysis: Output from claude_analyzer.analyze_own_account()
        brand_tone: Brand voice preference
        post_target: Target number of posts per week
        week_start: Start date for the calendar (defaults to next Monday)

    Returns:
        Parsed JSON calendar
    """
    if week_start is None:
        today = datetime.now(timezone.utc)
        days_until_monday = (7 - today.weekday()) % 7 or 7
        week_start = today + timedelta(days=days_until_monday)

    week_end = week_start + timedelta(days=6)

    client = _get_client()

    # Slim down inputs for the prompt
    comp_summary = {
        "opportunities": competitor_analysis.get("opportunities", []),
        "top_posts_features": competitor_analysis.get("top_posts_features", {}),
        "hashtag_analysis": competitor_analysis.get("hashtag_analysis", {}),
        "posting_strategy": competitor_analysis.get("posting_strategy", {}),
    }
    own_summary = {
        "best_post_types": own_analysis.get("best_post_types", []),
        "optimal_posting_times": own_analysis.get("optimal_posting_times", {}),
        "high_engagement_features": own_analysis.get("high_engagement_features", {}),
        "action_items": own_analysis.get("action_items", [])[:3],
    }

    prompt = CALENDAR_PROMPT.format(
        competitor_summary=json.dumps(comp_summary, ensure_ascii=False),
        own_summary=json.dumps(own_summary, ensure_ascii=False),
        brand_tone=brand_tone,
        post_target=post_target,
        week_start=week_start.strftime("%Y-%m-%d"),
        week_end=week_end.strftime("%Y-%m-%d"),
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        result = json.loads(raw)
        logger.info(f"[ContentAdvisor] Generated calendar for {week_start.date()}")
        return result

    except (json.JSONDecodeError, anthropic.APIError) as exc:
        logger.error(f"[ContentAdvisor] Calendar generation failed: {exc}")
        return {"error": str(exc)}


HASHTAG_PROMPT = """你是社群媒體 hashtag 策略專家。

根據以下貼文資訊，推薦 8-12 個最適合的 hashtag：
- 貼文主題：{topic}
- 貼文類型：{post_type}
- 平台：{platform}
- 品牌語氣：{brand_tone}
- 競品常用 hashtag：{competitor_hashtags}

請推薦兼顧品牌性、話題性和觸及力的 hashtag 組合。
以 JSON 格式回覆：
{{
  "brand_hashtags": ["品牌或產品相關，1-3個"],
  "topic_hashtags": ["主題相關，3-5個"],
  "trending_hashtags": ["話題熱門，2-4個"],
  "all_hashtags": ["完整推薦清單"],
  "reasoning": "選擇邏輯說明（50字）"
}}"""


def suggest_hashtags(
    topic: str,
    post_type: str,
    platform: str = "Instagram",
    brand_tone: str = "",
    competitor_hashtags: list = None,
) -> dict:
    """Suggest hashtags for a specific post."""
    client = _get_client()
    prompt = HASHTAG_PROMPT.format(
        topic=topic,
        post_type=post_type,
        platform=platform,
        brand_tone=brand_tone or "專業親切",
        competitor_hashtags=json.dumps(competitor_hashtags or [], ensure_ascii=False),
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        return json.loads(raw)
    except (json.JSONDecodeError, anthropic.APIError) as exc:
        logger.error(f"[ContentAdvisor] Hashtag suggestion failed: {exc}")
        return {"error": str(exc)}


def run_full_weekly_analysis(brand_tone: str = None, post_target: int = 5) -> dict:
    """
    Convenience function: pulls data from DB, runs full analysis pipeline,
    and saves results. Returns the complete analysis package.
    """
    from db.database import (
        get_accounts, get_posts, get_metrics,
        save_analysis, get_latest_analysis,
    )
    from analysis.claude_analyzer import (
        analyze_competitors, analyze_own_account, generate_weekly_summary
    )
    from config.settings import AppSettings

    brand_tone = brand_tone or AppSettings.brand_tone()

    # 1. Competitor analysis
    competitor_accounts = get_accounts(platform="threads", account_type="competitor")
    all_competitor_posts = []
    for acc in competitor_accounts:
        all_competitor_posts.extend(get_posts(account_id=acc["id"], limit=50))

    competitor_analysis = {}
    if all_competitor_posts:
        competitor_analysis = analyze_competitors(all_competitor_posts, brand_tone)
        save_analysis(
            analysis_type="competitor",
            result_json=json.dumps(competitor_analysis, ensure_ascii=False),
            summary_text=competitor_analysis.get("summary", ""),
        )

    # 2. Own account analysis
    own_accounts = get_accounts(account_type="own")
    own_posts, own_metrics = [], []
    for acc in own_accounts:
        own_posts.extend(get_posts(account_id=acc["id"], limit=50))
        own_metrics.extend(get_metrics(account_id=acc["id"], days=30))

    own_analysis = {}
    if own_posts:
        own_analysis = analyze_own_account(own_posts, own_metrics, competitor_analysis)
        save_analysis(
            analysis_type="own_account",
            result_json=json.dumps(own_analysis, ensure_ascii=False),
            summary_text=own_analysis.get("overall_performance", {}).get("insights", ""),
        )

    # 3. Content calendar
    calendar = {}
    if competitor_analysis or own_analysis:
        calendar = generate_content_calendar(
            competitor_analysis=competitor_analysis,
            own_analysis=own_analysis,
            brand_tone=brand_tone,
            post_target=post_target,
        )
        save_analysis(
            analysis_type="content_calendar",
            result_json=json.dumps(calendar, ensure_ascii=False),
            summary_text=calendar.get("week_theme", ""),
        )

    # 4. Weekly summary
    weekly_summary = {}
    if competitor_analysis or own_analysis:
        weekly_summary = generate_weekly_summary(own_analysis, competitor_analysis, calendar)
        save_analysis(
            analysis_type="weekly_report",
            result_json=json.dumps(weekly_summary, ensure_ascii=False),
            summary_text=weekly_summary.get("executive_summary", ""),
        )

    return {
        "competitor_analysis": competitor_analysis,
        "own_analysis": own_analysis,
        "content_calendar": calendar,
        "weekly_summary": weekly_summary,
    }
