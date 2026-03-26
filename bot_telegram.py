
"""
SMART PUMP FINDER — Bot Telegram (Multi-Source)

Setup:
  1) pip install requests
  2) Defina as variáveis de ambiente:
     TELEGRAM_TOKEN, CHAT_ID, CMC_API_KEY (opcional)
  3) python bot_telegram.py
"""

import os
import time
import logging
import requests
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

# =========================
# Configuração (ENV)
# =========================
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", os.getenv("SPF_BOT_TOKEN", "")).strip()
CHAT_ID = os.getenv("CHAT_ID", os.getenv("SPF_CHAT_ID", "")).strip()
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

BINANCE_URL = "https://api.binance.com/api/v3/ticker/24hr"
BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=spot"
CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("SPF")

session = requests.Session()

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

# =========================
# Utilidades
# =========================
EXCHANGE_LABELS = {
    "binance": "Binance",
    "bybit": "Bybit"
}

ALERT_STORE = {
    "pump": {},
    "explosion": {},
    "mega": {},
    "pre": {}
}

last_summary = datetime.now()

def is_valid_symbol(symbol: str) -> bool:
    if not symbol.endswith("USDT"):
        return False
    for bad in ("UP", "DOWN", "BULL", "BEAR"):
        if bad in symbol:
            return False
    return True


def fetch_binance() -> List[Ticker]:
    try:
        r = session.get(BINANCE_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
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
    except Exception as e:
        log.error(f"Erro Binance API: {e}")
        return []


def fetch_bybit() -> List[Ticker]:
    try:
        r = session.get(BYBIT_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
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
    except Exception as e:
        log.error(f"Erro Bybit API: {e}")
        return []


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
                    "Accept": "application/json"
                }
                try:
                    r = session.get(CMC_URL, params=params, headers=headers, timeout=12)
                    r.raise_for_status()
                    data = r.json().get("data", {})
                    for sym, info in data.items():
                        market_cap = info.get("quote", {}).get("USD", {}).get("market_cap")
                        rank = info.get("cmc_rank")
                        self.cache[sym] = {"market_cap": market_cap, "cmc_rank": rank}
                        self.cache_ts[sym] = now
                        fresh[sym] = self.cache[sym]
                except Exception as e:
                    log.error(f"Erro CMC API: {e}")
        return fresh


def chunked(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def aggregate(binance: List[Ticker], bybit: List[Ticker], cmc: Dict[str, Dict]) -> List[AggregatedCoin]:
    merged: Dict[str, Dict] = {}
    for t in binance + bybit:
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
            cmc_rank=cmc_rank
        ))
    return coins

# =========================
# Telegram
# =========================
TG_URL = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)


def send(text: str, parse_mode: str = "HTML", disable_preview: bool = False):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        r = session.post(TG_URL, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview
        }, timeout=8)
        if not r.ok:
            log.warning(f"Telegram erro: {r.text}")
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


def chart_link(symbol: str, exchange: str) -> str:
    tv_exchange = "BINANCE" if exchange == "binance" else "BYBIT"
    return f"https://www.tradingview.com/chart/?symbol={tv_exchange}:{symbol}"


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
    primary_exchange = max(coin.sources.values(), key=lambda t: t.change_pct).exchange
    link = chart_link(coin.symbol, primary_exchange)

    lines = [
        f"<b>{alert_header(level, coin.priority)}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🪙 <b>{coin.base}/USDT</b>",
        f"🏦 Exchanges: <b>{exchanges}</b>",
        f"📈 Variação 24h: <b>{pct_by_ex}</b>",
        f"💧 Volume 24h: <b>{vol_by_ex}</b>",
    ]

    if coin.market_cap:
        lines.append(f"💎 Market Cap: <b>${fmt_vol(coin.market_cap)}</b>")
    if coin.cmc_rank:
        lines.append(f"🏅 Rank: <b>#{coin.cmc_rank}</b>")

    lines.extend([
        f"🔗 <a href=\"{link}\">Abrir gráfico</a>",
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    ])

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
        f"• <b>{c.base}</b> → +{c.max_change:.1f}% ({', '.join(EXCHANGE_LABELS.get(ex, ex) for ex in c.sources)})"
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
# Lógica principal
# =========================
def should_alert(store: Dict[str, datetime], symbol: str) -> bool:
    last = store.get(symbol)
    if not last:
        return True
    return (datetime.now() - last).total_seconds() > COOLDOWN_SECS


def process(coins: List[AggregatedCoin]):
    global last_summary

    for coin in coins:
        pct = coin.max_change
        sym = coin.symbol

        if pct >= MEGA_MIN:
            if should_alert(ALERT_STORE["mega"], sym):
                log.info(f"🌌 MEGA: {sym} +{pct:.1f}%")
                send(format_alert(coin, "mega"))
                ALERT_STORE["mega"][sym] = datetime.now()
        elif pct >= EXPLOSION_MIN:
            if should_alert(ALERT_STORE["explosion"], sym):
                log.info(f"💥 EXPLOSÃO: {sym} +{pct:.1f}%")
                send(format_alert(coin, "explosion"))
                ALERT_STORE["explosion"][sym] = datetime.now()
        elif pct >= PUMP_MIN:
            if should_alert(ALERT_STORE["pump"], sym):
                log.info(f"🔥 PUMP: {sym} +{pct:.1f}%")
                send(format_alert(coin, "pump"))
                ALERT_STORE["pump"][sym] = datetime.now()
        elif PRE_PUMP_MIN <= pct <= PRE_PUMP_MAX:
            if should_alert(ALERT_STORE["pre"], sym):
                log.info(f"⚡ PRÉ: {sym} +{pct:.1f}%")
                send(format_alert(coin, "pre"))
                ALERT_STORE["pre"][sym] = datetime.now()

    mins_since = (datetime.now() - last_summary).total_seconds() / 60
    if mins_since >= SUMMARY_INTERVAL_MINS:
        log.info("📊 Enviando resumo periódico...")
        send(msg_summary(coins))
        last_summary = datetime.now()


def startup_msg():
    sources = "Binance + Bybit"
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

    if not BOT_TOKEN or not CHAT_ID:
        log.error("❌ Configure SPF_BOT_TOKEN e SPF_CHAT_ID antes de executar!")
        return

    cmc_cache = CmcCache(CMC_API_KEY)

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
        coins = aggregate(binance, bybit, cmc_data)

        if coins:
            log.info(f"   {len(coins)} pares agregados")
            process(coins)
        else:
            log.warning("   Nenhum dado retornado")

        time.sleep(INTERVAL_SECS)


if __name__ == "__main__":
    main()
