"""
Weekly Report module.
Generates a branded PDF report and emails it to configured recipients.
Uses FPDF2 for PDF generation with CJK (Chinese) support.
"""

import io
import json
import logging
import smtplib
import os
from datetime import datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent / "data" / "reports"
FONT_PATH = Path(__file__).parent / "fonts" / "NotoSansTC-Regular.ttf"


def _get_fpdf():
    try:
        from fpdf import FPDF
        return FPDF
    except ImportError:
        raise ImportError("fpdf2 not installed. Run: pip install fpdf2")


# ── PDF Generation ────────────────────────────────────────────────────────────

class WeeklyReportPDF:
    """Generates a branded weekly report PDF with Chinese text support."""

    def __init__(self):
        FPDF = _get_fpdf()
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(auto=True, margin=15)
        self._setup_fonts()

    def _setup_fonts(self):
        """Configure CJK-compatible fonts."""
        # Try to use bundled Noto Sans TC font for Chinese support
        if FONT_PATH.exists():
            self.pdf.add_font("NotoSans", "", str(FONT_PATH))
            self.body_font = "NotoSans"
        else:
            # Fallback to DejaVu (no CJK support, but widely available)
            self.body_font = "Helvetica"
            logger.warning(
                f"Chinese font not found at {FONT_PATH}. "
                "Chinese characters may not render. "
                "Download NotoSansTC-Regular.ttf and place in reports/fonts/"
            )

    def _add_header(self, title: str, subtitle: str = ""):
        self.pdf.set_fill_color(30, 30, 60)
        self.pdf.rect(0, 0, 210, 40, style="F")
        self.pdf.set_text_color(255, 255, 255)
        self.pdf.set_font(self.body_font, size=20)
        self.pdf.set_xy(10, 10)
        self.pdf.cell(0, 10, title, ln=True)
        if subtitle:
            self.pdf.set_font(self.body_font, size=11)
            self.pdf.set_x(10)
            self.pdf.cell(0, 8, subtitle, ln=True)
        self.pdf.set_text_color(0, 0, 0)
        self.pdf.set_y(50)

    def _section_title(self, text: str):
        self.pdf.set_fill_color(240, 240, 255)
        self.pdf.set_font(self.body_font, size=13)
        self.pdf.cell(0, 10, text, ln=True, fill=True)
        self.pdf.ln(3)

    def _body_text(self, text: str, indent: int = 5):
        self.pdf.set_font(self.body_font, size=10)
        self.pdf.set_x(10 + indent)
        self.pdf.multi_cell(0, 7, str(text))
        self.pdf.ln(2)

    def _bullet(self, text: str):
        self.pdf.set_font(self.body_font, size=10)
        self.pdf.set_x(15)
        self.pdf.multi_cell(0, 7, f"• {text}")

    def _kpi_row(self, kpis: list[tuple]):
        """Render a row of KPI boxes. kpis = [(label, value), ...]"""
        col_width = 190 // len(kpis)
        start_y = self.pdf.get_y()
        for i, (label, value) in enumerate(kpis):
            x = 10 + i * col_width
            self.pdf.set_xy(x, start_y)
            self.pdf.set_fill_color(245, 245, 255)
            self.pdf.rect(x, start_y, col_width - 2, 20, style="F")
            self.pdf.set_font(self.body_font, size=8)
            self.pdf.set_xy(x + 2, start_y + 2)
            self.pdf.cell(col_width - 4, 5, label)
            self.pdf.set_font(self.body_font, size=14)
            self.pdf.set_xy(x + 2, start_y + 8)
            self.pdf.cell(col_width - 4, 10, str(value))
        self.pdf.set_y(start_y + 25)

    def generate(
        self,
        week_start: datetime,
        week_end: datetime,
        own_analysis: dict,
        competitor_analysis: dict,
        content_calendar: dict,
        weekly_summary: dict,
        own_metrics: list,
    ) -> bytes:
        """Generate the full weekly PDF report and return as bytes."""
        self.pdf.add_page()

        # Cover
        week_str = f"{week_start.strftime('%Y/%m/%d')} – {week_end.strftime('%Y/%m/%d')}"
        self._add_header("品牌內容策略週報", subtitle=week_str)

        # Executive summary
        exec_summary = weekly_summary.get("executive_summary", "本週成效報告")
        self.pdf.set_font(self.body_font, size=12)
        self.pdf.set_fill_color(230, 245, 255)
        self.pdf.multi_cell(0, 9, f"【本週一句話摘要】{exec_summary}", fill=True)
        self.pdf.ln(5)

        # ── Section 1: Own Account KPIs ───────────────────────────────────────
        self._section_title("1. 本週帳號成效")

        overall = own_analysis.get("overall_performance", {})
        follower_count = own_metrics[0].get("follower_count", 0) if own_metrics else 0
        avg_er = overall.get("avg_engagement_rate", 0)
        trend = overall.get("engagement_trend", "")
        top_type = overall.get("top_performing_type", "")

        self._kpi_row([
            ("粉絲數", f"{follower_count:,}"),
            ("平均互動率", f"{avg_er:.2f}%"),
            ("互動趨勢", trend),
            ("最佳格式", top_type),
        ])
        self._body_text(overall.get("insights", ""))

        # Week highlights
        self._section_title("本週亮點")
        for h in weekly_summary.get("week_highlights", []):
            self._bullet(h)
        self.pdf.ln(3)

        # ── Section 2: Competitor Analysis ───────────────────────────────────
        self.pdf.add_page()
        self._section_title("2. 競品監控摘要")

        comp_summary = competitor_analysis.get("summary", "")
        if comp_summary:
            self._body_text(comp_summary)

        comp_insights = weekly_summary.get("competitor_insights", "")
        if comp_insights:
            self._body_text(f"vs. 競品比較：{comp_insights}")

        self._section_title("競品機會缺口")
        for opp in competitor_analysis.get("opportunities", []):
            self._bullet(opp)
        self.pdf.ln(3)

        self._section_title("競品威脅點")
        for threat in competitor_analysis.get("threats", []):
            self._bullet(threat)
        self.pdf.ln(3)

        # Competitor top hashtags
        hashtag_data = competitor_analysis.get("hashtag_analysis", {})
        if hashtag_data.get("top_hashtags"):
            self._section_title("競品常用 Hashtag")
            tags = " ".join(f"#{t}" for t in hashtag_data["top_hashtags"][:10])
            self._body_text(tags)

        # ── Section 3: Action Items ───────────────────────────────────────────
        self._section_title("3. 具體改善行動")
        for item in own_analysis.get("action_items", []):
            priority = item.get("priority", "")
            action = item.get("action", "")
            impact = item.get("expected_impact", "")
            self._bullet(f"[{priority}] {action} → 預期效果：{impact}")
        self.pdf.ln(3)

        # ── Section 4: Next Week Calendar ────────────────────────────────────
        self.pdf.add_page()
        self._section_title("4. 下週內容行事曆")

        week_theme = content_calendar.get("week_theme", "")
        if week_theme:
            self._body_text(f"本週主題：{week_theme}")

        posts = content_calendar.get("posts", [])
        for post in posts:
            day = post.get("day", "")
            topic = post.get("topic", "")
            post_type = post.get("post_type", "")
            direction = post.get("content_direction", "")
            time_str = post.get("best_posting_time", "")
            tags = " ".join(f"#{t}" for t in post.get("suggested_hashtags", [])[:5])

            self.pdf.set_font(self.body_font, size=11)
            self.pdf.set_x(10)
            self.pdf.cell(0, 8, f"{day}・{topic}（{post_type}）", ln=True)
            self._body_text(f"方向：{direction}", indent=8)
            self._body_text(f"發文時間：{time_str}　Hashtag：{tags}", indent=8)
            self.pdf.ln(2)

        strategy_notes = content_calendar.get("strategy_notes", "")
        if strategy_notes:
            self._section_title("策略說明")
            self._body_text(strategy_notes)

        # ── Section 5: Next Week Focus ────────────────────────────────────────
        self._section_title("5. 下週重點方向")
        for focus in weekly_summary.get("next_week_focus", []):
            self._bullet(focus)

        # Footer
        self.pdf.set_y(-20)
        self.pdf.set_font(self.body_font, size=8)
        self.pdf.set_text_color(150, 150, 150)
        self.pdf.cell(
            0, 10,
            f"品牌內容策略助手 · 自動生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            align="C"
        )

        return self.pdf.output()


