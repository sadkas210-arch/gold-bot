import time
import requests
from datetime import datetime

# ===== الإعدادات =====
TELEGRAM_TOKEN  = "8763311894:AAFNBiBL8Peack9uAEKJa6_MwpIh6ILxAGc"
CHAT_ID         = "1392281304"
TWELVEDATA_KEY  = "4b63389c3e814c0597d8ab94f75e949c"
SYMBOL          = "XAU/USD"
INTERVAL        = "15min"
INTERVAL_MIN    = 15
CANDLES         = 50
# ======================

TG_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
virtual_balance = 10000.0
virtual_trades  = []
open_trade      = None

def send_message(text):
    try:
        requests.post(f"{TG_URL}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
                      timeout=10)
    except Exception as e:
        print(f"خطأ تلغرام: {e}")

def get_gold_prices():
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol":     SYMBOL,
        "interval":   INTERVAL,
        "outputsize": CANDLES,
        "apikey":     TWELVEDATA_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if "values" not in data:
            print(f"خطأ API: {data}")
            return None
        vals   = list(reversed(data["values"]))
        prices = [float(c["close"]) for c in vals]
        highs  = [float(c["high"])  for c in vals]
        lows   = [float(c["low"])   for c in vals]
        return prices, highs, lows
    except Exception as e:
        print(f"خطأ جلب البيانات: {e}")
        return None

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100
    return round(100 - (100 / (1 + ag/al)), 1)

def calc_macd(prices):
    def ema(data, n):
        k = 2 / (n + 1)
        e = data[0]
        for p in data[1:]:
            e = p * k + e * (1 - k)
        return e
    if len(prices) < 26:
        return 0
    return round(ema(prices, 12) - ema(prices, 26), 4)

def calc_ma(prices, period):
    if len(prices) < period:
        return prices[-1]
    return round(sum(prices[-period:]) / period, 2)

def calc_atr(highs, lows, prices, period=14):
    trs = []
    for i in range(1, len(prices)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - prices[i-1]),
                 abs(lows[i]  - prices[i-1]))
        trs.append(tr)
    if not trs:
        return 5.0
    return round(sum(trs[-period:]) / min(period, len(trs)), 2)

def calc_bb(prices, period=20, dev=2.0):
    if len(prices) < period:
        return prices[-1], prices[-1], prices[-1]
    ma  = sum(prices[-period:]) / period
    std = (sum((p - ma)**2 for p in prices[-period:]) / period) ** 0.5
    return round(ma + dev*std, 2), round(ma, 2), round(ma - dev*std, 2)

