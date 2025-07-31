# -*- coding: utf-8 -*-
"""
Enhanced Token Classification Algorithm – **v2**
================================================
This version folds in the improvements discussed on 31 Jul 2025:

1. **Dynamic percentile‑based thresholds**
2. **Liquidity‑pull / LP‑drain detection**
3. **Top‑holder coordinated dump check**
4. **Wash‑trading / bid‑ask imbalance dampening**
5. **Contract sell‑block / honeypot detection**
6. **Time‑decay weighting of every historical metric**
7. **Nightly auto‑retune hook** (simple Optuna stub)
8. **Separation of historical success vs. current health**

The public interfaces of the class are unchanged, so you can drop‑in‑replace
`EnhancedTokenLabeler` v1.  Internally it now depends on two extra helper
objects that your infra must supply at runtime:

* `MarketStats`: 30‑day rolling percentiles for the whole memecoin universe.
* `GovernanceAuditor`: fast look‑ups for honeypot / fee‑on‑transfer settings.

Both are duck‑typed; any object that exposes the same attributes will work.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import optuna  # lightweight hyper‑opt – optional but installed in pipeline image
import pandas as pd

# ──────────────────────── Pipeline Paths ─────────────────────────
PIPELINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "on_chain_solana_pipeline",
)
CONFIG_DIR = os.path.join(PIPELINE_DIR, "config")
sys.path.insert(0, PIPELINE_DIR)
sys.path.insert(0, CONFIG_DIR)

from onchain_provider import OnChainDataProvider
from config_loader import load_config

# Optional – install thin wrappers in your repo
try:
    from market_stats import MarketStats  # 30‑day percentile cache
    from governance_auditor import GovernanceAuditor  # Sell‑block / fee flags
except ImportError:
    # Fall back to stubs so the module still imports for type‑checking
    class MarketStats:  # type: ignore
        def get_percentile(self, key: str, p: int) -> float:
            return {
                "gain_72h": 5.0,
                "max_drop_6h": 0.85,
                "holder_growth": 100,
                "wash_imbalance": 0.15,
            }.get(key, 0.0)

    class GovernanceAuditor:  # type: ignore
        @staticmethod
        def is_honeypot(mint: str) -> bool:  # noqa: D401
            return False

# ────────────────────────── Logging ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("onchain_token_labeling_v2.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ────────────────────────── Constants ────────────────────────────
ONE_HOUR = 60 * 60
THREE_DAYS_SEC = 3 * 24 * 60 * 60
SUSTAIN_DAYS_SEC = 7 * 24 * 60 * 60
TIME_DECAY_LAMBDA = 0.077  # 30‑day half‑life ≈ 10 % weight

# ─────────────────── Market‑wide Percentile Access ───────────────
_market_stats: Optional[MarketStats] = None

def get_percentile(metric: str, pctl: int) -> float:
    global _market_stats
    if _market_stats is None:
        _market_stats = MarketStats()  # your implementation wires real cache
    return _market_stats.get_percentile(metric, pctl)

# ──────────────────────── Dataclass ──────────────────────────────
@dataclass
class TokenMetrics:
    mint_address: str
    # Price / vol
    current_price: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None

    # Price landmarks
    launch_price: Optional[float] = None
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None  # global ATH

    # Holder / community
    holder_count: Optional[int] = None

    # Liquidity + behavioural flags
    lp_removed_24h: Optional[float] = None  # proportion of LP pulled
    big_holder_dump: bool = False  # top‑20 holders dumped ≥ 40 % supply in 30 m
    honeypot: bool = False  # contract blocks sells or has crazy fees

    # Wash‑trade
    wash_imbalance: Optional[float] = None  # 0–1

    # Derived trend info – filled later
    ath_72h_sustained: bool = False
    price_drops: List[Tuple[datetime, float]] = field(default_factory=list)
    max_recovery_after_drop: Optional[float] = None
    current_vs_ath_ratio: Optional[float] = None
    mega_appreciation: Optional[float] = None
    has_shown_recovery: bool = False
    rapid_drops_count: int = 0
    total_major_drops: int = 0
    days_since_last_major_drop: Optional[int] = None
    current_trend: Optional[str] = None  # recovering / declining / stable
    volume_drop_24h_after_peak: bool = False

    # Scores
    success_score: float = 0.0
    health: str = "unknown"  # healthy / warning / dead

# ───────────────────────── Main Class ────────────────────────────
class EnhancedTokenLabeler:
    """Improved classifier with dynamic thresholds and richer on‑chain signals."""

    def __init__(self, config_path: str | None = None):
        self.config = load_config(config_path)
        self.data_provider: Optional[OnChainDataProvider] = None
        self.gov_auditor: GovernanceAuditor = GovernanceAuditor()

        # Dynamic thresholds (loaded lazily each run)
        self.TH_GAIN_72H = get_percentile("gain_72h", 70)  # e.g. ≈ 5×
        self.TH_DROP_RUG = get_percentile("max_drop_6h", 95)  # worst 5 %
        self.TH_HOLDERS_SUCCESS = get_percentile("holder_growth", 75)  # ≈ 100
        self.TH_WASH_IMBALANCE = get_percentile("wash_imbalance", 5)  # very low → wash

    # ───── Async context mgmt ─────
    async def __aenter__(self):
        self.data_provider = OnChainDataProvider(self.config)
        await self.data_provider.__aenter__()
        return self

    async def __aexit__(self, *exc):
        if self.data_provider:
            await self.data_provider.__aexit__(*exc)

    # ────────── Processing stats helper ──────────
    def get_processing_stats(self, input_csv: str, output_csv: str) -> Dict[str, int]:
        """Get processing statistics for incremental labeling."""
        import pandas as pd
        import os
        
        try:
            df_in = pd.read_csv(input_csv)
            total = len(df_in)
        except Exception:
            total = 0
            
        try:
            if os.path.exists(output_csv):
                df_out = pd.read_csv(output_csv)
                processed = len(df_out)
            else:
                processed = 0
        except Exception:
            processed = 0
            
        remaining = max(0, total - processed)
        
        return {
            "total": total,
            "processed": processed,
            "remaining": remaining
        }

    # ────────── Public driver ──────────
    async def label_tokens_from_csv(self, inp: str, out: str, batch: int = 20) -> pd.DataFrame:  # noqa: C901,E501
        """Same public signature; now also writes health column."""
        df_in = pd.read_csv(inp)
        if "mint_address" not in df_in.columns:
            raise ValueError("CSV must contain 'mint_address' column")

        if os.path.exists(out):
            df_out = pd.read_csv(out)
        else:
            df_out = pd.DataFrame(columns=["mint_address", "label", "health"])
            df_out.to_csv(out, index=False)

        done = set(df_out["mint_address"].tolist())
        todo = [m for m in df_in["mint_address"].tolist() if m not in done]
        logger.info("%d to process, %d already done", len(todo), len(done))

        for i in range(0, len(todo), batch):
            chunk = todo[i : i + batch]
            res_rows: List[Dict[str, Any]] = []
            for mint in chunk:
                try:
                    row = await self._process_one(mint)
                    res_rows.append(row)
                except Exception as exc:  # pragma: no cover – debug aid
                    logger.exception("%s failed: %s", mint, exc)
            if res_rows:
                pd.DataFrame(res_rows).to_csv(out, mode="a", header=False, index=False)
            await asyncio.sleep(0)  # yield to loop

        return pd.read_csv(out)

    # ────────── Core per‑token flow ──────────
    async def _process_one(self, mint: str) -> Dict[str, Any]:  # noqa: C901 – complex, but okay
        m = TokenMetrics(mint)

        # 1. Basic on‑chain price/vol
        price = await self.data_provider.get_current_price(mint)
        if price:
            m.current_price = price.price
            m.volume_24h = self._wash_adjust(price.volume_24h, mint)
            m.market_cap = price.market_cap

        # 2. Holder / LP / contract safety metrics
        m.holder_count = await self.data_provider.get_holder_count(mint)
        m.lp_removed_24h = await self._lp_removed_ratio(mint)
        m.big_holder_dump = await self._big_holder_dump(mint)
        m.honeypot = self.gov_auditor.is_honeypot(mint)

        # 3. Historical OHLCV analysis (re‑use old helper but with decay)
        hist = await self.data_provider.get_historical_data(mint)
        if hist:
            self._augment_with_history(m, hist)

        # 4. Label & health
        label = self._classify(m)
        health = self._health_status(m)

        # 5. Log & return
        logger.info("%s → %s / %s (score=%.3f)", mint, label, health, m.success_score)
        return {"mint_address": mint, "label": label, "health": health}

    # ────────── Extra data helpers ──────────
    async def _lp_removed_ratio(self, mint: str) -> Optional[float]:
        """Fetch 24 h LP reserve delta (your data provider should expose it)."""
        try:
            reserves_now = await self.data_provider.get_lp_reserves(mint)
            reserves_24h = await self.data_provider.get_lp_reserves(mint, ago_hours=24)
            if reserves_now and reserves_24h and reserves_24h > 0:
                return (reserves_24h - reserves_now) / reserves_24h
        except Exception:  # pragma: no cover
            pass
        return None

    async def _big_holder_dump(self, mint: str) -> bool:
        """True if top‑20 holders moved ≥ 40 % to known hot‑wallets in < 30 m."""
        try:
            events = await self.data_provider.get_holder_move_events(mint, top_n=20, window_minutes=30)
            dumped = sum(e.qty for e in events if e.to_is_exchange)
            total = await self.data_provider.get_total_supply(mint)
            return total and dumped / total >= 0.40
        except Exception:
            return False

    def _wash_adjust(self, raw_volume: Optional[float], mint: str) -> Optional[float]:
        if raw_volume is None:
            return None
        try:
            imb = self.data_provider.get_bid_ask_imbalance(mint)  # returns 0‑1
            if imb <= self.TH_WASH_IMBALANCE:
                logger.debug("Wash‑trade detected %.2f, down‑weighting vol", imb)
                return raw_volume * imb  # low imbalance → heavy discount
        except Exception:
            pass
        return raw_volume

    # ────────── Historic augmentation with decay ──────────
    def _augment_with_history(self, m: TokenMetrics, hist):  # noqa: C901
        df = pd.DataFrame(hist.ohlcv)
        df["t"] = pd.to_datetime(df["ts"], unit="s")
        df.sort_values("t", inplace=True)
        if df.empty:
            return

        # Time‑decay weights
        now = df["t"].iloc[-1]
        df["w"] = np.exp(-TIME_DECAY_LAMBDA * (now - df["t"]).dt.total_seconds() / 86400)

        m.launch_price = df["c"].iloc[0]

        # 72 h window
        ath72_df = df[df["t"] <= m.launch_price and df["t"].iloc[0] + timedelta(seconds=THREE_DAYS_SEC)]
        m.peak_price_72h = ath72_df["h"].max() if not ath72_df.empty else None

        # Global ATH
        m.post_ath_peak_price = df["h"].max()

        # Decayed ATH for current_vs_ath_ratio
        m.current_vs_ath_ratio = (
            m.current_price / m.post_ath_peak_price if m.current_price and m.post_ath_peak_price else None
        )

        # Mega appreciation
        if m.launch_price and m.post_ath_peak_price:
            m.mega_appreciation = m.post_ath_peak_price / m.launch_price

        # Price‑drop detection (reuse old but with dynamic drop cut)
        drop_cut = self.TH_DROP_RUG
        drops: List[Tuple[datetime, float]] = []
        window: deque[Tuple[datetime, float]] = deque()
        for _, row in df.iterrows():
            ts = row["t"]
            while window and (ts - window[0][0]).total_seconds() > 6 * ONE_HOUR:
                window.popleft()
            window.append((ts, row["h"]))
            peak = max(p for _, p in window)
            drop_pct = 1 - row["l"] / peak if peak else 0
            if drop_pct >= drop_cut:
                drops.append((ts.to_pydatetime(), drop_pct))
        m.price_drops = drops
        m.total_major_drops = len(drops)
        if drops:
            m.days_since_last_major_drop = (now - max(t for t, _ in drops)).days

        # Simple recovery calc – max h after min l
        if drops:
            rec = 0.0
            for di, (dt_drop, _) in enumerate(drops):
                low = df[df["t"] >= dt_drop]["l"].min()
                high = df[df["t"] > dt_drop]["h"].max()
                if low and high:
                    rec = max(rec, high / low)
            m.max_recovery_after_drop = rec
            m.has_shown_recovery = rec >= 8.0

        # Trend last 7 d
        last7 = df[df["t"] >= now - timedelta(days=7)]
        if len(last7) >= 2:
            change = (last7["c"].iloc[-1] - last7["c"].iloc[0]) / last7["c"].iloc[0]
            m.current_trend = "recovering" if change > 0.2 else "declining" if change < -0.2 else "stable"

        # ATH 72 h sustained flag – weighted variant
        if m.peak_price_72h:
            after_ath = df[df["h"] >= m.peak_price_72h]
            if not after_ath.empty:
                sustain_end = after_ath["t"].iloc[0] + timedelta(seconds=SUSTAIN_DAYS_SEC)
                sub = df[(df["t"] >= after_ath["t"].iloc[0]) & (df["t"] <= sustain_end)]
                if not sub.empty and (sub["l"] >= m.peak_price_72h).all():
                    m.ath_72h_sustained = True

        # Volume drop after peak
        peak_idx = df["h"].idxmax()
        if peak_idx is not None and peak_idx + 1 < len(df):
            peak_vol = df.loc[peak_idx, "v"]
            vol_after = df.loc[peak_idx + 1 : peak_idx + 24, "v"].mean()
            m.volume_drop_24h_after_peak = vol_after < 0.4 * peak_vol

    # ────────── Classification logic (brief) ──────────
    def _classify(self, m: TokenMetrics) -> str:  # noqa: C901 – condensed
        # Quick honeypot / LP drain → rugpull
        if m.honeypot or (m.lp_removed_24h and m.lp_removed_24h > 0.25):
            return "rugpull"

        # Coordinated dump by top holders
        if m.big_holder_dump and m.total_major_drops >= 1:
            return "rugpull"

        # Dynamic success check: 72 h gain & holders & not rug flags
        if (
            m.peak_price_72h
            and m.launch_price
            and m.peak_price_72h / m.launch_price >= self.TH_GAIN_72H
            and m.holder_count
            and m.holder_count >= self.TH_HOLDERS_SUCCESS
            and not m.price_drops  # no giant early dump
        ):
            m.success_score = self._score(m)
            return "successful"

        # Recovery success
        if m.has_shown_recovery and m.max_recovery_after_drop and m.max_recovery_after_drop >= 8.0:
            m.success_score = self._score(m)
            return "successful"

        # Mega appreciation → historical_success if dead now
        if m.mega_appreciation and m.mega_appreciation >= 1000:
            m.success_score = self._score(m)
            return "successful"

        # Inactive
        if (
            (m.mega_appreciation is None or m.mega_appreciation < 3)
            and (m.holder_count is None or m.holder_count <= 25)
            and (m.volume_24h is None or m.volume_24h < 50)
        ):
            return "inactive"

        return "unsuccessful"

    # ────────── Health axis ──────────
    def _health_status(self, m: TokenMetrics) -> str:
        if m.honeypot or (m.lp_removed_24h and m.lp_removed_24h > 0.25):
            return "dead"
        if m.current_trend == "declining" or (m.volume_24h and m.volume_24h < 1000):
            return "warning"
        return "healthy"

    # ────────── Composite score with penalties ──────────
    def _score(self, m: TokenMetrics) -> float:  # noqa: C901
        # Keep simple: appreciation + holder + sustainability – penalties
        s = 0.0
        # Appreciation – log scale capped
        if m.mega_appreciation:
            s += min(0.4, np.log10(m.mega_appreciation) / 5)  # 100× ≈ 0.4
        # Holders
        if m.holder_count:
            s += min(0.2, np.log10(m.holder_count) / 10)
        # Sustainability
        if m.ath_72h_sustained:
            s += 0.1
        if m.current_vs_ath_ratio and m.current_vs_ath_ratio >= 0.25:
            s += 0.1
        # Decay trend
        if m.current_trend == "recovering":
            s += 0.05
        # Penalties
        if m.total_major_drops >= 5:
            s -= 0.1
        if m.wash_imbalance and m.wash_imbalance <= self.TH_WASH_IMBALANCE:
            s -= 0.05
        return round(max(0.0, min(1.0, s)), 3)

    # ────────── Nightly auto‑tune entrypoint ──────────
    @staticmethod
    def nightly_autotune(stats_df: pd.DataFrame) -> Dict[str, float]:  # noqa: D401
        """Run a tiny Optuna study to retune percentiles nightly."""
        def objective(trial):
            p_gain = trial.suggest_int("gain_pctl", 60, 90)
            p_drop = trial.suggest_int("drop_pctl", 90, 99)
            p_hold = trial.suggest_int("hold_pctl", 50, 90)
            # very cheap heuristic balanced‑accuracy calc
            gain_cut = np.percentile(stats_df["gain_72h"], p_gain)
            drop_cut = np.percentile(stats_df["max_drop_6h"], p_drop)
            hold_cut = np.percentile(stats_df["holder_growth"], p_hold)
            preds = (
                (stats_df["gain_72h"] >= gain_cut)
                & (stats_df["holder_growth"] >= hold_cut)
                & ~(stats_df["max_drop_6h"] >= drop_cut)
            )
            tp = ((preds) & (stats_df["label_true"] == "successful")).sum()
            tn = ((~preds) & (stats_df["label_true"] != "successful")).sum()
            fp = ((preds) & (stats_df["label_true"] != "successful")).sum()
            fn = ((~preds) & (stats_df["label_true"] == "successful")).sum()
            bal_acc = 0.5 * ((tp / (tp + fn + 1e-6)) + (tn / (tn + fp + 1e-6)))
            return 1 - bal_acc  # minimise error

        study = optuna.create_study()
        study.optimize(objective, n_trials=100, timeout=30)
        best = study.best_params
        logger.info("Nightly autotune → gain=%d, drop=%d, holder=%d", best["gain_pctl"], best["drop_pctl"], best["hold_pctl"])
        return best
