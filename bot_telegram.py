
"""
SMART PUMP FINDER — Bot Telegram (Multi-Source)

Setup:
  1) pip install requests
  2) Defina as variáveis de ambiente:
     TELEGRAM_TOKEN, CHAT_ID, CMC_API_KEY (opcional),
     BINANCE_API_KEY, BINANCE_API_SECRET,
     BYBIT_API_KEY, BYBIT_API_SECRET
  3) python bot_telegram.py
"""

import os
import json
import html as html_lib
import re
import time
import logging
import threading
import hmac
import hashlib
from urllib.parse import urlencode, urlparse, parse_qs
import requests
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional

# =========================
# Configuração (ENV)
# =========================
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", os.getenv("SPF_BOT_TOKEN", os.getenv("BOT_TOKEN", ""))).strip()
CHAT_ID = os.getenv("CHAT_ID", os.getenv("SPF_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))).strip()
CMC_API_KEY = os.getenv("CMC_API_KEY", os.getenv("SPF_CMC_API_KEY", "")).strip()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "").strip()
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", os.getenv("SPF_DISCORD_WEBHOOK_URL", "")).strip()
GENERIC_WEBHOOK_URL = os.getenv("WEBHOOK_URL", os.getenv("SPF_WEBHOOK_URL", "")).strip()
SIGNALS_API_KEY = os.getenv("SPF_SIGNALS_API_KEY", "").strip()
SIGNALS_CORS_ORIGIN = os.getenv("SPF_SIGNALS_CORS_ORIGIN", "*").strip() or "*"

PUMP_MIN = int(os.getenv("SPF_PUMP_MIN", "300"))
EXPLOSION_MIN = int(os.getenv("SPF_EXPLOSION_MIN", "500"))
MEGA_MIN = int(os.getenv("SPF_MEGA_MIN", "1000"))
PRE_PUMP_MIN = int(os.getenv("SPF_PRE_PUMP_MIN", "100"))
PRE_PUMP_MAX = int(os.getenv("SPF_PRE_PUMP_MAX", "299"))

MIN_VOLUME_USDT = float(os.getenv("SPF_MIN_VOLUME_USDT", "50000"))
MIN_FUTURES_VOLUME_USDT = float(os.getenv("SPF_MIN_FUTURES_VOLUME_USDT", str(MIN_VOLUME_USDT)))
MIN_MARKET_CAP_USD = float(os.getenv("SPF_MIN_MARKET_CAP_USD", "0"))
MAX_CMC_RANK = int(os.getenv("SPF_MAX_CMC_RANK", "0"))

INTERVAL_SECS = int(os.getenv("SPF_INTERVAL_SECS", "30"))
SUMMARY_INTERVAL_MINS = int(os.getenv("SPF_SUMMARY_INTERVAL_MINS", "15"))
COOLDOWN_SECS = int(os.getenv("SPF_COOLDOWN_SECS", "3600"))
KEEPALIVE_PORT = int(os.getenv("SPF_KEEPALIVE_PORT", "10000"))

USER_AGENT = os.getenv(
    "SPF_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT_SECS = int(os.getenv("SPF_HTTP_TIMEOUT_SECS", "10"))
HTTP_TIMEOUT_CMC_SECS = int(os.getenv("SPF_HTTP_TIMEOUT_CMC_SECS", "12"))
RETRY_ATTEMPTS = int(os.getenv("SPF_HTTP_RETRIES", "3"))
RETRY_DELAY_SECS = float(os.getenv("SPF_HTTP_RETRY_DELAY_SECS", "1.2"))
BINANCE_451_COOLDOWN_SECS = int(os.getenv("SPF_BINANCE_451_COOLDOWN_SECS", "900"))

BINANCE_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=linear"
CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
BINANCE_FAPI_BASE = "https://fapi.binance.com"
BYBIT_API_BASE = "https://api.bybit.com"
HISTORY_FILE = os.getenv("SPF_HISTORY_FILE", "pump_history.json")
METRICS_TTL_SECS = int(os.getenv("SPF_METRICS_TTL_SECS", "30"))
VOLUME_WEAKEN_RATIO = float(os.getenv("SPF_VOLUME_WEAKEN_RATIO", "0.85"))
SHORT_VOL_WINDOW_SECS = int(os.getenv("SPF_SHORT_VOL_WINDOW_SECS", "60"))
SPEED_RISE_MIN_PER_MIN = float(os.getenv("SPF_SPEED_RISE_MIN_PER_MIN", "80"))
ORDERBOOK_SELL_RATIO = float(os.getenv("SPF_ORDERBOOK_SELL_RATIO", "1.2"))
FUNDING_RATE_HIGH = float(os.getenv("SPF_FUNDING_RATE_HIGH", "0.01"))
OPEN_INTEREST_DROP_RATIO = float(os.getenv("SPF_OI_DROP_RATIO", "0.05"))
DISTANCE_RISK_PCT = float(os.getenv("SPF_DISTANCE_RISK_PCT", "500"))
SHORT_MIN_INDICATORS = int(os.getenv("SPF_SHORT_MIN_INDICATORS", "3"))
SHORT_MIN_PCT = int(os.getenv("SPF_SHORT_MIN_PCT", "300"))
MAX_SIGNAL_COINS = int(os.getenv("SPF_MAX_SIGNAL_COINS", "20"))
MIN_OPEN_INTEREST_USD = float(os.getenv("SPF_MIN_OPEN_INTEREST_USD", "0"))
FAKE_PUMP_VOL_USD = float(os.getenv("SPF_FAKE_PUMP_VOL_USD", "0"))
FAKE_PUMP_OI_STABLE_RATIO = float(os.getenv("SPF_FAKE_PUMP_OI_STABLE_RATIO", "0.01"))
SHORT_STOP_BUFFER_PCT = float(os.getenv("SPF_SHORT_STOP_BUFFER_PCT", "8"))
SHORT_TP1_PCT = float(os.getenv("SPF_SHORT_TP1_PCT", "10"))
SHORT_TP2_PCT = float(os.getenv("SPF_SHORT_TP2_PCT", "20"))
RESET_HISTORY_ON_START = os.getenv("SPF_RESET_HISTORY_ON_START", "1").strip().lower() in ("1", "true", "yes", "y", "on")
RESET_RUNTIME_ON_START = os.getenv("SPF_RESET_RUNTIME_ON_START", "1").strip().lower() in ("1", "true", "yes", "y", "on")
AUTH_PRIORITY_FAKE_PUMP = os.getenv("SPF_AUTH_PRIORITY_FAKE_PUMP", "1").strip().lower() in ("1", "true", "yes", "y", "on")
DATA_STALE_RESET_SECS = int(os.getenv("SPF_DATA_STALE_RESET_SECS", "300"))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("SPF")

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/json"
})
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json"
}

# =========================
# Modelos
# =========================
@dataclass
class Ticker:
    symbol: str
    exchange: str
    last_price: float
    open_price: float
    change_pct: float
    quote_volume: float
    meta: Optional[Dict] = None

@dataclass
class AggregatedCoin:
    symbol: str
    base: str
    sources: Dict[str, Ticker]
    max_change: float
    total_volume: float
    pump_sources: List[str]
    priority: bool
    market_cap: Optional[float]
    cmc_rank: Optional[int]
    multi_source: bool

# =========================
# Utilidades
# =========================
EXCHANGE_LABELS = {
    "binance": "Binance",
    "bybit": "Bybit",
    "cmc": "CoinMarketCap"
}