def ai_analyze(prices, highs, lows):
    global open_trade, virtual_balance, virtual_trades

    price    = prices[-1]
    rsi      = calc_rsi(prices)
    macd     = calc_macd(prices)
    ma20     = calc_ma(prices, 20)
    ma50     = calc_ma(prices, 50)
    ma200    = calc_ma(prices, min(200, len(prices)))
    atr      = calc_atr(highs, lows, prices)
    bb_up, bb_mid, bb_low = calc_bb(prices)
    trend    = prices[-1] - prices[-10] if len(prices) >= 10 else 0
    sl_dist  = atr * 1.5
    tp_dist  = atr * 3.0

    buy_score = sell_score = 0
    signals = []

    if rsi < 35:
        buy_score += 2
        signals.append(f"📉 RSI={rsi} ذروة بيع")
    elif rsi > 65:
        sell_score += 2
        signals.append(f"📈 RSI={rsi} ذروة شراء")
    else:
        signals.append(f"➡️ RSI={rsi} محايد")

    if macd > 0:
        buy_score += 2
        signals.append(f"✅ MACD إيجابي ({macd})")
    else:
        sell_score += 2
        signals.append(f"❌ MACD سلبي ({macd})")

    if price > ma20 > ma50:
        buy_score += 2
        signals.append("📊 فوق MA20 و MA50")
    elif price < ma20 < ma50:
        sell_score += 2
        signals.append("📊 تحت MA20 و MA50")
    else:
        signals.append("📊 متوسطات محايدة")

    if price > ma200:
        buy_score += 1
        signals.append("🔼 فوق MA200 اتجاه صاعد")
    else:
        sell_score += 1
        signals.append("🔽 تحت MA200 اتجاه هابط")

    if price < bb_low:
        buy_score += 2
        signals.append("💥 تحت Bollinger السفلي")
    elif price > bb_up:
        sell_score += 2
        signals.append("💥 فوق Bollinger العلوي")
    else:
        signals.append("⬜ داخل Bollinger")

    if trend > atr:
        buy_score += 1
        signals.append("⚡ زخم صاعد قوي")
    elif trend < -atr:
        sell_score += 1
        signals.append("⚡ زخم هابط قوي")

    close_msg = ""
    if open_trade:
        pl = 0
        if open_trade["type"] == "BUY":
            pl = (price - open_trade["entry"]) * 10
            if price >= open_trade["tp"] or price <= open_trade["sl"]:
                result = "✅ ربح" if price >= open_trade["tp"] else "❌ خسارة"
                virtual_balance += pl
                virtual_trades.append(pl)
                close_msg = f"\n\n🔒 <b>إغلاق شراء</b>\n{result}: <b>${pl:+.2f}</b>\nالرصيد: <b>${virtual_balance:.2f}</b>"
                open_trade = None
        elif open_trade["type"] == "SELL":
            pl = (open_trade["entry"] - price) * 10
            if price <= open_trade["tp"] or price >= open_trade["sl"]:
                result = "✅ ربح" if price <= open_trade["tp"] else "❌ خسارة"
                virtual_balance += pl
                virtual_trades.append(pl)
                close_msg = f"\n\n🔒 <b>إغلاق بيع</b>\n{result}: <b>${pl:+.2f}</b>\nالرصيد: <b>${virtual_balance:.2f}</b>"
                open_trade = None

    action = confidence = sl = tp = 0
    if buy_score >= 5 and buy_score > sell_score and not open_trade:
        action     = "🟢 شراء BUY"
        confidence = min(int((buy_score / 10) * 100), 95)
        sl         = round(price - sl_dist, 2)
        tp         = round(price + tp_dist, 2)
        open_trade = {"type": "BUY", "entry": price, "sl": sl, "tp": tp}
    elif sell_score >= 5 and sell_score > buy_score and not open_trade:
        action     = "🔴 بيع SELL"
        confidence = min(int((sell_score / 10) * 100), 95)
        sl         = round(price + sl_dist, 2)
        tp         = round(price - tp_dist, 2)
        open_trade = {"type": "SELL", "entry": price, "sl": sl, "tp": tp}
    else:
        action     = "⏸ انتظار HOLD"
        confidence = 0
        sl = tp   = 0

    wins   = sum(1 for t in virtual_trades if t > 0)
    losses = sum(1 for t in virtual_trades if t < 0)
    wr     = f"{int(wins/(wins+losses)*100)}%" if (wins+losses) > 0 else "---"

    return {
        "action": action, "confidence": confidence,
        "price": price, "sl": sl, "tp": tp,
        "rsi": rsi, "macd": macd, "atr": atr,
        "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "buy_score": buy_score, "sell_score": sell_score,
        "signals": signals, "close_msg": close_msg,
        "balance": virtual_balance, "win_rate": wr,
        "total_trades": len(virtual_trades)
    }

def format_signal(r):
    now  = datetime.now().strftime("%H:%M - %d/%m/%Y")
    sigs = "".join([f"  {s}\n" for s in r["signals"]])

    if r["confidence"] == 0:
        msg = f"""🤖 <b>AI Gold Trading Bot</b>
⏰ {now}
📌 الذهب <b>XAU/USD</b> | ATR: {r['atr']}

⏸ <b>لا توجد إشارة - انتظر</b>

{sigs}
نقاط شراء: {r['buy_score']}/10 | نقاط بيع: {r['sell_score']}/10
💼 الرصيد الافتراضي: <b>${r['balance']:.2f}</b>
📈 معدل الفوز: {r['win_rate']} ({r['total_trades']} صفقة)"""
    else:
        msg = f"""🤖 <b>AI Gold Trading Bot</b>
⏰ {now}
📌 الذهب <b>XAU/USD</b>

━━━━━━━━━━━━━━━
{r['action']}
نسبة الثقة: <b>{r['confidence']}%</b>
━━━━━━━━━━━━━━━

💰 السعر الحالي: <b>${r['price']}</b>
🛑 وقف الخسارة: <b>${r['sl']}</b>
🎯 جني الأرباح: <b>${r['tp']}</b>
📏 ATR: {r['atr']}

{sigs}
📊 MA20: {r['ma20']} | MA50: {r['ma50']} | MA200: {r['ma200']}
💼 الرصيد الافتراضي: <b>${r['balance']:.2f}</b>
📈 معدل الفوز: {r['win_rate']} ({r['total_trades']} صفقة)

⚠️ محاكاة افتراضية - ليس تداولاً حقيقياً"""

    return msg + r["close_msg"]

def main():
    print("🤖 بوت الذهب يبدأ...")
    send_message("🥇 <b>AI Gold Trading Bot شغّال!</b>\nيحلل أسعار الذهب الحقيقية كل 15 دقيقة ✅")

    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M')}] جاري جلب أسعار الذهب...")
            data = get_gold_prices()
            if data is None:
                time.sleep(60)
                continue
            prices, highs, lows = data
            print(f"✅ سعر الذهب: ${prices[-1]}")
            result = ai_analyze(prices, highs, lows)
            send_message(format_signal(result))
            print(f"✅ إشارة: {result['action']}")
        except Exception as e:
            print(f"خطأ: {e}")
            send_message(f"⚠️ خطأ: {str(e)}")
        time.sleep(INTERVAL_MIN * 60)

if __name__ == "__main__":
    main()
