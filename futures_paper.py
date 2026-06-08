import time
import requests
import pandas as pd
import json
import os

class FuturesPaperTrader:
    def __init__(self, initial_balance=100.0, state_file='futures_state.json'):
        self.state_file = state_file
        self.initial_balance = initial_balance
        self.load_state()
        print(f"--- Real-Time BTC Futures Paper Trading Started ---")
        print(f"Current Balance: ${self.balance:.2f}")
        if self.position:
            print(f"Restored Position: {self.position['side'].upper()} from ${self.position['entry']}")
        print("")

    def load_state(self):
        """Loads balance and position from a local JSON file to persist state across cron runs."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.balance = state.get('balance', self.initial_balance)
                    self.position = state.get('position', None)
            except Exception as e:
                print(f"Error loading state: {e}")
                self.balance = self.initial_balance
                self.position = None
        else:
            self.balance = self.initial_balance
            self.position = None

    def save_state(self):
        """Saves current balance and position to a local JSON file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump({
                    'balance': self.balance,
                    'position': self.position
                }, f)
        except Exception as e:
            print(f"Error saving state: {e}")

    def get_market_price(self):
        try:
            response = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
            data = response.json()
            return float(data['price'])
        except Exception as e:
            print(f"Error fetching price from Binance: {e}")
            return None

    def get_historical_klines(self, interval='15m', limit=200):
        try:
            response = requests.get(f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}")
            data = response.json()
            # Binance kline format: [OpenTime, Open, High, Low, Close, Volume, ...]
            df = pd.DataFrame(data, columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime', 'QuoteAssetVolume', 'NumberOfTrades', 'TakerBuyBaseAssetVolume', 'TakerBuyQuoteAssetVolume', 'Ignore'])
            df['Close'] = df['Close'].astype(float)
            df['High'] = df['High'].astype(float)
            df['Low'] = df['Low'].astype(float)
            return df
        except Exception as e:
            print(f"Error fetching klines from Binance: {e}")
            return pd.DataFrame()

    def calculate_indicators(self, df):
        if df.empty or len(df) < 200:
            return None, None, None
        
        # RSI (14)
        period = 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 0.001)
        rsi = 100 - (100 / (1 + rs))
        
        # 200 EMA for Trend Filtering
        ema200 = df['Close'].ewm(span=200, adjust=False).mean()
        
        # ATR (14) for Dynamic SL/TP
        high_low = df['High'] - df['Low']
        high_cp = (df['High'] - df['Close'].shift()).abs()
        low_cp = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()

        return rsi.iloc[-1], ema200.iloc[-1], atr.iloc[-1]

    def open_position(self, side, leverage, amount, price, atr):
        if self.position:
            return

        if amount > self.balance:
            print(f"Insufficient balance to open position. Needed: ${amount}, Have: ${self.balance:.2f}")
            return

        # ATR-based Dynamic Stop Loss and Take Profit
        # We use a 1.5x ATR Stop Loss and a 3.0x ATR Take Profit for a 1:2 Risk/Reward ratio.
        sl_dist = 1.5 * atr
        tp_dist = 3.0 * atr
        
        if side == 'long':
            tp_price = price + tp_dist
            sl_price = price - sl_dist
        else:
            tp_price = price - tp_dist
            sl_price = price + sl_dist

        self.balance -= amount
        self.position = {
            'side': side,
            'entry': price,
            'amount': amount,
            'leverage': leverage,
            'tp': tp_price,
            'sl': sl_price
        }
        self.save_state()
        print(f"OPEN {side.upper()} | Price: ${price} | Lev: {leverage}x | Margin: ${amount:.2f} | TP: ${tp_price:.2f} | SL: ${sl_price:.2f} | ATR: {atr:.2f}")

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
        
        # Liquidation check (100% loss of margin)
        if pnl_pct <= -1.0:
            print(f"LIQUIDATED at ${current_price}")
            self.position = None
            self.save_state()
            return

        hit_tp = (p['side'] == 'long' and current_price >= p['tp']) or (p['side'] == 'short' and current_price <= p['tp'])
        hit_sl = (p['side'] == 'long' and current_price <= p['sl']) or (p['side'] == 'short' and current_price >= p['sl'])

        if hit_tp or hit_sl:
            exit_reason = "TAKE PROFIT" if hit_tp else "STOP LOSS"
            final_payout = p['amount'] + pnl_amount
            self.balance += final_payout
            print(f"CLOSED via {exit_reason} | Price: ${current_price} | PnL: ${pnl_amount:.2f} | New Balance: ${self.balance:.2f}")
            self.position = None
            self.save_state()

    def trend_rsi_strategy(self):
        """
        Optimized Strategy:
        1. Trend Filter: Only trade in the direction of the 200 EMA (15m chart).
        2. Mean Reversion: Use RSI to find oversold/overbought entries within that trend.
        3. Risk Management: Use ATR for dynamic SL/TP and 10% equity position sizing.
        """
        if not self.position:
            df = self.get_historical_klines()
            rsi, ema200, atr = self.calculate_indicators(df)
            if rsi is None:
                print("Not enough data for indicators.")
                return
            
            price = df['Close'].iloc[-1]
            print(f"BTC: ${price:.2f} | RSI: {rsi:.2f} | EMA200: {ema200:.2f} | ATR: {atr:.2f}")
            
            # Entry Logic:
            # - Long: Price is above 200 EMA (Uptrend) AND RSI < 35 (Pullback)
            # - Short: Price is below 200 EMA (Downtrend) AND RSI > 65 (Pullback)
            
            if price > ema200 and rsi < 35:
                # Use 10% of balance as margin
                self.open_position('long', leverage=5, amount=self.balance * 0.1, price=price, atr=atr)
            elif price < ema200 and rsi > 65:
                self.open_position('short', leverage=5, amount=self.balance * 0.1, price=price, atr=atr)
        else:
            self.check_position()

if __name__ == "__main__":
    bot = FuturesPaperTrader(initial_balance=100.0)
    # The cron job executes this script every 15 minutes.
    bot.trend_rsi_strategy()