PROGRESSIVE_LEVELS = [
    ("p100", 100, "Moeda em movimento — +100%", "Movimento inicial confirmado"),
    ("p200", 200, "Atenção — +200%, monitorar", "Aceleração detectada"),
    ("p299", 299, "Zona crítica — próximo dos 300%", "Perto do limiar de pump"),
    ("p300", 300, "Pump confirmado", "Pump confirmado — acima de +300%"),
    ("p500", 500, "Alerta de explosão", "Explosão acima de +500%"),
    ("p1000", 1000, "Alerta mega", "Mega pump acima de +1000%")
]

REVERSAL_LEVELS = [
    ("drop5", 0.05, "⚠️ MOEDA A REGREDIR — recuou 5% do topo", "Recuo de 5% a partir do topo"),
    ("drop10", 0.10, "🔴 REVERSÃO CONFIRMADA — recuou 10% do topo, atenção", "Reversão confirmada com recuo de 10%")
]

last_summary = datetime.now()
binance_blocked_until = 0.0
history_records: List[Dict] = []
active_pumps: Dict[str, int] = {}
progressive_state: Dict[str, Dict] = {}
signal_state: Dict[str, Dict] = {}
metrics_cache: Dict[str, Dict] = {}
metrics_cache_ts: Dict[str, float] = {}
latest_signals: Dict[str, Dict] = {}
latest_signals_ts: float = 0.0
last_data_fingerprint: Optional[str] = None
last_data_change_ts: float = time.time()


class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/health", "/ping"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if path in ("/signals", "/api/signals"):
            query = parse_qs(parsed.query or "")
            key = (query.get("key", [""])[0] or "").strip()
            if SIGNALS_API_KEY and key != SIGNALS_API_KEY:
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", SIGNALS_CORS_ORIGIN)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "forbidden"}).encode("utf-8"))
                return

            symbols = (query.get("symbols", [""])[0] or "").strip()
            wanted = {s.strip().upper() for s in symbols.split(",") if s.strip()} if symbols else None
            payload = {}
            for sym, data in latest_signals.items():
                if wanted and sym not in wanted:
                    continue
                payload[sym] = data

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", SIGNALS_CORS_ORIGIN)
            self.end_headers()
            self.wfile.write(json.dumps({
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "count": len(payload),
                "signals": payload
            }, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_keepalive_server():
    try:
        httpd = HTTPServer(("", KEEPALIVE_PORT), KeepAliveHandler)
        t = threading.Thread(target=httpd.serve_forever, name="keepalive", daemon=True)
        t.start()
        log.info(f"Keepalive HTTP ativo na porta {KEEPALIVE_PORT}")
    except Exception as e:
        log.error(f"Falha ao iniciar keepalive HTTP: {e}")


def reset_persistent_history():
    global history_records, active_pumps
    history_records = []
    active_pumps = {}
    if os.path.exists(HISTORY_FILE):
        try:
            os.remove(HISTORY_FILE)
            log.info("Historico limpo (reset de emergencia).")
        except Exception as e:
            log.warning(f"Falha ao limpar historico: {e}")


def reset_runtime_state():
    global progressive_state, signal_state, metrics_cache, metrics_cache_ts
    global latest_signals, latest_signals_ts, last_summary
    progressive_state.clear()
    signal_state.clear()
    metrics_cache.clear()
    metrics_cache_ts.clear()
    latest_signals.clear()
    latest_signals_ts = 0.0
    last_summary = datetime.now()


def rebuild_session():
    global session
    try:
        session.close()
    except Exception:
        pass
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    })


def reset_connections(cmc_cache: Optional["CmcCache"] = None):
    global last_data_fingerprint, last_data_change_ts
    rebuild_session()
    metrics_cache.clear()
    metrics_cache_ts.clear()
    last_data_fingerprint = None
    last_data_change_ts = time.time()
    if cmc_cache is not None:
        cmc_cache.reset()


def tickers_fingerprint(tickers: List[Ticker]) -> str:
    items = [
        (t.exchange, t.symbol, round(t.last_price, 8), round(t.change_pct, 4), round(t.quote_volume, 2))
        for t in tickers
    ]
    items.sort()
    payload = json.dumps(items, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def data_stale(tickers: List[Ticker]) -> bool:
    global last_data_fingerprint, last_data_change_ts
    if DATA_STALE_RESET_SECS <= 0:
        return False
    now = time.time()
    fingerprint = tickers_fingerprint(tickers)
    if fingerprint != last_data_fingerprint:
        last_data_fingerprint = fingerprint
        last_data_change_ts = now
        return False
    if (now - last_data_change_ts) >= DATA_STALE_RESET_SECS:
        last_data_change_ts = now
        return True
    return False


def has_auth_priority(coin: AggregatedCoin) -> bool:
    return (
        ("binance" in coin.sources and BINANCE_API_KEY and BINANCE_API_SECRET)
        or ("bybit" in coin.sources and BYBIT_API_KEY and BYBIT_API_SECRET)
    )


def is_valid_symbol(symbol: str) -> bool:
    if not symbol.endswith("USDT"):
        return False
    for bad in ("UP", "DOWN", "BULL", "BEAR"):
        if bad in symbol:
            return False
    return True


def get_json_with_retries(
    url: str,
    *,
    params: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    timeout: int = 10
):
    last_exc = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            r = session.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_exc = e
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECS)
                continue
            raise
    raise last_exc


def binance_signed_get(path: str, params: Optional[Dict] = None) -> Optional[Dict]:
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        return None
    params = params or {}
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000
    query = urlencode(params, doseq=True)
    signature = hmac.new(
        BINANCE_API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    url = f"{BINANCE_FAPI_BASE}{path}?{query}&signature={signature}"
    headers = {**DEFAULT_HEADERS, "X-MBX-APIKEY": BINANCE_API_KEY}
    r = session.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECS)
    r.raise_for_status()
    return r.json()


def bybit_signed_get(path: str, params: Optional[Dict] = None) -> Optional[Dict]:
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        return None
    params = params or {}
    ts = str(int(time.time() * 1000))
    recv = "5000"
    query = urlencode(params, doseq=True)
    payload = f"{ts}{BYBIT_API_KEY}{recv}{query}"
    sign = hmac.new(
        BYBIT_API_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    headers = {
        **DEFAULT_HEADERS,
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-SIGN": sign,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": recv,
        "X-BAPI-SIGN-TYPE": "2"
    }
    url = f"{BYBIT_API_BASE}{path}"
    r = session.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT_SECS)
    r.raise_for_status()
    return r.json()


