# -*- coding: utf-8 -*-
"""
Binance Trading Bot - MULTI-COIN + Dashboard
Supporta più crypto contemporaneamente
"""

import os
import time
import json
import logging
import pandas as pd
import pandas_ta as ta
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv
from datetime import datetime
import sys

# --- CONFIGURAZIONE ---
load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')

# 🔥 LISTA CRYPTO DA TRADARE (puoi aggiungerne altre!)
TRADING_PAIRS = [
    'BTCUSDT',
    'ETHUSDT',
    'SOLUSDT',
    'XRPUSDT',
    'DOGEUSDT',
    'ADAUSDT',
    'AVAXUSDT',
    'MATICUSDT',
    'LINKUSDT',
    'DOTUSDT',
]

QUOTE_ASSET = 'USDT'
INTERVAL = '5m'
SLEEP_TIME = 60  # Controllo ogni 60s per multi-coin

# Strategia
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 40
RSI_SELL_THRESHOLD = 65
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
EMA_SHORT = 9
EMA_LONG = 21
RISK_PER_TRADE = 0.10  # 10% per coin (diversificato)
STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04
TRAILING_STOP_PCT = 0.025
VOLUME_SPIKE_MULT = 1.5

PAPER_TRADING = False

STATUS_FILE = '/root/.openclaw/workspace/bot_status.json'
MULTI_STATUS_FILE = '/root/.openclaw/workspace/multi_status.json'
HISTORY_FILE = '/root/.openclaw/workspace/trade_history.json'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot_multi.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

client = None

# Stato per ogni coin
coin_states = {}

class CoinState:
    def __init__(self, symbol):
        self.symbol = symbol
        self.in_position = False
        self.entry_price = 0.0
        self.position_quantity = 0.0
        self.highest_price = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        self.last_signal = "WAITING"
        self.buy_score = 0
        self.indicators = {}
        self.candle = {}

def init_client():
    global client
    if not API_KEY or not API_SECRET:
        logger.error("Chiavi API mancanti!")
        sys.exit(1)
    
    if PAPER_TRADING:
        client = Client(API_KEY, API_SECRET, testnet=True)
        logger.info("🔧 PAPER TRADING")
    else:
        client = Client(API_KEY, API_SECRET)
        logger.info("💰 LIVE TRADING")
    
    client.ping()
    logger.info("✅ Connessione OK")
    
    # Inizializza stato per ogni coin
    for pair in TRADING_PAIRS:
        coin_states[pair] = CoinState(pair)

def get_data(symbol, interval='5m', limit=100):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            'ts', 'open', 'high', 'low', 'close', 'volume',
            'close_ts', 'quote_vol', 'trades', 'taker_buy', 'taker_quote', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e:
        logger.error(f"Errore {symbol}: {e}")
        return None

