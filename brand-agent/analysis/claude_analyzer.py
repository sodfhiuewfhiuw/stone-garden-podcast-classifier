"""
Claude AI analyzer module.
Sends structured social media data to Claude and returns
competitor analysis, content insights, and strategic recommendations.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096


def _get_client() -> anthropic.Anthropic:
    from config.settings import Secrets
    api_key = Secrets.claude_api_key()
    if not api_key:
        raise ValueError("Claude API key not configured. Please set it in Settings.")
    return anthropic.Anthropic(api_key=api_key)


# ── Competitor Analysis ───────────────────────────────────────────────────────

COMPETITOR_ANALYSIS_PROMPT = """你是一位資深品牌內容策略師，專精社群媒體數據分析。

請根據以下競品帳號數據，提供深度競品分析報告。

## 競品數據
{competitor_data}

## 分析任務
請完成以下分析，回覆必須以 JSON 格式：

1. **高互動貼文特徵**：分析高互動貼文的共同特徵（主題、格式、發文時段、語氣、長度）
2. **發文策略規律**：競品的發文頻率、最佳發文時間、內容主題分佈
3. **Hashtag 策略**：使用最多的 hashtag、類型分析（品牌、話題、通用）
4. **內容格式偏好**：各內容類型（圖文、影片、輪播）的互動率比較
5. **機會缺口**：競品較少涉獵但市場需求高的主題方向
6. **威脅點**：競品最強的內容方向，我方需特別注意

回覆 JSON 格式：
{{
  "top_posts_features": {{
    "themes": ["主題1", "主題2"],
    "formats": ["格式1", "格式2"],
    "best_posting_times": ["時段1", "時段2"],
    "content_tone": "語氣描述",
    "avg_content_length": "長度描述"
  }},
  "posting_strategy": {{
    "avg_posts_per_week": 數字,
    "peak_days": ["星期幾"],
    "peak_hours": ["時段"],
    "topic_distribution": {{"主題": 比例}}
  }},
  "hashtag_analysis": {{
    "top_hashtags": ["hashtag列表"],
    "strategy": "策略描述",
    "avg_hashtags_per_post": 數字
  }},
  "format_performance": {{
    "image": {{"avg_engagement": 數字, "count": 數字}},
    "video": {{"avg_engagement": 數字, "count": 數字}},
    "carousel": {{"avg_engagement": 數字, "count": 數字}}
  }},
  "opportunities": ["機會點1", "機會點2"],
  "threats": ["威脅點1", "威脅點2"],
  "summary": "整體競品分析摘要（150字以內）"
}}"""


def analyze_competitors(posts_data: list[dict], brand_tone: str = "") -> dict:
    """
    Analyze competitor posts using Claude AI.

    Args:
        posts_data: List of normalized post dicts from database
        brand_tone: Optional brand tone preference to factor in

    Returns:
        Parsed JSON analysis result
    """
    if not posts_data:
        return {"error": "No competitor data available"}

    client = _get_client()

    # Summarize data for prompt (keep tokens manageable)
    summary = _summarize_posts_for_prompt(posts_data, max_posts=30)
    prompt = COMPETITOR_ANALYSIS_PROMPT.format(competitor_data=json.dumps(summary, ensure_ascii=False))

    if brand_tone:
        prompt += f"\n\n我方品牌語氣偏好：{brand_tone}"

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Extract JSON from markdown code block if present
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        result = json.loads(raw)
        logger.info("[Claude] Competitor analysis complete.")
        return result

    except (json.JSONDecodeError, anthropic.APIError) as exc:
        logger.error(f"[Claude] Competitor analysis failed: {exc}")
        return {"error": str(exc), "raw": raw if "raw" in dir() else ""}


# ── Own Account Performance Analysis ─────────────────────────────────────────

OWN_ACCOUNT_PROMPT = """你是一位資深品牌內容策略師。

請根據以下自家帳號的 Instagram / Threads 數據，進行成效分析。

## 帳號數據
{account_data}

## 分析任務
請完成深度成效分析，以 JSON 格式回覆：

1. **整體成效評估**：互動率趨勢、觸及率變化、粉絲成長
2. **最佳內容類型**：哪種格式（單圖/輪播/Reels）表現最好
3. **最佳發文時段**：依歷史數據推算黃金發文時間
4. **高互動貼文特徵**：分析互動率前 20% 貼文的共同特徵
5. **改善建議**：根據數據提出 3-5 個具體改善行動