def fetch_binance_metrics(symbol: str) -> Dict[str, Optional[float]]:
    metrics: Dict[str, Optional[float]] = {
        "orderbook_sell_ratio": None,
        "trade_sell_ratio": None,
        "funding_rate": None,
        "open_interest": None,
        "recent_quote_vol": None
    }
    try:
        depth = binance_signed_get("/fapi/v1/depth", {"symbol": symbol, "limit": 50})
        bids = depth.get("bids", []) if depth else []
        asks = depth.get("asks", []) if depth else []
        bid_qty = sum(float(b[1]) for b in bids[:25]) if bids else 0.0
        ask_qty = sum(float(a[1]) for a in asks[:25]) if asks else 0.0
        if bid_qty > 0:
            metrics["orderbook_sell_ratio"] = ask_qty / bid_qty
    except Exception as e:
        log.warning(f"Binance orderbook falhou ({symbol}): {e}")

    try:
        trades = binance_signed_get("/fapi/v1/trades", {"symbol": symbol, "limit": 80})
        if trades:
            sell_count = sum(1 for t in trades if t.get("buyerMaker"))
            metrics["trade_sell_ratio"] = sell_count / max(len(trades), 1)
            now_ms = int(time.time() * 1000)
            cutoff = now_ms - (SHORT_VOL_WINDOW_SECS * 1000)
            recent = [t for t in trades if isinstance(t.get("time"), int) and t.get("time") >= cutoff]
            if recent:
                metrics["recent_quote_vol"] = sum(float(t.get("price", 0)) * float(t.get("qty", 0)) for t in recent)
    except Exception as e:
        log.warning(f"Binance trades falhou ({symbol}): {e}")

    try:
        funding = binance_signed_get("/fapi/v1/premiumIndex", {"symbol": symbol})
        if funding:
            metrics["funding_rate"] = float(funding.get("lastFundingRate", 0))
    except Exception as e:
        log.warning(f"Binance funding falhou ({symbol}): {e}")

    try:
        oi = binance_signed_get("/fapi/v1/openInterest", {"symbol": symbol})
        if oi and oi.get("openInterest"):
            metrics["open_interest"] = float(oi.get("openInterest"))
    except Exception as e:
        log.warning(f"Binance open interest falhou ({symbol}): {e}")

    return metrics


def fetch_bybit_metrics(symbol: str) -> Dict[str, Optional[float]]:
    metrics: Dict[str, Optional[float]] = {
        "orderbook_sell_ratio": None,
        "trade_sell_ratio": None,
        "funding_rate": None,
        "open_interest": None,
        "recent_quote_vol": None
    }
    try:
        depth = bybit_signed_get("/v5/market/orderbook", {"category": "linear", "symbol": symbol, "limit": 50})
        result = (depth or {}).get("result", {})
        bids = result.get("b", [])
        asks = result.get("a", [])
        bid_qty = sum(float(b[1]) for b in bids[:25]) if bids else 0.0
        ask_qty = sum(float(a[1]) for a in asks[:25]) if asks else 0.0
        if bid_qty > 0:
            metrics["orderbook_sell_ratio"] = ask_qty / bid_qty
    except Exception as e:
        log.warning(f"Bybit orderbook falhou ({symbol}): {e}")

    try:
        trades = bybit_signed_get("/v5/market/recent-trade", {"category": "linear", "symbol": symbol, "limit": 80})
        items = (trades or {}).get("result", {}).get("list", [])
        if items:
            sell_count = sum(1 for t in items if (t.get("side") or "").lower() == "sell")
            metrics["trade_sell_ratio"] = sell_count / max(len(items), 1)
            now_ms = int(time.time() * 1000)
            cutoff = now_ms - (SHORT_VOL_WINDOW_SECS * 1000)
            recent = []
            for t in items:
                ts_raw = t.get("time") or t.get("execTime") or t.get("timestamp")
                try:
                    ts = int(ts_raw)
                except Exception:
                    continue
                if ts >= cutoff:
                    recent.append(t)
            if recent:
                metrics["recent_quote_vol"] = sum(float(t.get("price", 0)) * float(t.get("size", 0)) for t in recent)
    except Exception as e:
        log.warning(f"Bybit trades falhou ({symbol}): {e}")

    try:
        funding = bybit_signed_get("/v5/market/funding/history", {"category": "linear", "symbol": symbol, "limit": 1})
        items = (funding or {}).get("result", {}).get("list", [])
        if items:
            metrics["funding_rate"] = float(items[0].get("fundingRate", 0))
    except Exception as e:
        log.warning(f"Bybit funding falhou ({symbol}): {e}")

    try:
        oi = bybit_signed_get("/v5/market/open-interest", {"category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": 1})
        items = (oi or {}).get("result", {}).get("list", [])
        if items:
            metrics["open_interest"] = float(items[0].get("openInterest", 0))
    except Exception as e:
        log.warning(f"Bybit open interest falhou ({symbol}): {e}")

    return metrics


def merge_metric_values(values: List[Optional[float]], mode: str = "max") -> Optional[float]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if mode == "min":
        return min(vals)
    if mode == "avg":
        return sum(vals) / len(vals)
    return max(vals)


def get_market_metrics(coin: AggregatedCoin) -> Dict[str, Optional[float]]:
    symbol = coin.symbol
    now = time.time()
    if symbol in metrics_cache and (now - metrics_cache_ts.get(symbol, 0) < METRICS_TTL_SECS):
        return metrics_cache[symbol]

    use_binance = "binance" in coin.sources and BINANCE_API_KEY and BINANCE_API_SECRET
    use_bybit = "bybit" in coin.sources and BYBIT_API_KEY and BYBIT_API_SECRET

    binance_metrics = fetch_binance_metrics(symbol) if use_binance else {}
    bybit_metrics = fetch_bybit_metrics(symbol) if use_bybit else {}

    merged = {
        "orderbook_sell_ratio": merge_metric_values(
            [binance_metrics.get("orderbook_sell_ratio"), bybit_metrics.get("orderbook_sell_ratio")], "max"
        ),
        "trade_sell_ratio": merge_metric_values(
            [binance_metrics.get("trade_sell_ratio"), bybit_metrics.get("trade_sell_ratio")], "max"
        ),
        "funding_rate": merge_metric_values(
            [binance_metrics.get("funding_rate"), bybit_metrics.get("funding_rate")], "max"
        ),
        "open_interest": merge_metric_values(
            [binance_metrics.get("open_interest"), bybit_metrics.get("open_interest")], "avg"
        ),
        "recent_quote_vol": merge_metric_values(
            [binance_metrics.get("recent_quote_vol"), bybit_metrics.get("recent_quote_vol")], "avg"
        )
    }

    metrics_cache[symbol] = merged
    metrics_cache_ts[symbol] = now
    return merged


def fetch_binance() -> List[Ticker]:
    global binance_blocked_until
    now = time.time()
    if now < binance_blocked_until:
        remaining = int(binance_blocked_until - now)
        log.warning(f"Binance bloqueada (451). Usando Bybit/CMC por mais {remaining}s.")
        return []
    try:
        headers = dict(DEFAULT_HEADERS)
        if BINANCE_API_KEY:
            headers["X-MBX-APIKEY"] = BINANCE_API_KEY
        data = get_json_with_retries(
            BINANCE_URL,
            headers=headers,
            timeout=HTTP_TIMEOUT_SECS
        )
        out = []
        for d in data:
            symbol = d.get("symbol", "")
            if not is_valid_symbol(symbol):
                continue
            vol = float(d.get("quoteVolume", 0))
            if vol < MIN_FUTURES_VOLUME_USDT:
                continue
            out.append(Ticker(
                symbol=symbol,
                exchange="binance",
                last_price=float(d.get("lastPrice", 0)),
                open_price=float(d.get("openPrice", 0)),
                change_pct=float(d.get("priceChangePercent", 0)),
                quote_volume=vol
            ))
        return out
    except requests.HTTPError as e:
        status = e.response.status_code if e.response else None
        if status == 451:
            binance_blocked_until = time.time() + BINANCE_451_COOLDOWN_SECS
            log.warning(
                "Binance retornou 451 (geoblock). Fallback automático para Bybit/CMC."
            )
        else:
            log.error(f"Erro Binance API ({status}): {e}")
        return []
    except Exception as e:
        log.error(f"Erro Binance API: {e}")
        return []


