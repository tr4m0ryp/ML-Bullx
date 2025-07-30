"""
Solana Token Labeling Algorithm – Birdeye fallback edition
=========================================================

Adds **automatic fallback to Birdeye** (public REST) when DexScreener has no
listing. This covers most Pump.fun / Photon / micro‑cap Solana tokens that are
missing on DexScreener, without changing the success/rug logic.

How the lookup now works
------------------------
1. **Live price / liquidity**
   * try DexScreener → if no pairs → query
     `GET /public/price` on Birdeye.
2. **Historical 5‑minute candles (≈17 days)**
   * try DexScreener chart → if 404/empty → fetch Birdeye
     `GET /defi/v3/ohlc/single`.
3. **Holder count** still via SolScan.
4. A token is *skipped* only if **both** data sources return nothing.

Birdeye key
-----------
Set an env var **`BIRDEYE_API_KEY`** (free tier = 1 rps – fine for batches).

All other classification logic and CLI flags remain unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import pandas as pd

# ───────────────────────── Logging ──────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("token_labeling.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ──────────────────────── Constants ─────────────────────────
ONE_HOUR = 60 * 60
THREE_DAYS_SEC = 3 * 24 * 60 * 60
SUSTAIN_DAYS_SEC = 7 * 24 * 60 * 60
CANDLE_INTERVAL = "5m"

# DexScreener endpoints
DEX_CHART = (
    "https://api.dexscreener.com/latest/dex/chart/tokens/{mint}?interval="
    + CANDLE_INTERVAL + "&limit=5000"
)
DEX_TOKEN = "https://api.dexscreener.com/latest/dex/tokens/{mint}"

# Birdeye endpoints
BIRDEYE_PRICE = "https://public-api.birdeye.so/public/price?address={mint}"
BIRDEYE_OHLC = (
    "https://public-api.birdeye.so/defi/v3/ohlc/single?address={mint}&interval="
    + CANDLE_INTERVAL + "&from={start}&to={end}"
)

# SolScan
SOLSCAN_HOLDERS = "https://public-api.solscan.io/token/holders?account={mint}&limit=0"

# ─────────────────── Dataclass per token ────────────────────
@dataclass
class TokenMetrics:
    mint_address: str
    current_price: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None
    has_sustained_drop: bool = False
    price_drops: List[Tuple[datetime, float]] = None
    holder_count: Optional[int] = None

    def __post_init__(self):
        if self.price_drops is None:
            self.price_drops = []

# ─────────────────────── TokenLabeler ───────────────────────
class TokenLabeler:
    RUG_THRESHOLD = 0.70
    SUCCESS_APPRECIATION = 10.0
    SUCCESS_MIN_HOLDERS = 100

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.birdeye_key = os.getenv("BIRDEYE_API_KEY", "")
        if not self.birdeye_key:
            logger.warning("BIRDEYE_API_KEY env var not set – Birdeye fallback will likely 429")

    # ── async context ──
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(raise_for_status=False, timeout=aiohttp.ClientTimeout(total=20))
        return self

    async def __aexit__(self, *exc):
        if self.session:
            await self.session.close()

    # ────────── CSV driver ──────────
    async def label_tokens_from_csv(self, inp: str, out: str, batch: int = 50) -> pd.DataFrame:
        df = pd.read_csv(inp)
        if "mint_address" not in df.columns:
            raise ValueError("CSV must contain 'mint_address' column")
        mints = df["mint_address"].tolist()

        results: List[Tuple[str, str]] = []
        for i in range(0, len(mints), batch):
            chunk = mints[i:i + batch]
            logger.info("Batch %d/%d (size=%d)", i // batch + 1, (len(mints) + batch - 1) // batch, len(chunk))
            out_chunk = await asyncio.gather(*[self._process(m) for m in chunk])
            results.extend([r for r in out_chunk if r is not None])
            if i + batch < len(mints):
                await asyncio.sleep(1)

        out_df = pd.DataFrame(results, columns=["mint_address", "label"])
        out_df.to_csv(out, index=False)
        logger.info("Saved %d labeled tokens → %s", len(out_df), out)
        return out_df

    # ────────── Per‑token flow ──────────
    async def _process(self, mint: str) -> Optional[Tuple[str, str]]:
        m = await self._gather_metrics(mint)
        if not self._has_any_data(m):
            logger.info("%s – skipped (no DexScreener nor Birdeye nor SolScan data)", mint)
            return None
        return mint, self._classify(m)

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _has_any_data(m: TokenMetrics) -> bool:
        return (m.current_price is not None) or (m.holder_count is not None)

    async def _gather_metrics(self, mint: str) -> TokenMetrics:
        t = TokenMetrics(mint)

        # 1. price / liquidity ------------------------------------------------
        dex = await self._safe_json(DEX_TOKEN.format(mint=mint))
        if dex and dex.get("pairs"):
            pair = max(dex["pairs"], key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            t.current_price = float(pair.get("priceUsd", 0) or 0)
            t.volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
            t.market_cap = float(pair.get("marketCap", 0) or 0)
        else:
            price = await self._birdeye_price(mint)
            if price is not None:
                t.current_price = price

        # 2. historical candles ---------------------------------------------
        hist = await self._historical_metrics(mint)
        t.__dict__.update(hist)

        # 3. holders ---------------------------------------------------------
        t.holder_count = await self._holder_count(mint)
        return t

    # ---------- network helpers ----------------
    async def _safe_json(self, url: str, headers: Optional[Dict[str, str]] = None) -> Any:
        try:
            async with self.session.get(url, headers=headers) as r:
                if r.status == 200:
                    return await r.json()
                if r.status == 404:
                    return None
                logger.debug("%s → HTTP %d", url, r.status)
                return None
        except Exception as e:
            logger.debug("%s fetch error: %s", url, e)
            return None

    # Birdeye helpers -------------------------------------------------------
    def _be_headers(self) -> Dict[str, str]:
        return {"X-API-KEY": self.birdeye_key} if self.birdeye_key else {}

    async def _birdeye_price(self, mint: str) -> Optional[float]:
        data = await self._safe_json(BIRDEYE_PRICE.format(mint=mint), headers=self._be_headers())
        try:
            return float(data["data"]["value"])
        except Exception:
            return None

    async def _birdeye_candles(self, mint: str) -> List[Dict[str, Any]]:
        now = int(time.time())
        start = now - 17 * 24 * 60 * 60  # ~17 days back (≈5000×5‑min)
        url = BIRDEYE_OHLC.format(mint=mint, start=start, end=now)
        data = await self._safe_json(url, headers=self._be_headers())
        if not data or "data" not in data:
            return []
        candles = []
        for entry in data["data"]:
            # Birdeye returns [ts, o, h, l, c]
            ts, o, h, l, c = entry
            candles.append({"t": ts, "o": o, "h": h, "l": l, "c": c})
        return candles

    # Historical metrics with fallback -------------------------------------
    async def _historical_metrics(self, mint: str) -> Dict[str, Any]:
        candles = await self._safe_json(DEX_CHART.format(mint=mint))
        if not candles:
            candles = await self._birdeye_candles(mint)
        if not candles:
            return {}

        df = pd.DataFrame(candles)
        df["t"] = pd.to_datetime(df["t"], unit="s")
        df.sort_values("t", inplace=True)
        launch = df["t"].iloc[0]
        cut = launch + timedelta(seconds=THREE_DAYS_SEC)
        ath_3d = df.loc[df["t"] <= cut, "h"].max()
        if pd.isna(ath_3d):
            return {}
        post_df = df.loc[df["t"] > cut]
        if post_df.empty:
            return {}
        post_peak = post_df["h"].max()

        roll: deque[Tuple[datetime, float]] = deque()
        bad, drops = False, []
        for _, row in post_df.iterrows():
            ts = row["t"]
            while roll and (ts - roll[0][0]).total_seconds() > SUSTAIN_DAYS_SEC:
                roll.popleft()
            roll.append((ts, row["h"]))
            peak = max(h for _, h in roll)
            drop_pct = 1 - row["l"] / peak if peak else 0
            if drop_pct >= 0.5:
                bad = True
            if drop_pct >= 0.7 and (ts - roll[-1][0]).total_seconds() <= ONE_HOUR:
                drops.append((ts.to_pydatetime(), drop_pct))

        return {
            "peak_price_72h": float(ath_3d),
            "post_ath_peak_price": float(post_peak),
            "has_sustained_drop": bad,
            "price_drops": drops,
        }

    async def _holder_count(self, mint: str) -> Optional[int]:
        data = await self._safe_json(SOLSCAN_HOLDERS.format(mint=mint))
        return len(data) if isinstance(data, list) else None

    # ---------- classification ------------------
    def _classify(self, m: TokenMetrics) -> str:
        if m.current_price is None:
            return "unsuccessful"
        if any(d >= self.RUG_THRESHOLD for _, d in m.price_drops):
            return "rugpull"
        if self._is_success(m):
            return "successful"
        return "unsuccessful"

    def _is_success(self, m: TokenMetrics) -> bool:
        if None in (m.peak_price_72h, m.post_ath_peak_price, m.holder_count):
            return False
        if m.holder_count < self.SUCCESS_MIN_HOLDERS:
            return False
        if m.post_ath_peak_price / m.peak_price_72h < self.SUCCESS_APPRECIATION:
            return False
        if m.has_sustained_drop:
            return False
        return True

# ───────────────────────── CLI wrapper ─────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Label Solana tokens")
    parser.add_argument("--input", required=True, help="CSV with 'mint_address' column")
    parser.add_argument("--output", required=True, help="output CSV path")
    parser.add_argument("--batch", type=int, default=50, help="batch size (default 50)")
    args = parser.parse_args()

    async def runner():
        async with TokenLabeler() as tl:
            await tl.label_tokens_from_csv(args.input, args.output, args.batch)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
