import time
import random
import requests
import pandas as pd

class FuturesPaperTrader:
    def __init__(self, initial_balance=100.0):
        self.balance = initial_balance
        self.position = None  # None or {'side': 'long'/'short', 'entry': price, 'amount': amount, 'leverage': lev, 'tp': price, 'sl': price}
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

    def get_historical_klines(self):
        try:
            # Fetch 50 most recent 15m candles
            response = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=50")
            data = response.json()
            # [4] is the 'Close' price
            closes = [float(k[4]) for k in data]
            return closes
        except Exception as e:
            print(f"Error fetching klines from Binance: {e}")
            return []

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50
        
        series = pd.Series(prices)
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # Avoid division by zero
        rs = gain / loss.replace(0, 0.001)
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    def open_position(self, side, leverage, amount, tp_pct=0.05, sl_pct=0.02):
        if self.position:
            return

        price = self.get_market_price()
        if not price:
            print("Could not fetch price to open position.")
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
            'sl': sl_price
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
        
        # Simple liquidation check (100% loss of margin)
        if pnl_pct <= -1.0:
            print(f"LIQUIDATED at ${current_price}")
            self.position = None
            return

        hit_tp = (p['side'] == 'long' and current_price >= p['tp']) or (p['side'] == 'short' and current_price <= p['tp'])
        hit_sl = (p['side'] == 'long' and current_price <= p['sl']) or (p['side'] == 'short' and current_price >= p['sl'])

        if hit_tp or hit_sl:
            exit_reason = "TAKE PROFIT" if hit_tp else "STOP LOSS"
            final_payout = p['amount'] + pnl_amount
            self.balance += final_payout
            print(f"CLOSED via {exit_reason} | Price: ${current_price} | PnL: ${pnl_amount:.2f} | New Balance: ${self.balance:.2f}")
            self.position = None

    def rsi_strategy(self):
        """Simple RSI strategy using 15m klines."""
        if not self.position:
            klines = self.get_historical_klines()
            rsi = self.calculate_rsi(klines)
            print(f"Current BTC RSI (15m): {rsi:.2f} | Price: {klines[-1] if klines else 'N/A'}")
            
            # Simple RSI signals: Oversold < 30 (Long), Overbought > 70 (Short)
            if rsi < 30:
                self.open_position('long', leverage=10, amount=10)
            elif rsi > 70:
                self.open_position('short', leverage=10, amount=10)
        else:
            self.check_position()

if __name__ == "__main__":
    bot = FuturesPaperTrader(initial_balance=100.0)
    # Loop for 5 iterations as a baseline test
    for i in range(5):
        bot.rsi_strategy()
        time.sleep(1)