def fetch_bybit() -> List[Ticker]:
    try:
        headers = dict(DEFAULT_HEADERS)
        if BYBIT_API_KEY:
            headers["X-BAPI-API-KEY"] = BYBIT_API_KEY
        data = get_json_with_retries(
            BYBIT_URL,
            headers=headers,
            timeout=HTTP_TIMEOUT_SECS
        )
        items = data.get("result", {}).get("list", [])
        out = []
        for d in items:
            symbol = d.get("symbol", "")
            if not is_valid_symbol(symbol):
                continue
            vol = float(d.get("turnover24h", 0))
            if vol < MIN_FUTURES_VOLUME_USDT:
                continue
            last = float(d.get("lastPrice", 0))
            change_pct = float(d.get("price24hPcnt", 0)) * 100
            open_price = float(d.get("prevPrice24h", 0))
            if open_price == 0 and last and change_pct:
                open_price = last / (1 + change_pct / 100)
            out.append(Ticker(
                symbol=symbol,
                exchange="bybit",
                last_price=last,
                open_price=open_price or last,
                change_pct=change_pct,
                quote_volume=vol
            ))
        return out
    except requests.HTTPError as e:
        status = e.response.status_code if e.response else None
        log.error(f"Erro Bybit API ({status}): {e}")
        return []
    except Exception as e:
        log.error(f"Erro Bybit API: {e}")
        return []


class CmcCache:
    def __init__(self, api_key: str, ttl_secs: int = 600):
        self.api_key = api_key
        self.ttl_secs = ttl_secs
        self.cache: Dict[str, Dict] = {}
        self.cache_ts: Dict[str, float] = {}

    def reset(self):
        self.cache.clear()
        self.cache_ts.clear()

    def get(self, symbols: List[str]) -> Dict[str, Dict]:
        if not self.api_key:
            return {}

        now = time.time()
        fresh = {s: self.cache[s] for s in symbols if s in self.cache and (now - self.cache_ts[s] < self.ttl_secs)}
        missing = [s for s in symbols if s not in fresh]

        if missing:
            for chunk in chunked(missing, 100):
                params = {"symbol": ",".join(chunk), "convert": "USD"}
                headers = {
                    "X-CMC_PRO_API_KEY": self.api_key,
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT
                }
                try:
                    data = get_json_with_retries(
                        CMC_URL,
                        params=params,
                        headers=headers,
                        timeout=HTTP_TIMEOUT_CMC_SECS
                    )
                    data = data.get("data", {})
                    for sym, info in data.items():
                        quote = info.get("quote", {}).get("USD", {})
                        market_cap = quote.get("market_cap")
                        rank = info.get("cmc_rank")
                        price = quote.get("price")
                        pct_24h = quote.get("percent_change_24h")
                        vol_24h = quote.get("volume_24h")
                        self.cache[sym] = {
                            "market_cap": market_cap,
                            "cmc_rank": rank,
                            "price": price,
                            "percent_change_24h": pct_24h,
                            "volume_24h": vol_24h
                        }
                        self.cache_ts[sym] = now
                        fresh[sym] = self.cache[sym]
                except requests.HTTPError as e:
                    status = e.response.status_code if e.response else None
                    log.error(f"Erro CMC API ({status}): {e}")
                except Exception as e:
                    log.error(f"Erro CMC API: {e}")
        return fresh


def chunked(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]

def build_cmc_tickers(cmc_data: Dict[str, Dict]) -> List[Ticker]:
    out: List[Ticker] = []
    for sym, info in cmc_data.items():
        symbol = f"{sym}USDT"
        if not is_valid_symbol(symbol):
            continue
        price = info.get("price")
        pct = info.get("percent_change_24h")
        vol = float(info.get("volume_24h") or 0)
        if price is None or pct is None:
            continue
        if vol < MIN_VOLUME_USDT:
            continue
        price = float(price)
        pct = float(pct)
        open_price = price / (1 + pct / 100) if price and pct else price
        out.append(Ticker(
            symbol=symbol,
            exchange="cmc",
            last_price=price,
            open_price=open_price,
            change_pct=pct,
            quote_volume=vol
        ))
    return out


def aggregate(tickers: List[Ticker], cmc: Dict[str, Dict]) -> List[AggregatedCoin]:
    merged: Dict[str, Dict] = {}
    for t in tickers:
        if t.symbol not in merged:
            merged[t.symbol] = {"symbol": t.symbol, "base": t.symbol.replace("USDT", ""), "sources": {}}
        merged[t.symbol]["sources"][t.exchange] = t

    coins: List[AggregatedCoin] = []
    for entry in merged.values():
        sources = entry["sources"]
        max_change = max(t.change_pct for t in sources.values())
        total_volume = sum(t.quote_volume for t in sources.values())
        pump_sources = [ex for ex, t in sources.items() if t.change_pct >= PUMP_MIN]
        priority = len(pump_sources) >= 2
        multi_source = len(sources) >= 2

        cmc_data = cmc.get(entry["base"], {})
        market_cap = cmc_data.get("market_cap")
        cmc_rank = cmc_data.get("cmc_rank")

        if MIN_MARKET_CAP_USD > 0 and (not market_cap or market_cap < MIN_MARKET_CAP_USD):
            continue
        if MAX_CMC_RANK > 0 and (not cmc_rank or cmc_rank > MAX_CMC_RANK):
            continue

        coins.append(AggregatedCoin(
            symbol=entry["symbol"],
            base=entry["base"],
            sources=sources,
            max_change=max_change,
            total_volume=total_volume,
            pump_sources=pump_sources,
            priority=priority,
            market_cap=market_cap,
            cmc_rank=cmc_rank,
            multi_source=multi_source
        ))
    return coins

# =========================
# Telegram
# =========================
TG_URL = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)


def send(text: str, parse_mode: str = "HTML", disable_preview: bool = False, reply_markup: Optional[Dict] = None):
    if not BOT_TOKEN or not CHAT_ID:
        log.error("Telegram não configurado: verifique TELEGRAM_TOKEN/BOT_TOKEN e CHAT_ID.")
        return
    try:
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        r = session.post(TG_URL, json=payload, timeout=8)
        if not r.ok:
            log.warning(f"Telegram erro: {r.text}")
            if parse_mode == "HTML":
                fallback = strip_html(text)
                payload["text"] = fallback
                payload.pop("parse_mode", None)
                r2 = session.post(TG_URL, json=payload, timeout=8)
                if not r2.ok:
                    log.warning(f"Telegram fallback erro: {r2.text}")
    except Exception as e:
        log.error(f"Telegram send falhou: {e}")


def send_webhook(url: str, text: str):
    if not url:
        return
    try:
        if "discord" in url:
            payload = {"content": text}
        else:
            payload = {"text": text}
        r = session.post(url, json=payload, timeout=8)
        if not r.ok:
            log.warning(f"Webhook erro ({r.status_code}): {r.text}")
    except Exception as e:
        log.error(f"Webhook falhou: {e}")


# =========================
# Formatação
# =========================
def fmt_price(n: float) -> str:
    if n < 0.000001:
        return f"{n:.2e}"
    if n < 0.001:
        return f"{n:.8f}"
    if n < 1:
        return f"{n:.6f}"
    if n < 100:
        return f"{n:.4f}"
    return f"{n:.2f}"


