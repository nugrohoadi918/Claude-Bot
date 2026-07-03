import os
import json
import logging
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
import requests

# ============================================================
# KONFIGURASI — Diambil dari Environment Variables
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
WEBHOOK_SECRET     = os.getenv("WEBHOOK_SECRET", "rahasia123")
PORT = int(os.getenv("PORT", 5000))
WIB = timezone(timedelta(hours=7))

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        log.info("Pesan terkirim ke Telegram")
        return True
    except Exception as e:
        log.error(f"Gagal kirim Telegram: {e}")
        return False


def ask_claude(signal_data):
    if not ANTHROPIC_API_KEY:
        return ""
    prompt = f"""Kamu adalah analis trading profesional.
Berikan analisis singkat (maks 3 kalimat) untuk sinyal berikut:
Ticker: {signal_data.get('ticker', 'N/A')}
Aksi: {signal_data.get('action', 'N/A')}
Harga: {signal_data.get('price', 'N/A')}
Timeframe: {signal_data.get('timeframe', 'N/A')}
Indikator: {signal_data.get('indicator', 'N/A')}
Fokus pada level support/resistance terdekat dan risk/reward. Jawab dalam Bahasa Indonesia."""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    except Exception as e:
        log.error(f"Claude API error: {e}")
        return ""


def format_signal_message(data, claude_analysis=""):
    now = datetime.now(WIB).strftime("%d/%m/%Y %H:%M WIB")
    action = data.get("action", "SIGNAL").upper()
    ticker = data.get("ticker", "???")
    price  = data.get("price", "-")
    tf     = data.get("timeframe", "-")
    sl     = data.get("stoploss", "-")
    tp     = data.get("takeprofit", "-")
    indicator = data.get("indicator", "-")
    comment   = data.get("comment", "")
    emoji = {"BUY": "\U0001f7e2", "SELL": "\U0001f534", "CLOSE": "\u26aa"}.get(action, "\U0001f514")
    msg = f"""{emoji} <b>{action} — {ticker}</b>

\U0001f4b0 Harga: <code>{price}</code>
\u23f1 Timeframe: {tf}
\U0001f4ca Indikator: {indicator}
\U0001f6d1 Stop Loss: <code>{sl}</code>
\U0001f3af Take Profit: <code>{tp}</code>"""
    if comment:
        msg += f"\n\U0001f4ac {comment}"
    if claude_analysis:
        msg += f"\n\n\U0001f916 <b>Analisis Claude:</b>\n<i>{claude_analysis}</i>"
    msg += f"\n\n\U0001f550 {now}"
    return msg


@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data(as_text=True)
    log.info(f"Webhook diterima: {raw[:500]}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"action": "ALERT", "comment": raw}
    if WEBHOOK_SECRET:
        secret = data.get("secret", "")
        if secret and secret != WEBHOOK_SECRET:
            return jsonify({"error": "unauthorized"}), 401
    claude_analysis = ask_claude(data)
    message = format_signal_message(data, claude_analysis)
    success = send_telegram(message)
    if success:
        return jsonify({"status": "sent"}), 200
    else:
        return jsonify({"error": "telegram failed"}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running", "time": datetime.now(WIB).isoformat()})


@app.route("/test", methods=["GET"])
def test_signal():
    test_data = {
        "action": "BUY",
        "ticker": "BTCUSDT",
        "price": "67500.00",
        "timeframe": "4H",
        "indicator": "EMA Cross + RSI",
        "stoploss": "66000.00",
        "takeprofit": "70000.00",
        "comment": "Ini sinyal TEST",
    }
    claude_analysis = ask_claude(test_data)
    message = format_signal_message(test_data, claude_analysis)
    success = send_telegram(message)
    return jsonify({"status": "test sent" if success else "failed"})


if __name__ == "__main__":
    log.info(f"Server berjalan di port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