# ── Email Sending ─────────────────────────────────────────────────────────────

def send_weekly_email(
    pdf_bytes: bytes,
    recipients: list[str],
    week_str: str,
    executive_summary: str,
    smtp_config: dict,
) -> bool:
    """
    Send the weekly report PDF via SMTP email.
    Returns True on success, False on failure.
    """
    if not recipients:
        logger.warning("[Email] No recipients configured.")
        return False

    host = smtp_config.get("host", "smtp.gmail.com")
    port = smtp_config.get("port", 587)
    user = smtp_config.get("user", "")
    password = smtp_config.get("password", "")

    if not user or not password:
        logger.error("[Email] SMTP credentials not configured.")
        return False

    subject = f"品牌內容策略週報 · {week_str}"
    body = f"""您好，

本週品牌內容策略週報已生成，請見附件 PDF。

本週摘要：{executive_summary}

此報告由品牌內容策略助手自動生成。

祝好，
品牌內容策略助手
"""

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Attach PDF
    filename = f"weekly_report_{datetime.now().strftime('%Y%m%d')}.pdf"
    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(user, recipients, msg.as_string())
        logger.info(f"[Email] Weekly report sent to {recipients}")
        return True
    except Exception as exc:
        logger.error(f"[Email] Failed to send: {exc}")
        return False


