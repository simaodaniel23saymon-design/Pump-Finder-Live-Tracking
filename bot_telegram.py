
"""
SMART PUMP FINDER — Bot Telegram (Multi-Source)

Setup:
  1) pip install requests
  2) Defina as variáveis de ambiente:
     TELEGRAM_TOKEN, CHAT_ID, CMC_API_KEY (opcional)
  3) python bot_telegram.py
"""

import os
import json
import html as html_lib
import re
import time
import logging
import threading
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

PUMP_MIN = int(os.getenv("SPF_PUMP_MIN", "300"))
EXPLOSION_MIN = int(os.getenv("SPF_EXPLOSION_MIN", "500"))
MEGA_MIN = int(os.getenv("SPF_MEGA_MIN", "1000"))
PRE_PUMP_MIN = int(os.getenv("SPF_PRE_PUMP_MIN", "100"))
PRE_PUMP_MAX = int(os.getenv("SPF_PRE_PUMP_MAX", "299"))

MIN_VOLUME_USDT = float(os.getenv("SPF_MIN_VOLUME_USDT", "50000"))
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

BINANCE_URL = "https://api.binance.com/api/v3/ticker/24hr"
BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=spot"
CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&order=price_change_percentage_24h_desc&per_page=250&page=1"
    "&sparkline=true&price_change_percentage=24h"
)
COINGECKO_MIN_INTERVAL_SECS = int(os.getenv("SPF_COINGECKO_MIN_INTERVAL_SECS", "30"))
HISTORY_FILE = os.getenv("SPF_HISTORY_FILE", "pump_history.json")

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
    cg_id: Optional[str]
    multi_source: bool

# =========================
# Utilidades
# =========================
EXCHANGE_LABELS = {
    "binance": "Binance",
    "bybit": "Bybit",
    "coingecko": "CoinGecko",
    "cmc": "CoinMarketCap"
}

ALERT_STORE = {
    "explosion": {},
    "mega": {}
}

PROGRESSIVE_LEVELS = [
    ("p100", 100, "⚡ ALERTA +100%", "Atingiu +100% — início de movimento forte"),
    ("p200", 200, "🚨 ALERTA +200%", "Atingiu +200% — aceleração detectada"),
    ("p299", 299, "☢️ ZONA CRÍTICA", "Zona crítica — atenção máxima"),
    ("p300", 300, "🔥 PUMP CONFIRMADO", "Pump confirmado — acima de +300%")
]

REVERSAL_LEVELS = [
    ("drop5", 0.05, "🔻 REGRESSÃO", "Moeda a regredir, atenção"),
    ("drop10", 0.10, "⚠️ REVERSÃO CONFIRMADA", "Reversão confirmada, cuidado")
]

last_summary = datetime.now()
binance_blocked_until = 0.0
coingecko_last_fetch = 0.0
coingecko_cache: List[Ticker] = []
history_records: List[Dict] = []
active_pumps: Dict[str, int] = {}
progressive_state: Dict[str, Dict] = {}


class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health", "/ping"):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

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


def fetch_binance() -> List[Ticker]:
    global binance_blocked_until
    now = time.time()
    if now < binance_blocked_until:
        remaining = int(binance_blocked_until - now)
        log.warning(f"Binance bloqueada (451). Usando Bybit/CMC por mais {remaining}s.")
        return []
    try:
        data = get_json_with_retries(
            BINANCE_URL,
            headers=DEFAULT_HEADERS,
            timeout=HTTP_TIMEOUT_SECS
        )
        out = []
        for d in data:
            symbol = d.get("symbol", "")
            if not is_valid_symbol(symbol):
                continue
            vol = float(d.get("quoteVolume", 0))
            if vol < MIN_VOLUME_USDT:
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
        data = get_json_with_retries(
            BYBIT_URL,
            headers=DEFAULT_HEADERS,
            timeout=HTTP_TIMEOUT_SECS
        )
        items = data.get("result", {}).get("list", [])
        out = []
        for d in items:
            symbol = d.get("symbol", "")
            if not is_valid_symbol(symbol):
                continue
            vol = float(d.get("turnover24h", 0))
            if vol < MIN_VOLUME_USDT:
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