def fmt_vol(n: float) -> str:
    if n >= 1e12:
        return f"{n/1e12:.1f}T"
    if n >= 1e9:
        return f"{n/1e9:.1f}B"
    if n >= 1e6:
        return f"{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{n/1e3:.0f}K"
    return f"{n:.0f}"


def escape_html(text: str) -> str:
    return html_lib.escape(text or "", quote=True)


def strip_html(text: str) -> str:
    clean = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return re.sub(r"<[^>]+>", "", clean)


def chart_link(symbol: str, sources: Dict[str, Ticker]) -> str:
    if "binance" in sources:
        tv_exchange = "BINANCE"
    elif "bybit" in sources:
        tv_exchange = "BYBIT"
    else:
        tv_exchange = "BINANCE"
    return f"https://www.tradingview.com/chart/?symbol={tv_exchange}:{symbol}"


def exchange_links(coin: AggregatedCoin) -> List[Dict[str, str]]:
    base = coin.base.upper()
    links = []
    if "binance" in coin.sources:
        links.append({"label": "Binance", "url": f"https://www.binance.com/trade/{base}_USDT"})
    if "bybit" in coin.sources:
        links.append({"label": "Bybit", "url": f"https://www.bybit.com/trade/usdt/{base}USDT"})
    if "cmc" in coin.sources:
        slug = coin.base.lower()
        links.append({"label": "CMC", "url": f"https://coinmarketcap.com/currencies/{slug}"})
    return links


def build_alert_keyboard(coin: AggregatedCoin) -> Dict:
    chart = chart_link(coin.symbol, coin.sources)
    links = exchange_links(coin)
    rows = [[{"text": "📊 Gráfico", "url": chart}]]
    row = []
    for item in links:
        row.append({"text": f"💱 {item['label']}", "url": item["url"]})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


def alert_header(level: str, priority: bool) -> str:
    base = {
        "mega": "🌌 MEGA PUMP",
        "explosion": "💥 EXPLOSÃO",
        "pump": "🔥 PUMP DETECTADO",
        "pre": "⚡ PRÉ-PUMP"
    }[level]
    if priority:
        return f"{base} · PRIORIDADE MÁXIMA"
    return base


def format_alert(coin: AggregatedCoin, level: str) -> str:
    exchanges = " + ".join(EXCHANGE_LABELS.get(ex, ex) for ex in coin.sources.keys())
    pct_by_ex = " | ".join(
        f"{EXCHANGE_LABELS.get(ex, ex)} +{t.change_pct:.2f}%"
        for ex, t in coin.sources.items()
    )
    vol_by_ex = " | ".join(
        f"{EXCHANGE_LABELS.get(ex, ex)} ${fmt_vol(t.quote_volume)}"
        for ex, t in coin.sources.items()
    )
    chart = chart_link(coin.symbol, coin.sources)
    links = exchange_links(coin)
    links_line = " · ".join(
        f"<a href=\"{item['url']}\">{item['label']}</a>"
        for item in links
    ) or "—"

    level_title = {
        "mega": "🌌 MEGA PUMP",
        "explosion": "💥 EXPLOSÃO"
    }.get(level, "🚀 ALERTA")
    if coin.priority:
        level_title += " · PRIORIDADE MÁXIMA"

    lines = [
        f"<b>{level_title}: {escape_html(coin.base)}/USDT</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🛰️ <b>Fonte(s) do sinal</b>: {exchanges}",
        f"✅ <b>Confirmado</b>: {'SIM' if coin.multi_source else 'NÃO'} ({len(coin.sources)} fonte(s))",
        f"📈 <b>Variação 24h</b>: {pct_by_ex}",
        f"💧 <b>Volume 24h</b>: {vol_by_ex}",
    ]

    if coin.market_cap:
        lines.append(f"💎 <b>Market Cap</b>: ${fmt_vol(coin.market_cap)}")
    if coin.cmc_rank:
        lines.append(f"🏅 <b>Rank</b>: #{coin.cmc_rank}")

    lines.extend([
        f"🔗 <b>Links</b>: {links_line}",
        f"📊 <a href=\"{chart}\">Abrir gráfico</a>",
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    ])

    return "\n".join(lines)


def format_progressive_alert(coin: AggregatedCoin, title: str, note: str) -> str:
    exchanges = " + ".join(EXCHANGE_LABELS.get(ex, ex) for ex in coin.sources.keys())
    pct_by_ex = " | ".join(
        f"{EXCHANGE_LABELS.get(ex, ex)} +{t.change_pct:.2f}%"
        for ex, t in coin.sources.items()
    )
    vol_by_ex = " | ".join(
        f"{EXCHANGE_LABELS.get(ex, ex)} ${fmt_vol(t.quote_volume)}"
        for ex, t in coin.sources.items()
    )
    chart = chart_link(coin.symbol, coin.sources)
    links = exchange_links(coin)
    links_line = " · ".join(
        f"<a href=\"{item['url']}\">{item['label']}</a>"
        for item in links
    ) or "—"

    lines = [
        f"<b>{title}: {escape_html(coin.base)}/USDT</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🛰️ <b>Fonte(s)</b>: {exchanges}",
        f"📈 <b>Variação 24h</b>: {pct_by_ex}",
        f"💧 <b>Volume 24h</b>: {vol_by_ex}",
        f"⚠️ <b>Nota</b>: {note}",
    ]

    if coin.market_cap:
        lines.append(f"💎 <b>Market Cap</b>: ${fmt_vol(coin.market_cap)}")
    if coin.cmc_rank:
        lines.append(f"🏅 <b>Rank</b>: #{coin.cmc_rank}")

    lines.extend([
        f"🔗 <b>Links</b>: {links_line}",
        f"📊 <a href=\"{chart}\">Abrir gráfico</a>",
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    ])
    return "\n".join(lines)


def format_reversal_alert(coin: AggregatedCoin, peak_pct: float, drop_ratio: float, title: str, note: str) -> str:
    exchanges = " + ".join(EXCHANGE_LABELS.get(ex, ex) for ex in coin.sources.keys())
    pct_by_ex = " | ".join(
        f"{EXCHANGE_LABELS.get(ex, ex)} +{t.change_pct:.2f}%"
        for ex, t in coin.sources.items()
    )
    chart = chart_link(coin.symbol, coin.sources)
    links = exchange_links(coin)
    links_line = " · ".join(
        f"<a href=\"{item['url']}\">{item['label']}</a>"
        for item in links
    ) or "—"
    drop_pct = drop_ratio * 100

    lines = [
        f"<b>{title}: {escape_html(coin.base)}/USDT</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🛰️ <b>Fonte(s)</b>: {exchanges}",
        f"📉 <b>Queda do pico</b>: -{drop_pct:.1f}% (pico +{peak_pct:.1f}%)",
        f"📈 <b>Variação 24h</b>: {pct_by_ex}",
        f"⚠️ <b>Nota</b>: {note}",
        f"🔗 <b>Links</b>: {links_line}",
        f"📊 <a href=\"{chart}\">Abrir gráfico</a>",
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    ]
    return "\n".join(lines)


def short_success_stats() -> Optional[Dict[str, int]]:
    shorts = [r for r in history_records if r.get("short_signal")]
    if not shorts:
        return None
    total = len(shorts)
    hit10 = sum(1 for r in shorts if r.get("short_hit_10"))
    hit20 = sum(1 for r in shorts if r.get("short_hit_20"))
    return {"total": total, "hit10": hit10, "hit20": hit20}


