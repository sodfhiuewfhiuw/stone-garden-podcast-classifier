"""
Brand Content Strategy Agent — Main Entry Point
Starts APScheduler for automated data collection and report generation,
then launches the Streamlit dashboard.

Usage:
    python main.py             # Run scheduler + dashboard
    python main.py --scheduler # Run scheduler only (no dashboard)
    python main.py --dashboard # Run dashboard only (no scheduler)
"""

import sys
import os
import logging
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Ensure brand-agent root is on sys.path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "data" / "app.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── Scheduled Jobs ────────────────────────────────────────────────────────────

def job_fetch_all_data():
    """Daily 03:00 — fetch data from all configured platforms."""
    logger.info("[Scheduler] Starting daily data fetch…")
    try:
        from config.settings import Secrets, AppSettings
        from db.database import get_accounts

        threads_token = Secrets.threads_token()
        ig_token = Secrets.ig_token()
        ig_account_id = Secrets.ig_account_id()

        results = []

        # Threads own account
        if threads_token:
            from collectors.threads_api import ThreadsCollector, fetch_and_store_own
            collector = ThreadsCollector(threads_token)
            count = fetch_and_store_own(collector, limit=50)
            results.append(f"Threads own: {count} posts")

            # Threads competitors
            competitor_accounts = AppSettings.competitor_accounts()
            for acc in competitor_accounts:
                if acc.get("user_id"):
                    from collectors.threads_api import fetch_and_store_competitor
                    count = fetch_and_store_competitor(
                        collector,
                        username=acc["username"],
                        user_id=acc["user_id"],
                        limit=50,
                    )
                    results.append(f"Threads @{acc['username']}: {count} posts")

        # Instagram own account
        if ig_token and ig_account_id:
            from collectors.instagram_api import InstagramCollector, fetch_and_store_ig
            ig_collector = InstagramCollector(ig_token, ig_account_id)
            count = fetch_and_store_ig(ig_collector, limit=50)
            results.append(f"Instagram: {count} posts")

        logger.info(f"[Scheduler] Data fetch complete: {' | '.join(results)}")

    except Exception as exc:
        logger.error(f"[Scheduler] Data fetch failed: {exc}", exc_info=True)


def job_weekly_analysis():
    """Monday 06:00 — run full AI analysis pipeline."""
    logger.info("[Scheduler] Starting weekly AI analysis…")
    try:
        from analysis.content_advisor import run_full_weekly_analysis
        from config.settings import AppSettings

        result = run_full_weekly_analysis(
            brand_tone=AppSettings.brand_tone(),
            post_target=int(AppSettings.get("post_target", "5")),
        )
        logger.info("[Scheduler] Weekly analysis complete.")
        return result
    except Exception as exc:
        logger.error(f"[Scheduler] Weekly analysis failed: {exc}", exc_info=True)


def job_send_weekly_report():
    """Monday 08:00 — generate PDF and send weekly email report."""
    logger.info("[Scheduler] Generating and sending weekly report…")
    try:
        from reports.weekly_report import generate_and_send_weekly_report
        result = generate_and_send_weekly_report()
        if result.get("success"):
            logger.info(
                f"[Scheduler] Report sent. PDF: {result['pdf_path']} | "
                f"Email: {'sent' if result['email_sent'] else 'skipped'}"
            )
        else:
            logger.error(f"[Scheduler] Report failed: {result.get('error')}")
    except Exception as exc:
        logger.error(f"[Scheduler] Report generation failed: {exc}", exc_info=True)


# ── Scheduler Setup ───────────────────────────────────────────────────────────

def start_scheduler():
    """Configure and start APScheduler background scheduler."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        return None

    # Initialize DB before scheduling
    from db.database import init_db
    init_db()

    scheduler = BackgroundScheduler(timezone="Asia/Taipei")

    # Daily data fetch at 03:00 Taipei time
    scheduler.add_job(
        job_fetch_all_data,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_fetch",
        name="Daily Data Fetch",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Weekly AI analysis on Monday at 06:00
    scheduler.add_job(
        job_weekly_analysis,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=0),
        id="weekly_analysis",
        name="Weekly AI Analysis",
        replace_existing=True,
        misfire_grace_time=7200,
    )

    # Weekly report email on Monday at 08:00
    scheduler.add_job(
        job_send_weekly_report,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_report",
        name="Weekly Report Email",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()

    next_jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        next_jobs.append(f"  • {job.name}: {next_run}")
    logger.info(f"[Scheduler] Started. Scheduled jobs:\n" + "\n".join(next_jobs))

    return scheduler


# ── Dashboard Launch ──────────────────────────────────────────────────────────

def launch_dashboard():
    """Launch Streamlit dashboard as a subprocess."""
    dashboard_path = BASE_DIR / "dashboard" / "app.py"
    logger.info(f"[Dashboard] Launching: {dashboard_path}")

    # Pass brand-agent root as PYTHONPATH so imports work
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(dashboard_path),
         "--server.port", "8501",
         "--server.address", "0.0.0.0",
         "--browser.gatherUsageStats", "false"],
        env=env,
    )
    return proc


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Brand Content Strategy Agent")
    parser.add_argument("--scheduler", action="store_true", help="Run scheduler only")
    parser.add_argument("--dashboard", action="store_true", help="Run dashboard only")
    parser.add_argument("--fetch-now", action="store_true", help="Run data fetch immediately")
    parser.add_argument("--analyze-now", action="store_true", help="Run weekly analysis immediately")
    parser.add_argument("--report-now", action="store_true", help="Generate and send report immediately")
    args = parser.parse_args()

    # Ensure data directory exists
    (BASE_DIR / "data").mkdir(exist_ok=True)
    (BASE_DIR / "data" / "reports").mkdir(exist_ok=True)

    # Initialize database
    from db.database import init_db
    init_db()

    # One-off commands
    if args.fetch_now:
        job_fetch_all_data()
        return

    if args.analyze_now:
        job_weekly_analysis()
        return

    if args.report_now:
        job_send_weekly_report()
        return

    # Scheduler only
    if args.scheduler:
        scheduler = start_scheduler()
        if scheduler:
            logger.info("[Main] Scheduler running. Press Ctrl+C to stop.")
            try:
                import time
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                scheduler.shutdown()
                logger.info("[Main] Scheduler stopped.")
        return

    # Dashboard only
    if args.dashboard:
        proc = launch_dashboard()
        logger.info("[Main] Dashboard running at http://localhost:8501")
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
        return

    # Default: scheduler + dashboard
    scheduler = start_scheduler()
    dashboard_proc = launch_dashboard()
    logger.info("[Main] Brand Content Strategy Agent running.")
    logger.info("[Main] Dashboard: http://localhost:8501 | Press Ctrl+C to stop.")

    try:
        dashboard_proc.wait()
    except KeyboardInterrupt:
        logger.info("[Main] Shutting down…")
        if scheduler:
            scheduler.shutdown()
        dashboard_proc.terminate()
        logger.info("[Main] Stopped.")


if __name__ == "__main__":
    main()
