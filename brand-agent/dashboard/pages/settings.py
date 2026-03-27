"""
Settings page — zero-tech-jargon UI for brand clients.
All technical terms replaced with plain-language equivalents.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import streamlit as st

# ── Helper: Status indicator ──────────────────────────────────────────────────

def status_light(ok: bool, ok_msg: str = "", fail_msg: str = "") -> None:
    if ok:
        st.success(ok_msg or "✅ 連接成功")
    else:
        st.error(fail_msg or "❌ 連接失敗")


def friendly_error(exc) -> str:
    msg = str(exc)
    status = getattr(exc, "status_code", None)
    if status == 401:
        return "❌ 授權碼輸入錯誤，請重新複製貼上，注意不要有多餘空格"
    if status == 403:
        return "❌ 您的帳號尚未開啟必要權限，請點「查看教學」重新設定"
    if status == 429:
        return "⏳ 系統請求太頻繁，請等待 5 分鐘後再試"
    if "network" in msg.lower() or "connection" in msg.lower():
        return "🌐 網路連線異常，請確認您的網路後重試"
    return f"❌ 發生錯誤：{msg}"


# ── Main settings page ────────────────────────────────────────────────────────

def render():
    st.title("⚙️ 系統設定")
    st.caption("在這裡設定您的帳號連接與偏好。所有資料均加密儲存在您的本機，不會上傳至第三方伺服器。")
    st.divider()

    try:
        from config.settings import Secrets, AppSettings, set_secret
        from db.database import upsert_account, get_accounts, deactivate_account
    except ImportError as e:
        st.error(f"模組載入失敗：{e}")
        return

    # ── Step 1: Threads Connection ────────────────────────────────────────────
    with st.expander("🔗 第一步：連接 Threads 帳號", expanded=True):
        st.markdown("""
        **什麼是「Threads 授權碼」？**
        這是讓系統代替您讀取 Threads 數據的通行碼。
        [📖 查看教學：如何取得 Threads 授權碼](https://developers.facebook.com/docs/threads/get-started)
        """)

        current_token = Secrets.threads_token()
        token_display = ("●" * 20 + current_token[-6:]) if current_token else ""

        threads_token = st.text_input(
            "貼上您的 Threads 授權碼",
            value="",
            type="password",
            placeholder="貼上授權碼（以 EAA... 開頭）",
            help="請勿分享此授權碼給任何人",
        )

        if current_token:
            st.caption(f"目前已設定授權碼：{token_display}")

        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("🔍 測試 Threads 連線", key="test_threads"):
                token_to_test = threads_token or current_token
                if not token_to_test:
                    st.warning("請先輸入授權碼")
                else:
                    with st.spinner("測試連線中…"):
                        try:
                            from collectors.threads_api import ThreadsCollector
                            collector = ThreadsCollector(token_to_test)
                            ok, msg = collector.test_connection()
                            if ok:
                                st.success(msg)
                                if threads_token:
                                    set_secret(Secrets.THREADS_TOKEN, threads_token)
                                    st.info("✅ 授權碼已儲存")
                            else:
                                st.error(msg)
                        except Exception as exc:
                            st.error(friendly_error(exc))

        if threads_token and st.button("💾 儲存 Threads 授權碼", key="save_threads"):
            set_secret(Secrets.THREADS_TOKEN, threads_token)
            st.success("✅ 授權碼已加密儲存")

    st.divider()

    # ── Step 2: Instagram Connection ──────────────────────────────────────────
    with st.expander("📸 第二步：連接 Instagram 帳號", expanded=True):
        st.markdown("""
        **什麼是「Instagram 帳號連接」？**
        系統需要您的 Instagram 商業帳號授權，才能讀取您的貼文成效數據。
        [📖 查看教學：如何取得 Instagram 授權](https://developers.facebook.com/docs/instagram-api/getting-started)
        """)

        current_ig_token = Secrets.ig_token()
        current_ig_id = Secrets.ig_account_id()

        ig_token = st.text_input(
            "貼上您的 Instagram 授權碼",
            value="",
            type="password",
            placeholder="授權碼（以 EAA... 開頭）",
        )
        ig_account_id = st.text_input(
            "輸入您的 Instagram 帳號 ID",
            value=current_ig_id or "",
            placeholder="例：17841400000000000",
            help="帳號 ID 可在 Meta 開發者後台找到",
        )

        if current_ig_token:
            st.caption(f"目前已設定 IG 授權碼：{'●' * 15}{current_ig_token[-6:]}")

        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("🔍 測試 Instagram 連線", key="test_ig"):
                token_to_test = ig_token or current_ig_token
                id_to_test = ig_account_id or current_ig_id
                if not token_to_test or not id_to_test:
                    st.warning("請先填寫授權碼與帳號 ID")
                else:
                    with st.spinner("測試連線中…"):
                        try:
                            from collectors.instagram_api import InstagramCollector
                            collector = InstagramCollector(token_to_test, id_to_test)
                            ok, msg = collector.test_connection()
                            if ok:
                                st.success(msg)
                                if ig_token:
                                    set_secret(Secrets.IG_TOKEN, ig_token)
                                if ig_account_id:
                                    set_secret(Secrets.IG_ACCOUNT_ID, ig_account_id)
                                st.info("✅ 設定已儲存")
                            else:
                                st.error(msg)
                        except Exception as exc:
                            st.error(friendly_error(exc))

        if ig_token and st.button("💾 儲存 Instagram 設定", key="save_ig"):
            set_secret(Secrets.IG_TOKEN, ig_token)
            if ig_account_id:
                set_secret(Secrets.IG_ACCOUNT_ID, ig_account_id)
            st.success("✅ 設定已加密儲存")

    st.divider()

    # ── Step 3: Competitor Management ────────────────────────────────────────
    with st.expander("🔍 第三步：新增要觀察的競品", expanded=True):
        st.markdown("""
        **輸入競品的 @帳號名稱**（Threads 帳號），系統會自動抓取他們的公開貼文數據。
        最多可同時監控 10 個競品帳號。
        """)

        saved_competitors = AppSettings.competitor_accounts()

        # Display current competitors
        if saved_competitors:
            st.markdown("**目前監控中的競品帳號：**")
            for i, acc in enumerate(saved_competitors):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"`@{acc['username']}`　｜　ID: `{acc.get('user_id', '待取得')}`")
                with col2:
                    if st.button("🗑️ 刪除", key=f"del_comp_{i}"):
                        saved_competitors.pop(i)
                        AppSettings.set_competitor_accounts(saved_competitors)
                        try:
                            deactivate_account("threads", acc["username"])
                        except Exception:
                            pass
                        st.rerun()
        else:
            st.info("尚未設定競品帳號。")

        if len(saved_competitors) < 10:
            st.markdown("---")
            st.markdown("**新增競品帳號**")
            new_username = st.text_input(
                "輸入競品 @帳號名稱（不需輸入 @）",
                placeholder="例：brand_competitor",
                key="new_competitor_username",
            )
            new_user_id = st.text_input(
                "輸入該帳號的 Threads 帳號 ID",
                placeholder="例：123456789",
                key="new_competitor_id",
                help="Threads 帳號 ID 可透過 Threads API 或第三方工具查詢",
            )

            if st.button("➕ 新增競品", key="add_competitor"):
                if not new_username:
                    st.warning("請輸入帳號名稱")
                elif any(c["username"] == new_username for c in saved_competitors):
                    st.warning("此帳號已在監控清單中")
                else:
                    new_entry = {
                        "username": new_username.lstrip("@"),
                        "user_id": new_user_id,
                    }
                    saved_competitors.append(new_entry)
                    AppSettings.set_competitor_accounts(saved_competitors)
                    if new_user_id:
                        try:
                            upsert_account(
                                platform="threads",
                                account_type="competitor",
                                username=new_username.lstrip("@"),
                                account_id=new_user_id,
                            )
                        except Exception:
                            pass
                    st.success(f"✅ 已新增 @{new_username} 到監控清單")
                    st.rerun()
        else:
            st.info("已達 10 個競品上限，請刪除舊帳號後再新增。")

    st.divider()

    # ── Step 4: Email Report Settings ────────────────────────────────────────
    with st.expander("📧 第四步：設定報告寄送信箱", expanded=True):
        st.markdown("""
        **週報將在每週一早上 8 點自動寄出。**
        可設定多個收件人（用逗號分隔）。
        """)

        current_emails = ", ".join(AppSettings.report_emails())
        report_emails = st.text_area(
            "週報收件人 Email（多個請用逗號分隔）",
            value=current_emails,
            placeholder="name@example.com, manager@example.com",
            height=80,
        )

        st.markdown("**Email 發送設定（進階）**")
        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input("郵件伺服器", value=AppSettings.get(AppSettings.SMTP_HOST, "smtp.gmail.com"))
            smtp_user = st.text_input("寄件者 Email", value=AppSettings.get(AppSettings.SMTP_USER, ""))
        with col2:
            smtp_port = st.number_input("Port", value=int(AppSettings.get(AppSettings.SMTP_PORT, "587")), min_value=1, max_value=65535)
            smtp_pass = st.text_input("郵件密碼 / App Password", type="password", placeholder="留空表示不更改")

        if st.button("💾 儲存 Email 設定", key="save_email"):
            if report_emails:
                emails = [e.strip() for e in report_emails.split(",") if e.strip()]
                AppSettings.set_report_emails(emails)
            AppSettings.set(AppSettings.SMTP_HOST, smtp_host)
            AppSettings.set(AppSettings.SMTP_PORT, str(smtp_port))
            AppSettings.set(AppSettings.SMTP_USER, smtp_user)
            if smtp_pass:
                set_secret(Secrets.SMTP_PASSWORD, smtp_pass)
            st.success("✅ Email 設定已儲存")

    st.divider()

    # ── Step 5: Brand Preferences ─────────────────────────────────────────────
    with st.expander("🎨 品牌偏好設定（選填）", expanded=False):
        brand_tone = st.text_area(
            "品牌語氣與風格",
            value=AppSettings.brand_tone(),
            height=100,
            placeholder="例：專業且親切，用詞簡潔有力，避免使用艱深術語…",
            help="AI 生成內容建議時會參考此設定",
        )
        post_target = st.slider("每週目標發文數", min_value=1, max_value=14, value=5)

        claude_key = st.text_input(
            "Claude AI 金鑰（選填，優先使用環境變數 ANTHROPIC_API_KEY）",
            type="password",
            placeholder="sk-ant-...",
        )

        if st.button("💾 儲存品牌偏好", key="save_brand"):
            AppSettings.set(AppSettings.BRAND_TONE, brand_tone)
            AppSettings.set("post_target", str(post_target))
            if claude_key:
                set_secret(Secrets.CLAUDE_API_KEY, claude_key)
            st.success("✅ 品牌偏好已儲存")

    st.divider()

    # ── Save & Activate ───────────────────────────────────────────────────────
    st.subheader("💾 啟動監控")
    st.markdown("""
    完成以上設定後，點擊下方按鈕啟動自動監控排程。
    系統將在每天凌晨 3 點自動抓取數據，每週一早上 8 點生成並寄出週報。
    """)

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🚀 儲存並開始監控", type="primary", key="activate"):
            issues = []
            if not Secrets.threads_token():
                issues.append("• Threads 授權碼尚未設定")
            if not Secrets.ig_token():
                issues.append("• Instagram 授權碼尚未設定")
            if not AppSettings.report_emails():
                issues.append("• 週報收件人 Email 尚未設定")

            if issues:
                st.warning("以下設定尚未完成，部分功能將無法使用：\n" + "\n".join(issues))
            else:
                st.success("🎉 所有設定完成！監控排程已啟動。")
                st.balloons()

    with st.expander("🔒 隱私與安全說明"):
        st.markdown("""
        - 所有授權碼使用 **AES-256 Fernet 對稱加密**儲存於您的本機
        - 加密金鑰存放於 `config/.key`，請妥善保管此檔案
        - **任何資料均不會上傳至第三方伺服器**
        - 若需重置，刪除 `config/secrets.enc` 即可清除所有授權碼
        """)


if __name__ == "__main__":
    render()
