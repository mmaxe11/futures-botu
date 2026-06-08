import time
import random

class FuturesPaperTrader:
    def __init__(self, initial_balance=100.0):
        self.balance = initial_balance
        self.position = None  # None or {'type': 'long'/'short', 'entry': price, 'size': amount, 'leverage': lev, 'tp': price, 'sl': price}
        self.history = []
        print(f"--- Paper Trading Started ---")
        print(f"Initial Balance: ${self.balance:.2f}\n")

    def get_market_price(self):
        # Simulating market price for demonstration
        return round(random.uniform(20000, 60000), 2)

    def open_position(self, side, leverage, amount, tp_pct=0.05, sl_pct=0.02):
        if self.position:
            print("Position already open.")
            return

        price = self.get_market_price()
        if amount > self.balance:
            print("Insufficient balance.")
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
        p = self.position
        
        # Calculate PnL
        price_diff_pct = (current_price - p['entry']) / p['entry']
        if p['side'] == 'short':
            price_diff_pct = -price_diff_pct
            
        pnl_pct = price_diff_pct * p['leverage']
        pnl_amount = p['amount'] * pnl_pct
        
        # Check Liquidation (Simplified: 100% loss of margin)
        if pnl_pct <= -1.0:
            print(f"LIQUIDATED at ${current_price}")
            self.position = None
            return

        # Check TP/SL
        hit_tp = (p['side'] == 'long' and current_price >= p['tp']) or (p['side'] == 'short' and current_price <= p['tp'])
        hit_sl = (p['side'] == 'long' and current_price <= p['sl']) or (p['side'] == 'short' and current_price >= p['sl'])

        if hit_tp or hit_sl:
            exit_reason = "TAKE PROFIT" if hit_tp else "STOP LOSS"
            final_payout = p['amount'] + pnl_amount
            self.balance += final_payout
            print(f"CLOSED via {exit_reason} | Price: ${current_price} | PnL: ${pnl_amount:.2f} | New Balance: ${self.balance:.2f}")
            self.position = None

    def simple_strategy(self):
        # Dummy strategy: Randomly enter if no position
        if not self.position:
            side = random.choice(['long', 'short'])
            self.open_position(side, leverage=10, amount=10)
        else:
            self.check_position()

if __name__ == "__main__":
    bot = FuturesPaperTrader(initial_balance=100.0)
    for i in range(10):
        print(f"Tick {i+1}...")
        bot.simple_strategy()
        time.sleep(1)