def format_short_signal(coin: AggregatedCoin, analysis: Dict) -> str:
    base = escape_html(coin.base)
    best = max(coin.sources.values(), key=lambda t: t.change_pct)
    price = fmt_price(best.last_price)
    variation = f"+{coin.max_change:.1f}%"
    volume_line = "enfraquecendo ⚠️" if analysis.get("volume_weak") else "estável"

    funding_rate = analysis.get("funding_rate")
    if funding_rate is None:
        funding_line = "n/d"
    else:
        funding_pct = funding_rate * 100
        funding_line = f"{funding_pct:+.3f}%"
        if analysis.get("funding_high"):
            funding_line += " (elevado)"

    order_book_line = "pressão vendedora" if analysis.get("order_pressure") else "equilibrado"
    hits = analysis.get("hits", 0)
    total = analysis.get("total", 6)
    confidence = analysis.get("confidence", "")
    confidence_line = f"🎯 <b>Confiança</b>: {confidence}" if confidence else None

    stop_price = analysis.get("stop_price")
    tp1_price = analysis.get("tp1_price")
    tp2_price = analysis.get("tp2_price")
    stop_line = None
    if stop_price:
        stop_line = f"🛑 <b>Stop sugerido</b>: ${fmt_price(stop_price)} (+{SHORT_STOP_BUFFER_PCT:.1f}%)"
    target_line = None
    if tp1_price and tp2_price:
        target_line = (
            f"🎯 <b>Alvos</b>: ${fmt_price(tp1_price)} (-{SHORT_TP1_PCT:.0f}%) · "
            f"${fmt_price(tp2_price)} (-{SHORT_TP2_PCT:.0f}%)"
        )

    binance_link = f"https://www.binance.com/en/futures/{coin.base.upper()}USDT"
    bybit_link = f"https://www.bybit.com/trade/usdt/{coin.base.upper()}USDT"

    lines = [
        f"🎯 <b>SINAL DE SHORT — {base}/USDT</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📈 <b>Variação</b>: {variation}",
        f"💲 <b>Preço actual</b>: ${price}",
        f"📊 <b>Volume</b>: {volume_line}",
        f"📉 <b>Funding rate</b>: {funding_line}",
        f"📖 <b>Order book</b>: {order_book_line}",
        f"🔍 <b>Análise</b>: {hits} de {total} indicadores apontam reversão",
        confidence_line
    ]
    if stop_line:
        lines.append(stop_line)
    if target_line:
        lines.append(target_line)

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━",
        "⚠️ Possível momento de entrada em SHORT",
        f"🔗 Binance Futures: <a href=\"{binance_link}\">link</a>",
        f"🔗 Bybit Futures: <a href=\"{bybit_link}\">link</a>",
        "⚠️ Não é conselho financeiro. Gerencie o risco."
    ])
    return "\n".join([line for line in lines if line])


def analyze_short_signal(coin: AggregatedCoin) -> Optional[Dict]:
    if coin.max_change < SHORT_MIN_PCT:
        return None

    sym = coin.symbol
    now = time.time()
    state = signal_state.get(sym, {
        "peak_pct": coin.max_change,
        "last_volume": None,
        "last_recent_vol": None,
        "last_pct": None,
        "last_ts": None,
        "oi_at_peak": None,
        "short_sent": False
    })

    if coin.max_change > state.get("peak_pct", 0):
        state["peak_pct"] = coin.max_change

    speed_fast = False
    if state.get("last_pct") is not None and state.get("last_ts"):
        dt_min = (now - state["last_ts"]) / 60
        if dt_min > 0:
            speed = (coin.max_change - state["last_pct"]) / dt_min
            speed_fast = speed >= SPEED_RISE_MIN_PER_MIN

    metrics = get_market_metrics(coin)
    recent_quote_vol = metrics.get("recent_quote_vol")
    peak_pct = state.get("peak_pct", coin.max_change)
    past_peak = coin.max_change < peak_pct

    volume_weak = False
    if recent_quote_vol is not None:
        if state.get("last_recent_vol") is not None and past_peak:
            volume_weak = recent_quote_vol < state["last_recent_vol"] * VOLUME_WEAKEN_RATIO
        state["last_recent_vol"] = recent_quote_vol
    else:
        if state.get("last_volume") is not None and past_peak:
            volume_weak = coin.total_volume < state["last_volume"] * VOLUME_WEAKEN_RATIO
        state["last_volume"] = coin.total_volume

    orderbook_ratio = metrics.get("orderbook_sell_ratio")
    trade_sell_ratio = metrics.get("trade_sell_ratio")
    order_pressure = False
    if orderbook_ratio is not None and orderbook_ratio >= ORDERBOOK_SELL_RATIO:
        order_pressure = True
    if trade_sell_ratio is not None and trade_sell_ratio >= 0.6:
        order_pressure = True

    funding_rate = metrics.get("funding_rate")
    funding_high = funding_rate is not None and funding_rate >= FUNDING_RATE_HIGH
    price_falling = state.get("last_pct") is not None and coin.max_change < state["last_pct"]
    funding_divergence = funding_high and (past_peak or price_falling)

    oi_drop = False
    open_interest = metrics.get("open_interest")
    if open_interest is not None:
        if coin.max_change >= peak_pct:
            state["oi_at_peak"] = open_interest
        if past_peak and state.get("oi_at_peak") is not None:
            if open_interest < state["oi_at_peak"] * (1 - OPEN_INTEREST_DROP_RATIO):
                oi_drop = True

    state["last_pct"] = coin.max_change
    state["last_ts"] = now
    signal_state[sym] = state

    distance_risk = peak_pct >= DISTANCE_RISK_PCT

    oi_usd = None
    if open_interest is not None:
        best = max(coin.sources.values(), key=lambda t: t.change_pct)
        oi_usd = open_interest * float(best.last_price or 0)

    illiquid = MIN_OPEN_INTEREST_USD > 0 and oi_usd is not None and oi_usd < MIN_OPEN_INTEREST_USD

    fake_pump = False
    if FAKE_PUMP_VOL_USD > 0 and recent_quote_vol is not None:
        if recent_quote_vol < FAKE_PUMP_VOL_USD and state.get("oi_at_peak") is not None and open_interest is not None:
            oi_ref = state.get("oi_at_peak") or 0
            if oi_ref > 0:
                delta_ratio = abs(open_interest - oi_ref) / oi_ref
                fake_pump = delta_ratio <= FAKE_PUMP_OI_STABLE_RATIO

    if AUTH_PRIORITY_FAKE_PUMP and has_auth_priority(coin):
        fake_pump = False

    indicators = {
        "volume_weak": volume_weak,
        "speed_fast": speed_fast,
        "order_pressure": order_pressure,
        "funding_high": funding_high,
        "funding_divergence": funding_divergence,
        "oi_drop": oi_drop,
        "distance_risk": distance_risk
    }
    hits = sum(1 for v in indicators.values() if v)

    status = "up"
    if hits >= SHORT_MIN_INDICATORS and not fake_pump and not illiquid:
        status = "short"
    elif hits >= 2 or distance_risk or fake_pump or illiquid:
        status = "attention"

    confidence = ""
    total = len(indicators)
    if hits >= max(5, total - 1):
        confidence = "ALTA"
    elif hits >= SHORT_MIN_INDICATORS:
        confidence = "MÉDIA"
    elif hits >= 2:
        confidence = "BAIXA"

    return {
        **indicators,
        "funding_rate": funding_rate,
        "trade_sell_ratio": trade_sell_ratio,
        "orderbook_ratio": orderbook_ratio,
        "hits": hits,
        "total": len(indicators),
        "distance_risk": distance_risk,
        "funding_divergence": funding_divergence,
        "confidence": confidence,
        "illiquid": illiquid,
        "fake_pump": fake_pump,
        "oi_usd": oi_usd,
        "recent_quote_vol": recent_quote_vol,
        "status": status
    }


