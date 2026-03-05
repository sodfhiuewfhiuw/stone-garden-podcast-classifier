"""
health.py — System health tracking for Stone Garden Podcast Classifier

Tracks:
- Consecutive error count → triggers WARNING banner in UI
- Total session analyses and failures
- Active degradation layer
- Last successful analysis timestamp
"""

import time
from dataclasses import dataclass, field
from typing import Optional
import streamlit as st

# Alert thresholds
CONSECUTIVE_ERROR_LIMIT = 2   # consecutive failures before WARNING
ERROR_RATE_LIMIT = 0.30       # 30% failure rate triggers DEGRADED notice
STALE_THRESHOLD_SEC = 600     # 10 min without success → STALE alert


@dataclass
class HealthState:
    total_analyses: int = 0
    total_failures: int = 0
    consecutive_errors: int = 0
    active_layer: int = 1          # 1=full librosa, 2=basic, 3=metadata, 4=record-only
    last_success_ts: Optional[float] = None
    last_error_msg: str = ""
    alerts: list = field(default_factory=list)

    # --- mutation helpers ---

    def record_success(self, layer: int) -> None:
        self.total_analyses += 1
        self.consecutive_errors = 0
        self.active_layer = layer
        self.last_success_ts = time.time()
        self.alerts.clear()

    def record_failure(self, msg: str) -> None:
        self.total_analyses += 1
        self.total_failures += 1
        self.consecutive_errors += 1
        self.last_error_msg = msg
        self._evaluate_alerts()

    def _evaluate_alerts(self) -> None:
        self.alerts = []
        if self.consecutive_errors >= CONSECUTIVE_ERROR_LIMIT:
            self.alerts.append(
                f"CONSECUTIVE_ERRORS: {self.consecutive_errors} failures in a row — "
                f"last error: {self.last_error_msg}"
            )
        if self.total_analyses > 0:
            rate = self.total_failures / self.total_analyses
            if rate >= ERROR_RATE_LIMIT:
                pct = int(rate * 100)
                self.alerts.append(
                    f"HIGH_ERROR_RATE: {pct}% of analyses failed this session"
                )
        if self.last_success_ts is not None:
            elapsed = time.time() - self.last_success_ts
            if elapsed > STALE_THRESHOLD_SEC:
                mins = int(elapsed // 60)
                self.alerts.append(
                    f"STALE: No successful analysis for {mins} minutes"
                )

    # --- read-only properties ---

    @property
    def error_rate(self) -> float:
        if self.total_analyses == 0:
            return 0.0
        return self.total_failures / self.total_analyses

    @property
    def status_label(self) -> str:
        if self.consecutive_errors >= CONSECUTIVE_ERROR_LIMIT:
            return "DEGRADED"
        if self.active_layer == 4:
            return "RECORD-ONLY"
        if self.active_layer > 1:
            return f"FALLBACK-L{self.active_layer}"
        return "HEALTHY"

    @property
    def status_color(self) -> str:
        return {"HEALTHY": "green", "DEGRADED": "red", "RECORD-ONLY": "gray"}.get(
            self.status_label, "orange"
        )


def get_health() -> HealthState:
    """Return (or initialize) the singleton HealthState from session_state."""
    if "health" not in st.session_state:
        st.session_state.health = HealthState()
    return st.session_state.health


def render_health_sidebar(health: HealthState) -> None:
    """Render health status panel in the sidebar."""
    st.sidebar.divider()
    st.sidebar.subheader("System Health")

    label = health.status_label
    color = health.status_color
    st.sidebar.markdown(f"**Status:** :{color}[{label}]")

    cols = st.sidebar.columns(2)
    cols[0].metric("Analyses", health.total_analyses)
    cols[1].metric("Failures", health.total_failures)

    if health.total_analyses > 0:
        pct = int(health.error_rate * 100)
        st.sidebar.metric("Error Rate", f"{pct}%")

    if health.last_success_ts:
        elapsed = int(time.time() - health.last_success_ts)
        st.sidebar.metric("Last OK", f"{elapsed}s ago")

    st.sidebar.caption(f"Active layer: L{health.active_layer}")


def render_alerts(health: HealthState) -> None:
    """Render alert banners at the top of the main content area."""
    for alert in health.alerts:
        if alert.startswith("CONSECUTIVE"):
            st.error(f"ALERT — {alert}")
        elif alert.startswith("HIGH_ERROR"):
            st.warning(f"WARNING — {alert}")
        elif alert.startswith("STALE"):
            st.warning(f"WARNING — {alert}")
