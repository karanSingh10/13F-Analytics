"""
Shared utilities: a polite, retrying HTTP session for SEC endpoints and
small parquet I/O helpers.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

log = logging.getLogger("13f")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

_last_request_ts = 0.0


def make_session() -> requests.Session:
    """Session with automatic retries + exponential backoff.

    Fixes the old pattern of a single requests.get wrapped in a bare
    `except: return None`, which hid every real error (403s, timeouts,
    SEC throttling) and produced 'mysteriously empty' DataFrames.
    """
    session = requests.Session()
    retry = Retry(
        total=config.MAX_RETRIES,
        backoff_factor=1.0,                    # 1s, 2s, 4s, 8s
        status_forcelist=(403, 429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update(config.HEADERS)
    return session


def polite_get(session: requests.Session, url: str, timeout: int = 30) -> requests.Response:
    """GET with SEC rate limiting. Raises on HTTP errors instead of hiding them."""
    global _last_request_ts
    wait = config.REQUEST_DELAY_SECONDS - (time.time() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    resp = session.get(url, timeout=timeout)
    _last_request_ts = time.time()
    resp.raise_for_status()
    return resp


def save_parquet(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    log.info("wrote %s  (%d rows, %d cols)", path.name, len(df), df.shape[1])


def load_parquet(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run the earlier notebook that produces it first "
            f"(notebooks pass data through the /data layer, never call each other)."
        )
    return pd.read_parquet(path)
