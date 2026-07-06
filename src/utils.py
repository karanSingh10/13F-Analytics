# shared utilities - HTTP session with retries and parquet read/write helpers
# nothing too fancy here, just making sure we dont hammer the SEC servers
# and that errors actually show up instead of silently returning None

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


def make_session():
    # retries with backoff so we dont crash on temporary SEC errors
    # 403, 429, 500 etc will retry automatically up to MAX_RETRIES times
    session = requests.Session()
    retry = Retry(
        total=config.MAX_RETRIES,
        backoff_factor=1.0,
        status_forcelist=(403, 429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update(config.HEADERS)
    return session


def polite_get(session, url, timeout=30):
    # sleep between requests so we stay under SEC rate limit
    # raises on HTTP errors instead of returning None and hiding the problem
    global _last_request_ts
    wait = config.REQUEST_DELAY_SECONDS - (time.time() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    resp = session.get(url, timeout=timeout)
    _last_request_ts = time.time()
    resp.raise_for_status()
    return resp


def save_parquet(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    log.info("saved %s  (%d rows)", path.name, len(df))


def load_parquet(path):
    if not path.exists():
        raise FileNotFoundError(
            f"cant find {path} - make sure you ran the earlier notebook that creates it"
        )
    return pd.read_parquet(path)
