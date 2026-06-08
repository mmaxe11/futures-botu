import time
import random
import requests
import pandas as pd
import numpy as np

class FuturesPaperTrader:
    def __init__(self, initial_balance=100.0):
        self.balance = initial_balance
        self.position = None  # None or {'side': 'long'/'short', 'entry': price, 'amount': amount, 'leverage': lev, 'tp': price, 'sl': price, 'trailing_sl': price}
        print(f"--- Real-Time BTC Futures Paper Trading Started ---")
        print(f"Initial Balance: ${self.balance:.2f}\n")

    def get_market_price(self):
        try:
            response = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
            data = response.json()
            return float(data['price'])
        except Exception as e:
            print(f"Error fetching price from Binance: {e}")
            return None

    def get_historical_klines(self, interval='15m', limit=50):
        try:
            response = requests.get(f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
            data = response.json()
            closes = [float(k[4]) for k in data]
            return closes
        except Exception as e:
            print(f"Error fetching {interval} klines from Binance: {e}")
            return []

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50
        series = pd.Series(prices)
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 0.001)
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    def get_macro_trend(self):
        """Checks the 4-hour trend using moving averages."""
        klines = self.get_historical_klines(interval='4h', limit=20)
        if len(klines) < 20:
            return "neutral"
        sma = np.mean(klines)
        current_price = klines[-1]
        if current_price > sma * 1.005:
            return "bullish"
        elif current_price < sma * 0.995:
            return "bearish"
        return "neutral"

    def open_position(self, side, leverage, amount, tp_pct=0.03, sl_pct=0.015):
        if self.position:
            return

        price = self.get_market_price()
        if not price:
            return
            
        if amount > self.balance:
            print(f"Insufficient balance to open position. Needed: ${amount}, Have: ${self.balance:.2f}")
            return

        self.balance -= amount
        
        tp_price = price * (1 + tp_pct) if side == 'long' else price * (1 - tp_pct)
        sl_price = price * (1 - sl_pct) if side == 'long' else price * (1 + sl_pct)

        self.position = {
            'side': side,
            'entry': price,
            'amount': amount,
            'leverage': leverage,
            'tp': tp_price,
            'sl': sl_price,
            'trailing_sl': sl_price, # Initial trailing stop is same as SL
            'high_water_mark': price if side == 'long' else price
        }
        print(f"OPEN {side.upper()} | Price: ${price} | Lev: {leverage}x | Margin: ${amount} | TP: ${tp_price:.2f} | SL: ${sl_price:.2f}")

    def check_position(self):
        if not self.position:
            return

        current_price = self.get_market_price()
        if not current_price:
            return

        p = self.position
        price_diff_pct = (current_price - p['entry']) / p['entry']
        if p['side'] == 'short':
            price_diff_pct = -price_diff_pct
            
        pnl_pct = price_diff_pct * p['leverage']
        pnl_amount = p['amount'] * pnl_pct
        
        # Trailing Stop-Loss Logic (locks in profits)
        if p['side'] == 'long':
            if current_price > p['high_water_mark']:
                p['high_water_mark'] = current_price
                new_trailing = current_price * 0.99
                if new_trailing > p['trailing_sl']:
                    p['trailing_sl'] = new_trailing
        else: # short
            if current_price < p['high_water_mark']:
                p['high_water_mark'] = current_price
                new_trailing = current_price * 1.01
                if new_trailing < p['trailing_sl']:
                    p['trailing_sl'] = new_trailing

        if pnl_pct <= -1.0:
            print(f"LIQUIDATED at ${current_price}")
            self.position = None
            return

        hit_tp = (p['side'] == 'long' and current_price >= p['tp']) or (p['side'] == 'short' and current_price <= p['tp'])
        hit_sl = (p['side'] == 'long' and current_price <= p['trailing_sl']) or (p['side'] == 'short' and current_price >= p['trailing_sl'])

        if hit_tp or hit_sl:
            exit_reason = "TAKE PROFIT" if hit_tp else "TRAILING STOP LOSS"
            final_payout = p['amount'] + pnl_amount
            self.balance += final_payout
            print(f"CLOSED via {exit_reason} | Price: ${current_price} | PnL: ${pnl_amount:.2f} | New Balance: ${self.balance:.2f}")
            self.position = None

    def rsi_strategy(self):
        """Advanced RSI strategy with Multi-Timeframe filter and Dynamic Leverage."""
        if not self.position:
            macro = self.get_macro_trend()
            klines = self.get_historical_klines(interval='15m')
            rsi = self.calculate_rsi(klines)
            print(f"BTC Analysis | 15m RSI: {rsi:.2f} | 4h Trend: {macro} | Price: {klines[-1] if klines else 'N/A'}")
            
            leverage = 10 if macro != "neutral" else 5
            
            if rsi < 30 and macro != "bearish":
                self.open_position('long', leverage=leverage, amount=10)
            elif rsi > 70 and macro != "bullish":
                self.open_position('short', leverage=leverage, amount=10)
        else:
            self.check_position()

if __name__ == "__main__":
    bot = FuturesPaperTrader(initial_balance=100.0)
    for i in range(5):
        bot.rsi_strategy()
        time.sleep(1)