def calc_indicators(df):
    df['rsi'] = ta.rsi(df['close'], length=RSI_PERIOD)
    macd = ta.macd(df['close'], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    df['macd'] = macd['MACD_12_26_9']
    df['macd_signal'] = macd['MACDs_12_26_9']
    df['macd_hist'] = macd['MACDh_12_26_9']
    df['ema_short'] = ta.ema(df['close'], length=EMA_SHORT)
    df['ema_long'] = ta.ema(df['close'], length=EMA_LONG)
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['vol_spike'] = df['volume'] > (df['vol_ma'] * VOLUME_SPIKE_MULT)
    return df

def analyze_coin(symbol, df):
    """Analizza una coin e restituisce segnale + indicatori"""
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    price = latest['close']
    
    state = coin_states[symbol]
    
    # Calcola segnali
    signals = {
        "rsi_buy": bool(latest['rsi'] < RSI_BUY_THRESHOLD),
        "macd_bullish": bool(latest['macd'] > latest['macd_signal']),
        "macd_hist_positive": bool(latest['macd_hist'] > 0),
        "price_above_ema": bool(price > latest['ema_short']),
        "volume_spike": bool(latest['vol_spike']) if 'vol_spike' in latest else False,
    }
    
    buy_score = sum([
        signals["rsi_buy"],
        signals["macd_bullish"] or signals["macd_hist_positive"],
        signals["price_above_ema"],
        signals["volume_spike"]
    ])
    
    state.buy_score = buy_score
    
    # Salva indicatori
    state.indicators = {
        "rsi": round(latest['rsi'], 2),
        "macd": round(latest['macd_hist'], 2),
        "ema_short": round(latest['ema_short'], 2),
        "ema_long": round(latest['ema_long'], 2),
        "volume_spike": signals["volume_spike"],
    }
    
    # Salva candela
    state.candle = {
        "open": round(latest['open'], 2),
        "high": round(latest['high'], 2),
        "low": round(latest['low'], 2),
        "close": round(latest['close'], 2),
        "volume": round(latest['volume'], 4),
        "is_green": bool(latest['close'] > latest['open']),
    }
    
    # Segnale BUY?
    if buy_score >= 3 and not state.in_position:
        return "BUY", price
    elif buy_score <= 1 and state.in_position:
        return "SELL_WEAK", price
    
    return "WAITING", price

def check_sell_signal(symbol, price):
    state = coin_states[symbol]
    
    if price > state.highest_price:
        state.highest_price = price
    
    tp_price = state.entry_price * (1 + TAKE_PROFIT_PCT)
    if price >= tp_price:
        return True, "TP"
    
    sl_price = state.entry_price * (1 - STOP_LOSS_PCT)
    if price <= sl_price:
        return True, "SL"
    
    trailing_sl = state.highest_price * (1 - TRAILING_STOP_PCT)
    if price <= trailing_sl and state.highest_price > state.entry_price:
        return True, "TRAIL"
    
    return False, None

def place_order(symbol, side, quantity, price):
    try:
        if PAPER_TRADING:
            logger.info(f"📝 [PAPER] {side} {quantity} {symbol} @ {price}")
            return {'orderId': int(time.time()*1000), 'quantity': quantity, 'price': price}
        else:
            order = client.create_order(
                symbol=symbol, side=side, type='LIMIT',
                timeInForce='GTC', quantity=f"{quantity:.8f}", price=f"{price:.8f}"
            )
            logger.info(f"✅ {side} {symbol}: {order['orderId']}")
            return order
    except Exception as e:
        logger.error(f"❌ Errore {symbol}: {e}")
        return None

def get_balance(asset):
    try:
        b = client.get_asset_balance(asset=asset)
        return float(b['free']) if b else 0.0
    except:
        return 0.0

def update_dashboard(all_coins_data):
    """Aggiorna il file JSON multi-coin"""
    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "LIVE" if not PAPER_TRADING else "PAPER",
        "total_pairs": len(TRADING_PAIRS),
        "coins": {}
    }
    
    for symbol, coin_data in all_coins_data.items():
        state = coin_states[symbol]
        data["coins"][symbol] = {
            "price": coin_data.get("price", 0),
            "signal": coin_data.get("signal", "WAITING"),
            "buy_score": state.buy_score,
            "buy_score_pct": round((state.buy_score / 4) * 100),
            "rsi": state.indicators.get("rsi", 0),
            "macd": state.indicators.get("macd", 0),
            "ema_short": state.indicators.get("ema_short", 0),
            "ema_long": state.indicators.get("ema_long", 0),
            "volume_spike": state.indicators.get("volume_spike", False),
            "in_position": state.in_position,
            "entry_price": state.entry_price,
            "quantity": state.position_quantity,
            "unrealized_pnl": round((coin_data.get("price", 0) - state.entry_price) * state.position_quantity, 4) if state.in_position else 0,
            "tp_price": round(state.entry_price * (1 + TAKE_PROFIT_PCT), 2) if state.in_position else 0,
            "sl_price": round(state.entry_price * (1 - STOP_LOSS_PCT), 2) if state.in_position else 0,
            "total_trades": state.total_trades,
            "win_rate": round((state.winning_trades / state.total_trades * 100), 1) if state.total_trades > 0 else 0,
            "total_pnl": round(state.total_pnl, 4),
            "candle": state.candle
        }
    
    with open(MULTI_STATUS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Aggiorna anche il file principale con la prima coin con segnale buy
    primary_data = None
    for symbol in TRADING_PAIRS:
        if all_coins_data.get(symbol, {}).get("signal") in ["BUY", "SELL", "SELL_WEAK"]:
            primary_data = all_coins_data[symbol]
            break
    
    if primary_data:
        with open(STATUS_FILE, 'w') as f:
            json.dump(primary_data, f, indent=2)

def add_trade_to_history(trade):
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            try:
                history = json.load(f)
            except:
                history = []
    history.insert(0, trade)
    history = history[:100]
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def main():
    logger.info("="*60)
    logger.info(f"🚀 MULTI-COIN BOT - {len(TRADING_PAIRS)} CRYPTO")
    logger.info(f"Coins: {', '.join(TRADING_PAIRS)}")
    logger.info(f"Risk: {RISK_PER_TRADE*100}% per coin")
    logger.info("="*60)
    
    init_client()
    
    while True:
        try:
            all_coins_data = {}
            
            for symbol in TRADING_PAIRS:
                try:
                    df = get_data(symbol, INTERVAL, 100)
                    if df is None:
                        continue
                    
                    df = calc_indicators(df)
                    signal, price = analyze_coin(symbol, df)
                    state = coin_states[symbol]
                    
                    all_coins_data[symbol] = {
                        "signal": signal,
                        "price": price
                    }
                    
                    # Esegui trade se necessario
                    if signal == "BUY" and not state.in_position:
                        balance = get_balance(QUOTE_ASSET)
                        qty = (balance * RISK_PER_TRADE) / price
                        if qty * price > 5:
                            order = place_order(symbol, SIDE_BUY, qty, price)
                            if order:
                                state.in_position = True
                                state.entry_price = price
                                state.position_quantity = qty
                                state.highest_price = price
                                logger.info(f"🟢 BUY {symbol}: {qty:.6f} @ ${price:.2f}")
                    
                    elif state.in_position:
                        if price > state.highest_price:
                            state.highest_price = price
                        
                        sell, reason = check_sell_signal(symbol, price)
                        if sell:
                            order = place_order(symbol, SIDE_SELL, state.position_quantity, price)
                            if order:
                                pnl = (price - state.entry_price) * state.position_quantity
                                pct = ((price - state.entry_price) / state.entry_price) * 100
                                state.total_trades += 1
                                if pnl > 0:
                                    state.winning_trades += 1
                                state.total_pnl += pnl
                                
                                add_trade_to_history({
                                    "type": "SELL",
                                    "symbol": symbol,
                                    "reason": reason,
                                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "entry_price": round(state.entry_price, 2),
                                    "exit_price": round(price, 2),
                                    "quantity": round(state.position_quantity, 8),
                                    "pnl": round(pnl, 4),
                                    "pnl_pct": round(pct, 2)
                                })
                                
                                logger.info(f"🔴 SELL {symbol} ({reason}): PnL={pnl:.4f} ({pct:+.2f}%)")
                                state.in_position = False
                                state.entry_price = 0
                                state.position_quantity = 0
                                state.highest_price = 0
                        
                        elif signal == "SELL_WEAK" and reason is None:
                            # Forza vendita se segnale ribassista
                            pass
                    
                    # Log sintetico
                    pos = "📊" if state.in_position else "⏳"
                    emoji = "🟢" if signal == "BUY" else ("🔴" if signal in ["SELL", "SELL_WEAK"] else "⚪")
                    logger.info(f"{emoji} {symbol}: ${price:.2f} | RSI:{state.indicators['rsi']:.0f} | Score:{state.buy_score}/4 {pos}")
                    
                except Exception as e:
                    logger.error(f"Errore {symbol}: {e}")
            
            # Aggiorna dashboard
            update_dashboard(all_coins_data)
            
            time.sleep(SLEEP_TIME)
            
        except KeyboardInterrupt:
            logger.info("🛑 Fermato")
            sys.exit(0)
        except Exception as e:
            logger.error(f"❌ Errore globale: {e}")
            time.sleep(SLEEP_TIME)

if __name__ == "__main__":
    main()
