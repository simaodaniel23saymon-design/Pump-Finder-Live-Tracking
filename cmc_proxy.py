"""
CMC Proxy simples para uso no navegador.

Uso:
  1) pip install requests
  2) Defina CMC_API_KEY
  3) python cmc_proxy.py

Endpoint:
  http://127.0.0.1:8787/cmc?symbols=BTC,ETH
"""

import os
import json
import time
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
CMC_API_KEY = os.getenv("CMC_API_KEY", os.getenv("SPF_CMC_API_KEY", "")).strip()
HOST = os.getenv("SPF_CMC_HOST", "127.0.0.1")
PORT = int(os.getenv("SPF_CMC_PORT", "8787"))
USER_AGENT = os.getenv(
    "SPF_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT_SECS = int(os.getenv("SPF_HTTP_TIMEOUT_SECS", "12"))
RETRY_ATTEMPTS = int(os.getenv("SPF_HTTP_RETRIES", "3"))
RETRY_DELAY_SECS = float(os.getenv("SPF_HTTP_RETRY_DELAY_SECS", "1.2"))

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/json"
})


def get_json_with_retries(url, *, params=None, headers=None, timeout=12):
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


def build_response(data, status=200):
    payload = json.dumps(data).encode("utf-8")
    return status, payload


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/cmc":
            self.send_response(404)
            self.end_headers()
            return

        if not CMC_API_KEY:
            status, payload = build_response({"error": "CMC_API_KEY ausente"}, 400)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)
            return

        qs = parse_qs(parsed.query)
        symbols = qs.get("symbols", [""])[0]
        symbols = ",".join([s.strip().upper() for s in symbols.split(",") if s.strip()])

        if not symbols:
            status, payload = build_response({"error": "symbols vazio"}, 400)
        else:
            try:
                data = get_json_with_retries(
                    CMC_URL,
                    params={"symbol": symbols, "convert": "USD"},
                    headers={
                        "X-CMC_PRO_API_KEY": CMC_API_KEY,
                        "Accept": "application/json",
                        "User-Agent": USER_AGENT
                    },
                    timeout=HTTP_TIMEOUT_SECS
                )
                data = data.get("data", {})
                normalized = {
                    sym: {
                        "market_cap": info.get("quote", {}).get("USD", {}).get("market_cap"),
                        "cmc_rank": info.get("cmc_rank")
                    }
                    for sym, info in data.items()
                }
                status, payload = build_response({"data": normalized})
            except Exception as e:
                status, payload = build_response({"error": str(e)}, 500)

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    httpd = HTTPServer((HOST, PORT), Handler)
    print(f"CMC proxy ativo em http://{HOST}:{PORT}/cmc")
    httpd.serve_forever()