# ── High-level entry point ────────────────────────────────────────────────────

def generate_and_send_weekly_report() -> dict:
    """
    Full pipeline: load latest analyses → generate PDF → send email → save file.
    Returns status dict.
    """
    from db.database import get_latest_analysis, get_accounts, get_metrics
    from config.settings import AppSettings

    today = datetime.now(timezone.utc)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    week_str = f"{week_start.strftime('%Y/%m/%d')} – {week_end.strftime('%Y/%m/%d')}"

    # Load analyses
    def load_json(analysis_type: str) -> dict:
        rec = get_latest_analysis(analysis_type)
        if rec:
            try:
                return json.loads(rec["result_json"])
            except Exception:
                return {}
        return {}

    own_analysis = load_json("own_account")
    competitor_analysis = load_json("competitor")
    content_calendar = load_json("content_calendar")
    weekly_summary = load_json("weekly_report")

    # Load metrics for KPIs
    own_accounts = get_accounts(account_type="own")
    own_metrics = []
    for acc in own_accounts:
        own_metrics.extend(get_metrics(account_id=acc["id"], days=7))

    # Generate PDF
    try:
        generator = WeeklyReportPDF()
        pdf_bytes = generator.generate(
            week_start=week_start,
            week_end=week_end,
            own_analysis=own_analysis,
            competitor_analysis=competitor_analysis,
            content_calendar=content_calendar,
            weekly_summary=weekly_summary,
            own_metrics=own_metrics,
        )
    except Exception as exc:
        logger.error(f"[Report] PDF generation failed: {exc}")
        return {"success": False, "error": str(exc)}

    # Save to file
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"weekly_report_{today.strftime('%Y%m%d')}.pdf"
    filepath = REPORTS_DIR / filename
    filepath.write_bytes(pdf_bytes)
    logger.info(f"[Report] Saved to {filepath}")

    # Send email
    recipients = AppSettings.report_emails()
    smtp_config = AppSettings.smtp_config()
    email_sent = send_weekly_email(
        pdf_bytes=pdf_bytes,
        recipients=recipients,
        week_str=week_str,
        executive_summary=weekly_summary.get("executive_summary", ""),
        smtp_config=smtp_config,
    )

    return {
        "success": True,
        "pdf_path": str(filepath),
        "email_sent": email_sent,
        "recipients": recipients,
        "week_str": week_str,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = generate_and_send_weekly_report()
    print(result)
