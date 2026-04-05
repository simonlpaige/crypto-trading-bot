"""
Kraken API client — used ONLY for fetching price data.
No order placement ever happens through this client.
"""
import logging
import time
from typing import Optional, Dict, Any

import krakenex
from pykrakenapi import KrakenAPI

import config

logger = logging.getLogger("cryptobot.kraken")


class KrakenClient:
    """Thin wrapper around krakenex for price data."""

    def __init__(self):
        self._api = krakenex.API()
        self._api.key = config.KRAKEN_API_KEY
        self._api.secret = config.KRAKEN_PRIVATE_KEY
        self._k = KrakenAPI(self._api)
        self._last_call = 0.0
        self._min_interval = 2.0  # Kraken rate-limit courtesy

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.time()

    def get_ticker(self, pair: str = config.PAIR) -> Optional[Dict[str, Any]]:
        """Return ticker dict with 'ask', 'bid', 'last' as floats."""
        try:
            self._throttle()
            resp = self._api.query_public("Ticker", {"pair": pair})
            if resp.get("error"):
                logger.error("Kraken Ticker error: %s", resp["error"])
                return None
            data = list(resp["result"].values())[0]
            return {
                "ask": float(data["a"][0]),
                "bid": float(data["b"][0]),
                "last": float(data["c"][0]),
                "volume_24h": float(data["v"][1]),
                "high_24h": float(data["h"][1]),
                "low_24h": float(data["l"][1]),
            }
        except Exception as e:
            logger.exception("Failed to fetch ticker: %s", e)
            return None

    def get_ohlc(self, pair: str = config.PAIR, interval: int = 60, count: int = 100):
        """Return OHLC as list of dicts with open/high/low/close/volume keys.
        
        Uses raw Kraken API to avoid pykrakenapi pandas freq bug.
        """
        try:
            self._throttle()
            resp = self._api.query_public("OHLC", {"pair": pair, "interval": interval})
            if resp.get("error"):
                logger.error("Kraken OHLC error: %s", resp["error"])
                return None
            # Result has pair key + "last" key
            result = resp.get("result", {})
            # Remove 'last' key, get the pair data
            pair_data = None
            for k, v in result.items():
                if k != "last" and isinstance(v, list):
                    pair_data = v
                    break
            if not pair_data:
                return None
            # Each entry: [time, open, high, low, close, vwap, volume, count]
            records = []
            for candle in pair_data:
                records.append({
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[6]),
                })
            return records[-count:] if len(records) > count else records
        except Exception as e:
            logger.exception("Failed to fetch OHLC: %s", e)
            return None