def fetch_coingecko() -> List[Ticker]:
    global coingecko_last_fetch, coingecko_cache
    now = time.time()
    if (now - coingecko_last_fetch) < COINGECKO_MIN_INTERVAL_SECS and coingecko_cache:
        return coingecko_cache
    try:
        data = get_json_with_retries(
            COINGECKO_URL,
            headers=DEFAULT_HEADERS,
            timeout=HTTP_TIMEOUT_SECS
        )
        out = []
        for d in data:
            base = (d.get("symbol") or "").upper()
            if not base:
                continue
            symbol = f"{base}USDT"
            if not is_valid_symbol(symbol):
                continue
            last = float(d.get("current_price") or 0)
            change_pct = d.get("price_change_percentage_24h")
            change_pct = float(change_pct) if change_pct is not None else 0.0
            open_price = last / (1 + change_pct / 100) if last and change_pct else 0.0
            if not open_price:
                price_change = d.get("price_change_24h")
                if price_change is not None and last:
                    open_price = last - float(price_change)
            if not open_price:
                open_price = last
            vol = float(d.get("total_volume") or 0)
            if vol < MIN_VOLUME_USDT:
                continue
            out.append(Ticker(
                symbol=symbol,
                exchange="coingecko",
                last_price=last,
                open_price=open_price,
                change_pct=change_pct,
                quote_volume=vol,
                meta={"cg_id": d.get("id")}
            ))
        coingecko_cache = out
        coingecko_last_fetch = now
        return out
    except requests.HTTPError as e:
        status = e.response.status_code if e.response else None
        log.error(f"Erro CoinGecko API ({status}): {e}")
        return coingecko_cache if coingecko_cache else []
    except Exception as e:
        log.error(f"Erro CoinGecko API: {e}")
        return coingecko_cache if coingecko_cache else []


class CmcCache:
    def __init__(self, api_key: str, ttl_secs: int = 600):
        self.api_key = api_key
        self.ttl_secs = ttl_secs
        self.cache: Dict[str, Dict] = {}
        self.cache_ts: Dict[str, float] = {}

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
        cg_id = None
        for t in sources.values():
            if t.meta and t.meta.get("cg_id"):
                cg_id = t.meta.get("cg_id")
                break
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
            cg_id=cg_id,
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
    if "coingecko" in coin.sources:
        cg_id = (coin.cg_id or coin.base).lower()
        links.append({"label": "CoinGecko", "url": f"https://www.coingecko.com/en/coins/{cg_id}"})
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

    return (
        f"📊 <b>RESUMO — Smart Pump Finder</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 Pumps +300%: <b>{len(above_300)}</b>\n"
        f"💥 Explosão +500%: <b>{len(above_500)}</b>\n"
        f"🌌 Mega +1000%: <b>{len(above_1000)}</b>\n"
        f"⚡ Pré-pump: <b>{len(pre)}</b>\n"
        f"🔁 Confluências: <b>{len(dual)}</b>\n"
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
                "sources": sources
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

    for sym in list(active_pumps.keys()):
        if sym not in active_now:
            rec = history_records[active_pumps[sym]]
            if not rec.get("end_time"):
                rec["end_time"] = now_iso
                changed = True
            active_pumps.pop(sym, None)

    if changed:
        save_history()


# =========================
# Lógica principal
# =========================
def should_alert(store: Dict[str, datetime], symbol: str) -> bool:
    last = store.get(symbol)
    if not last:
        return True
    return (datetime.now() - last).total_seconds() > COOLDOWN_SECS


def process(coins: List[AggregatedCoin]):
    global last_summary

    current_syms = {c.symbol for c in coins}
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

        if pct >= MEGA_MIN:
            if should_alert(ALERT_STORE["mega"], sym):
                log.info(f"🌌 MEGA: {sym} +{pct:.1f}%")
                send(format_alert(coin, "mega"), reply_markup=build_alert_keyboard(coin))
                ALERT_STORE["mega"][sym] = datetime.now()
        elif pct >= EXPLOSION_MIN:
            if should_alert(ALERT_STORE["explosion"], sym):
                log.info(f"💥 EXPLOSÃO: {sym} +{pct:.1f}%")
                send(format_alert(coin, "explosion"), reply_markup=build_alert_keyboard(coin))
                ALERT_STORE["explosion"][sym] = datetime.now()

    for sym in list(progressive_state.keys()):
        if sym not in current_syms:
            progressive_state.pop(sym, None)

    mins_since = (datetime.now() - last_summary).total_seconds() / 60
    if mins_since >= SUMMARY_INTERVAL_MINS:
        log.info("📊 Enviando resumo periódico...")
        send(msg_summary(coins))
        last_summary = datetime.now()


def startup_msg():
    sources = "Binance + Bybit + CoinGecko"
    if CMC_API_KEY:
        sources += " + CMC"
    cap_info = "ativa" if CMC_API_KEY else "desativada"
    send(
        f"✅ <b>Smart Pump Finder ATIVO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛰️ Fontes: <b>{sources}</b>\n"
        f"🔑 CoinMarketCap: <b>{cap_info}</b>\n"
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
        coingecko = fetch_coingecko()
        symbols = list({t.symbol.replace("USDT", "") for t in binance + bybit})
        cmc_data = cmc_cache.get(symbols)
        cmc_tickers = build_cmc_tickers(cmc_data)
        tickers = binance + bybit + coingecko + cmc_tickers
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