def msg_summary(coins: List[AggregatedCoin]) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    above_300 = [c for c in coins if c.max_change >= 300]
    above_500 = [c for c in coins if c.max_change >= 500]
    above_1000 = [c for c in coins if c.max_change >= 1000]
    pre = [c for c in coins if PRE_PUMP_MIN <= c.max_change < 300]
    dual = [c for c in coins if c.priority]

    top5 = sorted(above_300, key=lambda c: -c.max_change)[:5]
    top_lines = "\n".join(
        f"• <b>{escape_html(c.base)}</b> → +{c.max_change:.1f}% ({', '.join(EXCHANGE_LABELS.get(ex, ex) for ex in c.sources)})"
        for c in top5
    ) or "(nenhum)"

    short_stats = short_success_stats()
    short_lines = ""
    if short_stats:
        short_lines = (
            f"🎯 Shorts ≥10%: <b>{short_stats['hit10']}/{short_stats['total']}</b>\n"
            f"✅ Shorts ≥20%: <b>{short_stats['hit20']}/{short_stats['total']}</b>\n"
        )

    return (
        f"📊 <b>RESUMO — Smart Pump Finder</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 Pumps +300%: <b>{len(above_300)}</b>\n"
        f"💥 Explosão +500%: <b>{len(above_500)}</b>\n"
        f"🌌 Mega +1000%: <b>{len(above_1000)}</b>\n"
        f"⚡ Pré-pump: <b>{len(pre)}</b>\n"
        f"🔁 Confluências: <b>{len(dual)}</b>\n"
        f"{short_lines}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>TOP 5</b>\n{top_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now} · Monitorando {len(coins)} pares"
    )


# =========================
# Histórico Persistente
# =========================
def load_history():
    global history_records, active_pumps
    if not os.path.exists(HISTORY_FILE):
        return
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            history_records = data
            active_pumps = {}
            for idx, rec in enumerate(history_records):
                if rec.get("end_time") in (None, "", "null"):
                    sym = rec.get("symbol")
                    if sym:
                        active_pumps[sym] = idx
    except Exception as e:
        log.error(f"Falha ao carregar histórico: {e}")


def save_history():
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Falha ao salvar histórico: {e}")


def update_pump_history(coins: List[AggregatedCoin]):
    global history_records, active_pumps
    now_iso = datetime.now().isoformat(timespec="seconds")
    active_now = {c.symbol: c for c in coins if c.max_change >= PUMP_MIN}
    changed = False

    for sym, coin in active_now.items():
        sources = sorted({EXCHANGE_LABELS.get(ex, ex) for ex in coin.sources.keys()})
        if sym not in active_pumps:
            record = {
                "symbol": sym,
                "detected_pct": round(coin.max_change, 2),
                "peak_pct": round(coin.max_change, 2),
                "start_time": now_iso,
                "end_time": None,
                "sources": sources,
                "short_signal": False,
                "short_time": None,
                "short_indicators": None,
                "short_entry_pct": None,
                "short_entry_price": None,
                "short_confidence": None,
                "short_max_drop_pct": 0.0,
                "short_hit_5": False,
                "short_hit_10": False,
                "short_hit_20": False,
                "max_drawdown_pct": 0.0
            }
            history_records.append(record)
            active_pumps[sym] = len(history_records) - 1
            changed = True
        else:
            rec = history_records[active_pumps[sym]]
            if coin.max_change > float(rec.get("peak_pct") or 0):
                rec["peak_pct"] = round(coin.max_change, 2)
                changed = True
            if sources and sources != rec.get("sources"):
                rec["sources"] = sources
                changed = True
            peak = float(rec.get("peak_pct") or 0)
            if peak > 0:
                drawdown = max(0.0, (peak - coin.max_change) / peak * 100)
                if drawdown > float(rec.get("max_drawdown_pct") or 0):
                    rec["max_drawdown_pct"] = round(drawdown, 2)
                    changed = True
            if rec.get("short_signal") and rec.get("short_entry_pct"):
                entry_pct = float(rec.get("short_entry_pct") or 0)
                if entry_pct > 0:
                    short_drop = max(0.0, (entry_pct - coin.max_change) / entry_pct * 100)
                    if short_drop > float(rec.get("short_max_drop_pct") or 0):
                        rec["short_max_drop_pct"] = round(short_drop, 2)
                        changed = True
                    if short_drop >= 5 and not rec.get("short_hit_5"):
                        rec["short_hit_5"] = True
                        changed = True
                    if short_drop >= 10 and not rec.get("short_hit_10"):
                        rec["short_hit_10"] = True
                        changed = True
                    if short_drop >= 20 and not rec.get("short_hit_20"):
                        rec["short_hit_20"] = True
                        changed = True

    for sym in list(active_pumps.keys()):
        if sym not in active_now:
            rec = history_records[active_pumps[sym]]
            if not rec.get("end_time"):
                rec["end_time"] = now_iso
                changed = True
            active_pumps.pop(sym, None)

    if changed:
        save_history()


def mark_short_signal(symbol: str, indicators: Dict, *, entry_pct: float, entry_price: float, confidence: str):
    idx = active_pumps.get(symbol)
    if idx is None:
        return
    rec = history_records[idx]
    if rec.get("short_signal"):
        return
    rec["short_signal"] = True
    rec["short_time"] = datetime.now().isoformat(timespec="seconds")
    rec["short_indicators"] = indicators
    rec["short_entry_pct"] = round(entry_pct, 2)
    rec["short_entry_price"] = round(entry_price, 8)
    rec["short_confidence"] = confidence
    save_history()


