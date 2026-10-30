import os
import time
import uuid
import threading
import logging
from datetime import datetime, timezone
from statistics import mean, pstdev

import requests
from flask import Flask, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("forex-d1-grid")

FX = "https://api.fxapis.com"
TD = "https://api.twelvedata.com"
SYMBOL_TD = os.getenv("TD_SYMBOL", "EUR/USD")
SYMBOL_MT5 = os.getenv("MT5_SYMBOL", "EURUSD")
LOT = "0.01"
MAX_SIDE = 5
GRID_PIPS = [1500, 2500, 3800, 6800]
TP_PIPS = 50
BASKET_TP = 3.0
PIP = 0.0001
POLL_SECONDS = 60

lock = threading.Lock()
runtime = {"account_id": None, "account_state": "not_connected", "last_cycle": None,
           "last_error": None, "last_action": "none", "trading_enabled": False}

def env(name):
    return os.getenv(name, "").strip()

def fx_headers(idempotency=None):
    h = {"Authorization": f"Bearer {env('FXAPIS_API_KEY')}", "Content-Type": "application/json"}
    if idempotency:
        h["Idempotency-Key"] = idempotency
    return h

def fx_request(method, path, **kwargs):
    r = requests.request(method, FX + path, headers=fx_headers(kwargs.pop("idempotency", None)),
                         timeout=25, **kwargs)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:500]}
    if r.status_code >= 400:
        raise RuntimeError(f"FXAPIS {r.status_code}: {body}")
    return body.get("data", body)

def get_account_id():
    if runtime["account_id"]:
        return runtime["account_id"]
    if env("FXAPIS_ACCOUNT_ID"):
        runtime["account_id"] = env("FXAPIS_ACCOUNT_ID")
        return runtime["account_id"]
    # First try to find an already-connected account in this FXAPIS workspace.
    try:
        accounts = fx_request("GET", "/v1/accounts")
        # Current FXAPIS list responses use {items, next_cursor, total};
        # older responses may use {accounts: [...]} or a bare list.
        if isinstance(accounts, list):
            rows = accounts
        elif isinstance(accounts, dict):
            rows = accounts.get("items") or accounts.get("accounts") or []
        else:
            rows = []
        for a in rows:
            if not isinstance(a, dict):
                continue
            login = a.get("login") or a.get("accountLogin")
            server = a.get("server") or a.get("serverName")
            account_id = a.get("id") or a.get("accountId")
            if str(login or "") == env("XM_LOGIN") and str(server or "").strip() == env("XM_SERVER"):
                if account_id:
                    runtime["account_id"] = account_id
                    log.info("Found existing FXAPIS account; reusing it.")
                    return runtime["account_id"]
    except Exception as e:
        log.warning("Account lookup: %s", e)
    payload = {"login": env("XM_LOGIN"), "server": env("XM_SERVER"),
               "password": env("XM_PASSWORD"), "mode": "warm_on_demand",
               "label": "Forex D1 Grid - XM DEMO"}
    data = fx_request("POST", "/v1/accounts", json=payload)
    runtime["account_id"] = data.get("id")
    if not runtime["account_id"]:
        raise RuntimeError("FXAPIS não retornou o ID da conta.")
    return runtime["account_id"]

def warm_account(account_id):
    try:
        fx_request("POST", f"/v1/accounts/{account_id}/warm", json={})
    except Exception as e:
        # 409/already running is not necessarily a failure; status below decides.
        log.info("Warm response: %s", e)
    status = fx_request("GET", f"/v1/accounts/{account_id}/status")
    state = status.get("state", "unknown")
    runtime["account_state"] = state
    if state != "ready":
        raise RuntimeError(f"Conta MT5 ainda não está pronta: {state}")
    return status

def candles_d1():
    r = requests.get(TD + "/time_series", params={
        "symbol": SYMBOL_TD, "interval": "1day", "outputsize": 60,
        "timezone": "UTC", "apikey": env("TWELVEDATA_API_KEY")
    }, timeout=20)
    data = r.json()
    if r.status_code >= 400 or "values" not in data:
        raise RuntimeError(f"Twelve Data: {data}")
    rows = data["values"]  # newest first
    today = datetime.now(timezone.utc).date().isoformat()
    # Exclude today's still-forming daily candle. Use only fully closed candles.
    rows = [x for x in rows if x.get("datetime", "")[:10] < today]
    rows.sort(key=lambda x: x["datetime"])
    if len(rows) < 25:
        raise RuntimeError("Histórico D1 insuficiente para RSI/Bollinger.")
    return rows

def indicators(rows):
    closes = [float(x["close"]) for x in rows]
    # Wilder-style RSI approximation over the latest 14 changes.
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = changes[-14:]
    gains = [max(v, 0.0) for v in recent]
    losses = [max(-v, 0.0) for v in recent]
    avg_gain, avg_loss = mean(gains), mean(losses)
    rsi = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    window = closes[-20:]
    mid = mean(window)
    sd = pstdev(window)
    lower, upper = mid - 2 * sd, mid + 2 * sd
    last = closes[-1]
    signal = "buy" if rsi <= 30 and last <= lower else ("sell" if rsi >= 70 and last >= upper else None)
    return {"rsi": rsi, "lower": lower, "upper": upper, "close": last,
            "signal": signal, "candle": rows[-1]["datetime"]}

def positions(account_id):
    data = fx_request("GET", f"/v1/accounts/{account_id}/positions")
    return data if isinstance(data, list) else data.get("positions", [])

