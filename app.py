import os
from flask import Flask, jsonify

app = Flask(__name__)

# Safety lock: this project remains in DEMO/diagnostic mode until the
# broker connection, D1 feed, durable state store and order safeguards
# have all been verified.
TRADING_ENABLED = False
GRID_PIPS = [1500, 2500, 3800, 6800]
LOT_SIZE = 0.01
MAX_POSITIONS_PER_SIDE = 5
INDIVIDUAL_TAKE_PROFIT_PIPS = 50
BASKET_TAKE_PROFIT_USD = 3.0


def readiness():
    checks = {
        "fxapis_api_key": bool(os.getenv("FXAPIS_API_KEY")),
        "market_data_api_key": bool(os.getenv("TWELVEDATA_API_KEY")),
        "xm_login": bool(os.getenv("XM_LOGIN")),
        "xm_server": bool(os.getenv("XM_SERVER")),
        "xm_password_configured": bool(os.getenv("XM_PASSWORD")),
        "database_url": bool(os.getenv("DATABASE_URL")),
    }
    missing = [name for name, ok in checks.items() if not ok]
    return checks, missing


@app.get("/")
def home():
    checks, missing = readiness()
    return jsonify({
        "service": "Forex D1 Grid Bot",
        "status": "online",
        "mode": "diagnostic_only",
        "trading_enabled": TRADING_ENABLED,
        "checks": checks,
        "missing_configuration": missing,
        "strategy": {
            "timeframe": "D1",
            "signal": "RSI(14) + Bollinger(20, 2), last closed candle",
            "lot_per_order": LOT_SIZE,
            "max_positions_per_side": MAX_POSITIONS_PER_SIDE,
            "grid_distances_pips": GRID_PIPS,
            "individual_take_profit_pips": INDIVIDUAL_TAKE_PROFIT_PIPS,
            "basket_take_profit_account_currency": BASKET_TAKE_PROFIT_USD
        },
        "message": "Diagnóstico disponível. Nenhuma ordem será enviada enquanto todos os requisitos não forem validados."
    })


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/ready")
def ready():
    checks, missing = readiness()
    # Presence is not proof of valid credentials; external connection tests
    # are still required before any trading can be enabled.
    return jsonify({
        "ready_for_connection_test": len(missing) == 0,
        "checks": checks,
        "missing_configuration": missing,
        "trading_enabled": TRADING_ENABLED,
        "note": "A presença das variáveis não valida credenciais, feed D1 ou execução."
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