# =========================
# Lógica principal
# =========================
def process(coins: List[AggregatedCoin]):
    global last_summary

    current_syms = {c.symbol for c in coins}
    short_candidates = sorted(
        [c for c in coins if c.max_change >= SHORT_MIN_PCT],
        key=lambda c: -c.max_change
    )[:MAX_SIGNAL_COINS]
    short_candidate_syms = {c.symbol for c in short_candidates}

    for coin in coins:
        pct = coin.max_change
        sym = coin.symbol

        if pct < PRE_PUMP_MIN:
            if sym in progressive_state:
                progressive_state.pop(sym, None)
            continue

        state = progressive_state.get(sym)
        if not state:
            state = {"levels": set(), "peak": pct, "reversal": set()}
            progressive_state[sym] = state
        else:
            if pct > state.get("peak", 0):
                state["peak"] = pct

        for level_key, threshold, title, note in PROGRESSIVE_LEVELS:
            if pct >= threshold and level_key not in state["levels"]:
                log.info(f"{title}: {sym} +{pct:.1f}%")
                send(format_progressive_alert(coin, title, note), reply_markup=build_alert_keyboard(coin))
                state["levels"].add(level_key)

        peak = state.get("peak", pct)
        if peak >= PRE_PUMP_MIN and pct < peak:
            drop_ratio = (peak - pct) / peak if peak else 0
            for rev_key, drop_threshold, title, note in REVERSAL_LEVELS:
                if drop_ratio >= drop_threshold and rev_key not in state["reversal"]:
                    log.info(f"{title}: {sym} pico +{peak:.1f}% → +{pct:.1f}%")
                    send(format_reversal_alert(coin, peak, drop_ratio, title, note), reply_markup=build_alert_keyboard(coin))
                    state["reversal"].add(rev_key)

        if sym in short_candidate_syms:
            analysis = analyze_short_signal(coin)
            if analysis:
                latest_signals[sym] = {
                    "symbol": sym,
                    "status": analysis.get("status"),
                    "hits": analysis.get("hits"),
                    "total": analysis.get("total"),
                    "confidence": analysis.get("confidence"),
                    "indicators": {
                        "volume_weak": analysis.get("volume_weak"),
                        "speed_fast": analysis.get("speed_fast"),
                        "order_pressure": analysis.get("order_pressure"),
                        "funding_high": analysis.get("funding_high"),
                        "funding_divergence": analysis.get("funding_divergence"),
                        "oi_drop": analysis.get("oi_drop"),
                        "distance_risk": analysis.get("distance_risk")
                    },
                    "meta": {
                        "fake_pump": analysis.get("fake_pump"),
                        "illiquid": analysis.get("illiquid"),
                        "recent_quote_vol": analysis.get("recent_quote_vol"),
                        "oi_usd": analysis.get("oi_usd")
                    },
                    "updated_at": datetime.now().isoformat(timespec="seconds")
                }

            if analysis and analysis.get("status") == "short":
                state = signal_state.get(sym, {})
                if not state.get("short_sent"):
                    best = max(coin.sources.values(), key=lambda t: t.change_pct)
                    entry_price = float(best.last_price or 0)
                    stop_price = entry_price * (1 + SHORT_STOP_BUFFER_PCT / 100) if entry_price else None
                    tp1_price = entry_price * (1 - SHORT_TP1_PCT / 100) if entry_price else None
                    tp2_price = entry_price * (1 - SHORT_TP2_PCT / 100) if entry_price else None
                    analysis["stop_price"] = stop_price
                    analysis["tp1_price"] = tp1_price
                    analysis["tp2_price"] = tp2_price

                    log.info(f"🎯 SHORT: {sym} +{pct:.1f}% ({analysis.get('hits')} de {analysis.get('total')})")
                    message = format_short_signal(coin, analysis)
                    send(message, reply_markup=build_alert_keyboard(coin))
                    webhook_text = strip_html(message)
                    if DISCORD_WEBHOOK_URL:
                        send_webhook(DISCORD_WEBHOOK_URL, webhook_text)
                    if GENERIC_WEBHOOK_URL:
                        send_webhook(GENERIC_WEBHOOK_URL, webhook_text)
                    state["short_sent"] = True
                    signal_state[sym] = state
                    mark_short_signal(
                        sym,
                        {
                            "hits": analysis.get("hits"),
                            "total": analysis.get("total"),
                            "volume_weak": analysis.get("volume_weak"),
                            "speed_fast": analysis.get("speed_fast"),
                            "order_pressure": analysis.get("order_pressure"),
                            "funding_high": analysis.get("funding_high"),
                            "funding_divergence": analysis.get("funding_divergence"),
                            "oi_drop": analysis.get("oi_drop"),
                            "distance_risk": analysis.get("distance_risk"),
                            "fake_pump": analysis.get("fake_pump"),
                            "illiquid": analysis.get("illiquid")
                        },
                        entry_pct=coin.max_change,
                        entry_price=entry_price,
                        confidence=analysis.get("confidence") or ""
                    )

    for sym in list(progressive_state.keys()):
        if sym not in current_syms:
            progressive_state.pop(sym, None)

    for sym in list(signal_state.keys()):
        if sym not in current_syms:
            signal_state.pop(sym, None)
        else:
            if sym in current_syms:
                coin = next((c for c in coins if c.symbol == sym), None)
                if coin and coin.max_change < PRE_PUMP_MIN:
                    signal_state.pop(sym, None)

    for sym in list(latest_signals.keys()):
        if sym not in current_syms:
            latest_signals.pop(sym, None)

    mins_since = (datetime.now() - last_summary).total_seconds() / 60
    if mins_since >= SUMMARY_INTERVAL_MINS:
        log.info("📊 Enviando resumo periódico...")
        send(msg_summary(coins))
        last_summary = datetime.now()


def startup_msg():
    sources = "Binance + Bybit"
    if CMC_API_KEY:
        sources += " + CMC"
    cap_info = "ativa" if CMC_API_KEY else "desativada"
    binance_auth = "ok" if BINANCE_API_KEY and BINANCE_API_SECRET else "ausente"
    bybit_auth = "ok" if BYBIT_API_KEY and BYBIT_API_SECRET else "ausente"
    send(
        f"✅ <b>Smart Pump Finder ATIVO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛰️ Fontes: <b>{sources}</b>\n"
        f"🔑 CoinMarketCap: <b>{cap_info}</b>\n"
        f"🔐 Binance auth: <b>{binance_auth}</b>\n"
        f"🔐 Bybit auth: <b>{bybit_auth}</b>\n"
        f"⚙️ Threshold pump: <b>+{PUMP_MIN}%</b>\n"
        f"💥 Threshold explosão: <b>+{EXPLOSION_MIN}%</b>\n"
        f"🌌 Threshold mega: <b>+{MEGA_MIN}%</b>\n"
        f"⚡ Pré-pump: <b>+{PRE_PUMP_MIN}% – {PRE_PUMP_MAX}%</b>\n"
        f"🔁 Intervalo: <b>{INTERVAL_SECS}s</b>\n"
        f"💧 Volume mín: <b>${MIN_VOLUME_USDT:,.0f} USDT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 Monitoramento iniciado"
    )


def main():
    log.info("=" * 55)
    log.info("  SMART PUMP FINDER — Bot Telegram")
    log.info("=" * 55)

    start_keepalive_server()

    if not BOT_TOKEN or not CHAT_ID:
        log.error("❌ Configure SPF_BOT_TOKEN e SPF_CHAT_ID antes de executar!")
        return

    if RESET_HISTORY_ON_START:
        reset_persistent_history()
    if RESET_RUNTIME_ON_START:
        reset_runtime_state()

    cmc_cache = CmcCache(CMC_API_KEY)
    load_history()

    log.info("🚀 Iniciando bot...")
    startup_msg()

    cycle = 0
    while True:
        cycle += 1
        log.info(f"🔄 Ciclo #{cycle} — {datetime.now().strftime('%H:%M:%S')}")

        binance = fetch_binance()
        bybit = fetch_bybit()
        symbols = list({t.symbol.replace("USDT", "") for t in binance + bybit})
        cmc_data = cmc_cache.get(symbols)
        cmc_tickers = build_cmc_tickers(cmc_data)
        tickers = binance + bybit + cmc_tickers

        if data_stale(tickers):
            log.warning(f"Dados estagnados por mais de {DATA_STALE_RESET_SECS}s. Reiniciando conexao HTTP.")
            reset_connections(cmc_cache)
            time.sleep(1)
            continue

        coins = aggregate(tickers, cmc_data)

        if coins:
            log.info(f"   {len(coins)} pares agregados")
            process(coins)
            update_pump_history(coins)
        else:
            log.warning("   Nenhum dado retornado")

        time.sleep(INTERVAL_SECS)


if __name__ == "__main__":
    main()