def live_price():
    r = requests.get(TD + "/price", params={"symbol": SYMBOL_TD,
                     "apikey": env("TWELVEDATA_API_KEY")}, timeout=15)
    d = r.json()
    if r.status_code >= 400 or "price" not in d:
        raise RuntimeError(f"Preço EURUSD indisponível: {d}")
    return float(d["price"])

def close_position(account_id, ticket):
    return fx_request("POST", f"/v1/accounts/{account_id}/positions/{ticket}/close",
                      json={}, idempotency=f"close-{account_id}-{ticket}")

def market_order(account_id, side, slot, candle):
    key = f"d1grid-{candle}-{side}-{slot}"
    payload = {"symbol": SYMBOL_MT5, "side": side, "volume": LOT,
               "comment": "D1Grid demo"}
    return fx_request("POST", f"/v1/accounts/{account_id}/orders/market",
                      json=payload, idempotency=key)

def cycle():
    with lock:
        runtime["last_cycle"] = datetime.now(timezone.utc).isoformat()
        runtime["last_action"] = "checking"
        try:
            required = ["FXAPIS_API_KEY", "TWELVEDATA_API_KEY", "XM_LOGIN", "XM_SERVER", "XM_PASSWORD"]
            missing = [x for x in required if not env(x)]
            if missing:
                raise RuntimeError("Variáveis ausentes: " + ", ".join(missing))
            account_id = get_account_id()
            warm_account(account_id)
            rows = candles_d1()
            ind = indicators(rows)
            pos = positions(account_id)
            pos = [p for p in pos if p.get("symbol") in (SYMBOL_MT5, SYMBOL_TD.replace("/", "")) or p.get("instrument") == SYMBOL_MT5]
            price = live_price()

            # Close the whole basket at +3 account-currency units.
            total_profit = sum(float(p.get("profit") or 0) + float(p.get("swap") or 0) for p in pos)
            if pos and total_profit >= BASKET_TP:
                for p in pos:
                    ticket = p.get("brokerPositionId")
                    if ticket:
                        close_position(account_id, ticket)
                runtime["last_action"] = f"basket_closed_profit_{total_profit:.2f}"
                runtime["last_error"] = None
                return

            # Individual exit at +50 pips from the entry price.
            for p in pos:
                entry = float(p.get("openPrice") or 0)
                current = float(p.get("currentPrice") or price)
                side = p.get("side")
                gain_pips = ((current-entry)/PIP if side == "buy" else (entry-current)/PIP)
                if gain_pips >= TP_PIPS and p.get("brokerPositionId"):
                    close_position(account_id, p["brokerPositionId"])

            # Refresh after any individual exits.
            pos = positions(account_id)
            pos = [p for p in pos if p.get("symbol") in (SYMBOL_MT5, SYMBOL_TD.replace("/", "")) or p.get("instrument") == SYMBOL_MT5]
            buys = [p for p in pos if p.get("side") == "buy"]
            sells = [p for p in pos if p.get("side") == "sell"]

            # Initial entry only when flat, based on the last fully closed D1 candle.
            if not pos and ind["signal"]:
                market_order(account_id, ind["signal"], 0, ind["candle"])
                runtime["last_action"] = f"opened_initial_{ind['signal']}"
            else:
                # Add one grid order at a time, measuring adverse distance from the most recent entry.
                for side, side_positions in (("buy", buys), ("sell", sells)):
                    n = len(side_positions)
                    if 1 <= n < MAX_SIDE:
                        latest = max(side_positions, key=lambda p: p.get("openedAt") or "")
                        anchor = float(latest.get("openPrice") or 0)
                        adverse_pips = ((anchor-price)/PIP if side == "buy" else (price-anchor)/PIP)
                        threshold = GRID_PIPS[n-1]
                        if adverse_pips >= threshold:
                            market_order(account_id, side, n, ind["candle"])
                            runtime["last_action"] = f"grid_{n+1}_{side}"
                            break
            runtime["last_error"] = None
            runtime["trading_enabled"] = True
            log.info("Cycle ok: %s", runtime["last_action"])
        except Exception as e:
            runtime["last_error"] = str(e)[:700]
            runtime["trading_enabled"] = False
            log.exception("Trading cycle failed")

def worker():
    while True:
        cycle()
        time.sleep(POLL_SECONDS)

@app.get("/")
def home():
    return jsonify({"service":"Forex D1 Grid Bot","mode":"XM_DEMO",
        "strategy":{"symbol":SYMBOL_MT5,"timeframe":"D1","lot":LOT,
        "max_positions_per_side":MAX_SIDE,"grid_pips":GRID_PIPS,
        "individual_tp_pips":TP_PIPS,"basket_tp":BASKET_TP,
        "stop_loss":"none"},
        "runtime":runtime}), 200

@app.get("/health")
def health():
    return jsonify({"status":"ok"}), 200

@app.get("/ready")
def ready():
    checks = {"fxapis_api_key":bool(env("FXAPIS_API_KEY")),
              "market_data_api_key":bool(env("TWELVEDATA_API_KEY")),
              "xm_login":bool(env("XM_LOGIN")),"xm_server":bool(env("XM_SERVER")),
              "xm_password_configured":bool(env("XM_PASSWORD"))}
    return jsonify({"checks":checks,"runtime":runtime,
                    "note":"Conexão e operação dependem do estado real informado pela FXAPIS."}), 200

if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