回覆 JSON 格式：
{{
  "overall_performance": {{
    "avg_engagement_rate": 數字,
    "engagement_trend": "上升/下降/持平",
    "top_performing_type": "格式名稱",
    "insights": "整體評估（100字）"
  }},
  "best_post_types": [
    {{"type": "格式", "avg_engagement_rate": 數字, "recommendation": "建議"}}
  ],
  "optimal_posting_times": {{
    "best_days": ["星期"],
    "best_hours": ["時段"],
    "reasoning": "根據數據的推論"
  }},
  "high_engagement_features": {{
    "themes": ["主題"],
    "content_length": "長度特徵",
    "hashtag_count": 數字,
    "tone": "語氣"
  }},
  "action_items": [
    {{"priority": "高/中/低", "action": "具體行動", "expected_impact": "預期效果"}}
  ]
}}"""


def analyze_own_account(posts_data: list[dict], metrics_data: list[dict],
                        competitor_analysis: dict = None) -> dict:
    """Analyze own account performance."""
    if not posts_data:
        return {"error": "No account data available"}

    client = _get_client()

    account_data = {
        "recent_posts": _summarize_posts_for_prompt(posts_data, max_posts=20),
        "daily_metrics": metrics_data[:14],
    }
    if competitor_analysis:
        account_data["competitor_benchmark"] = {
            "their_avg_engagement": competitor_analysis.get("format_performance", {}),
            "their_opportunities": competitor_analysis.get("opportunities", []),
        }

    prompt = OWN_ACCOUNT_PROMPT.format(
        account_data=json.dumps(account_data, ensure_ascii=False)
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
        logger.info("[Claude] Own account analysis complete.")
        return result

    except (json.JSONDecodeError, anthropic.APIError) as exc:
        logger.error(f"[Claude] Own account analysis failed: {exc}")
        return {"error": str(exc)}


# ── Weekly Strategy Summary ───────────────────────────────────────────────────

WEEKLY_SUMMARY_PROMPT = """你是一位品牌社群媒體策略師，請根據本週數據生成一份完整的週報摘要。

## 本週數據
{weekly_data}

## 任務
生成一份給品牌客戶看的週報摘要，語氣專業且易讀，以 JSON 格式回覆：

{{
  "week_highlights": ["本週亮點1", "本週亮點2", "本週亮點3"],
  "performance_summary": "本週成效總結（150字，直接告訴客戶重點）",
  "competitor_insights": "競品本週動態與我方比較（100字）",
  "next_week_focus": ["下週重點方向1", "下週重點方向2", "下週重點方向3"],
  "executive_summary": "一句話週報摘要（30字）"
}}"""


def generate_weekly_summary(own_analysis: dict, competitor_analysis: dict,
                             content_calendar: dict) -> dict:
    """Generate a weekly report summary."""
    client = _get_client()

    weekly_data = {
        "own_performance": own_analysis,
        "competitor_analysis": competitor_analysis,
        "next_week_calendar": content_calendar,
    }

    prompt = WEEKLY_SUMMARY_PROMPT.format(
        weekly_data=json.dumps(weekly_data, ensure_ascii=False, indent=2)
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        return json.loads(raw)
    except (json.JSONDecodeError, anthropic.APIError) as exc:
        logger.error(f"[Claude] Weekly summary failed: {exc}")
        return {"error": str(exc)}


# ── Helper functions ──────────────────────────────────────────────────────────

def _summarize_posts_for_prompt(posts: list[dict], max_posts: int = 30) -> list[dict]:
    """Select and slim down posts for prompt input."""
    selected = sorted(posts, key=lambda p: p.get("engagement_rate", 0), reverse=True)
    selected = selected[:max_posts]
    slim = []
    for p in selected:
        slim.append({
            "type": p.get("post_type", ""),
            "published_at": p.get("published_at", "")[:16],
            "content_preview": (p.get("content") or "")[:100],
            "hashtags": json.loads(p.get("hashtags", "[]"))[:5],
            "likes": p.get("like_count", 0),
            "comments": p.get("comment_count", 0),
            "shares": p.get("share_count", 0),
            "reach": p.get("reach", 0),
            "engagement_rate": round(p.get("engagement_rate", 0), 2),
        })
    return slim
