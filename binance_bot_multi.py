#!/usr/bin/env python3
"""
Binance Multi-Coin Trading Bot - VERSIONE COMPLETA
Con dashboard dettagliata e indicators avanzati
"""

import os
import time
import json
import logging
import pandas as pd
import pandas_ta as ta
from binance.client import Client
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys

# --- CONFIGURAZIONE ---
load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')

TRADING_PAIRS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT',
    'ADAUSDT', 'AVAXUSDT', 'MATICUSDT', 'LINKUSDT', 'DOTUSDT',
    'UNIUSDT', 'AAVEUSDT', 'LTCUSDT', 'ATOMUSDT', 'FILUSDT',
]

QUOTE_ASSET = 'USDT'
INTERVAL = '5m'
SLEEP_TIME = 45

# Indicatori
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 40
RSI_SELL_THRESHOLD = 65
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
STOCH_PERIOD = 14
BB_PERIOD = 20
ATR_PERIOD = 14

RISK_PER_TRADE = 0.10
STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04
TRAILING_STOP_PCT = 0.025
VOLUME_SPIKE_MULT = 1.5

PAPER_TRADING = False

STATUS_FILE = '/root/.openclaw/workspace/multi_status.json'
HISTORY_FILE = '/root/.openclaw/workspace/trade_history.json'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s',
                   handlers=[logging.FileHandler('trading_bot.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

client = None
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
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.best_trade = 0.0
        self.worst_trade = 0.0
        self.avg_win = 0.0
        self.avg_loss = 0.0
        self.price_history = []
        self.last_update = None

def init_client():
    global client
    client = Client(API_KEY, API_SECRET) if not PAPER_TRADING else Client(API_KEY, API_SECRET, testnet=True)
    client.ping()
    logger.info(f"✅ Connesso - Modalità: {'PAPER' if PAPER_TRADING else 'LIVE'}")
    for pair in TRADING_PAIRS:
        coin_states[pair] = CoinState(pair)

def get_data(symbol, limit=100):
    try:
        klines = client.get_klines(symbol=symbol, interval=INTERVAL, limit=limit)
        df = pd.DataFrame(klines, columns=['ts', 'open', 'high', 'low', 'close', 'volume',
                                           'close_ts', 'quote_vol', 'trades', 'taker_buy', 'taker_quote', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e:
        logger.error(f"Errore dati {symbol}: {e}")
        return None

def calc_all_indicators(df):
    """Calcola TUTTI gli indicatori tecnici"""
    
    # Trend Indicators
    df['rsi'] = ta.rsi(df['close'], length=RSI_PERIOD)
    df['rsi_sma'] = ta.sma(df['rsi'], length=10)  # RSI smoothed
    
    macd = ta.macd(df['close'], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    df['macd'] = macd['MACD_12_26_9']
    df['macd_signal'] = macd['MACDs_12_26_9']
    df['macd_hist'] = macd['MACDh_12_26_9']
    
    df['ema_fast'] = ta.ema(df['close'], length=EMA_FAST)
    df['ema_mid'] = ta.ema(df['close'], length=EMA_MID)
    df['ema_slow'] = ta.ema(df['close'], length=EMA_SLOW)
    
    # Stochastic
    stoch = ta.stoch(df['high'], df['low'], df['close'], length=STOCH_PERIOD)
    df['stoch_k'] = stoch['STOCHk_14_3_3']
    df['stoch_d'] = stoch['STOCHd_14_3_3']
    
    # Bollinger Bands
    bb = ta.bbands(df['close'], length=BB_PERIOD)
    bb_cols = bb.columns.tolist()
    df['bb_upper'] = bb[[c for c in bb_cols if c.startswith('BBU')][0]]
    df['bb_mid'] = bb[[c for c in bb_cols if c.startswith('BBM')][0]]
    df['bb_lower'] = bb[[c for c in bb_cols if c.startswith('BBL')][0]]
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid'] * 100
    
    # ATR (Average True Range) - Volatilità
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=ATR_PERIOD)
    df['atr_pct'] = df['atr'] / df['close'] * 100
    
    # Volume Analysis
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['vol_ma_short'] = df['volume'].rolling(5).mean()
    df['vol_spike'] = df['volume'] > (df['vol_ma'] * VOLUME_SPIKE_MULT)
    df['vol_ratio'] = df['volume'] / df['vol_ma']
    
    # Price Action
    df['price_change'] = df['close'].pct_change() * 100
    df['price_change_5'] = df['close'].pct_change(5) * 100
    df['high_low_pct'] = (df['high'] - df['low']) / df['close'] * 100
    
    # Support/Resistance levels
    df['pivot'] = (df['high'].shift(1) + df['low'].shift(1) + df['close'].shift(1)) / 3
    df['resistance1'] = 2 * df['pivot'] - df['low'].shift(1)
    df['support1'] = 2 * df['pivot'] - df['high'].shift(1)
    
    # Momentum
    df['momentum'] = ta.mom(df['close'], length=10)
    df['roc'] = ta.roc(df['close'], length=10)
    
    # Trend Strength
    df['adx'] = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14']
    
    return df

def analyze_coin(symbol, df):
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    prev2 = df.iloc[-3] if len(df) > 2 else prev
    state = coin_states[symbol]
    price = latest['close']
    
    # Aggiorna storico prezzi
    state.price_history.append({
        'time': datetime.now().strftime('%H:%M'),
        'price': round(price, 2),
        'rsi': round(latest['rsi'], 1),
        'volume': round(latest['volume'], 2)
    })
    if len(state.price_history) > 100:
        state.price_history = state.price_history[-100:]
    
    # Segnali dettagliati
    signals = {
        'rsi_buy': bool(latest['rsi'] < RSI_BUY_THRESHOLD),
        'rsi_sell': bool(latest['rsi'] > RSI_SELL_THRESHOLD),
        'macd_bullish': bool(latest['macd'] > latest['macd_signal']),
        'macd_cross_up': bool(latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']),
        'macd_cross_down': bool(latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']),
        'ema_bullish': bool(latest['ema_fast'] > latest['ema_mid'] > latest['ema_slow']),
        'ema_bearish': bool(latest['ema_fast'] < latest['ema_mid'] < latest['ema_slow']),
        'price_above_ema': bool(price > latest['ema_fast']),
        'stoch_oversold': bool(latest['stoch_k'] < 20),
        'stoch_overbought': bool(latest['stoch_k'] > 80),
        'bb_lower_touch': bool(price <= latest['bb_lower'] * 1.01),
        'bb_upper_touch': bool(price >= latest['bb_upper'] * 0.99),
        'volume_spike': bool(latest['vol_spike']),
        'high_volatility': bool(latest['atr_pct'] > 2),
        'strong_trend': bool(latest['adx'] > 25),
    }
    
    # Score complessivo
    buy_score = sum([
        signals['rsi_buy'],
        signals['macd_bullish'] or signals['macd_cross_up'],
        signals['ema_bullish'],
        signals['price_above_ema'],
        signals['stoch_oversold'],
        signals['bb_lower_touch'],
        signals['volume_spike'],
    ])
    
    sell_score = sum([
        signals['rsi_sell'],
        signals['macd_cross_down'],
        signals['ema_bearish'],
        signals['stoch_overbought'],
        signals['bb_upper_touch'],
    ])
    
    # Determina segnale
    if buy_score >= 4 and not state.in_position:
        signal = "STRONG_BUY"
    elif buy_score >= 3 and not state.in_position:
        signal = "BUY"
    elif sell_score >= 3 and state.in_position:
        signal = "STRONG_SELL"
    elif sell_score >= 2 and state.in_position:
        signal = "SELL"
    else:
        signal = "NEUTRAL"
    
    return {
        'signal': signal,
        'price': price,
        'buy_score': buy_score,
        'sell_score': sell_score,
        'signals': signals,
        'indicators': {
            'rsi': round(latest['rsi'], 2),
            'rsi_sma': round(latest['rsi_sma'], 2),
            'macd': round(latest['macd'], 4),
            'macd_signal': round(latest['macd_signal'], 4),
            'macd_hist': round(latest['macd_hist'], 4),
            'stoch_k': round(latest['stoch_k'], 2),
            'stoch_d': round(latest['stoch_d'], 2),
            'ema_fast': round(latest['ema_fast'], 2),
            'ema_mid': round(latest['ema_mid'], 2),
            'ema_slow': round(latest['ema_slow'], 2),
            'bb_upper': round(latest['bb_upper'], 2),
            'bb_mid': round(latest['bb_mid'], 2),
            'bb_lower': round(latest['bb_lower'], 2),
            'bb_width': round(latest['bb_width'], 3),
            'atr': round(latest['atr'], 4),
            'atr_pct': round(latest['atr_pct'], 3),
            'adx': round(latest['adx'], 2),
            'momentum': round(latest['momentum'], 4),
            'roc': round(latest['roc'], 3),
        },
        'volume': {
            'current': round(latest['volume'], 4),
            'avg_20': round(latest['vol_ma'], 4),
            'avg_5': round(latest['vol_ma_short'], 4),
            'ratio': round(latest['vol_ratio'], 2),
            'spike': bool(latest['vol_spike']),
        },
        'price_data': {
            'open': round(latest['open'], 2),
            'high': round(latest['high'], 2),
            'low': round(latest['low'], 2),
            'close': round(latest['close'], 2),
            'change_1': round(latest['price_change'], 3) if pd.notna(latest['price_change']) else 0,
            'change_5': round(latest['price_change_5'], 3) if pd.notna(latest['price_change_5']) else 0,
            'volatility': round(latest['high_low_pct'], 3),
            'is_green': bool(latest['close'] > latest['open']),
        },
        'levels': {
            'pivot': round(latest['pivot'], 2),
            'resistance1': round(latest['resistance1'], 2),
            'support1': round(latest['support1'], 2),
        }
    }

def update_dashboard(all_data):
    """Aggiorna JSON con tutti i dati"""
    
    # Calcola statistiche globali
    total_positions = sum(1 for s in coin_states.values() if s.in_position)
    total_pnl = sum(s.total_pnl for s in coin_states.values())
    total_trades = sum(s.total_trades for s in coin_states.values())
    total_wins = sum(s.winning_trades for s in coin_states.values())
    
    buy_signals = sum(1 for d in all_data.values() if d['signal'] in ['BUY', 'STRONG_BUY'])
    sell_signals = sum(1 for d in all_data.values() if d['signal'] in ['SELL', 'STRONG_SELL'])
    
    # Top performers
    sorted_by_score = sorted(all_data.items(), key=lambda x: x[1]['buy_score'], reverse=True)
    top_buys = [{'symbol': k, 'score': v['buy_score'], 'rsi': v['indicators']['rsi']} 
                for k, v in sorted_by_score[:3] if v['signal'] in ['BUY', 'STRONG_BUY']]
    
    data = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'mode': 'LIVE' if not PAPER_TRADING else 'PAPER',
        'summary': {
            'total_coins': len(TRADING_PAIRS),
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'neutral': len(TRADING_PAIRS) - buy_signals - sell_signals,
            'active_positions': total_positions,
            'total_trades': total_trades,
            'total_wins': total_wins,
            'total_losses': total_trades - total_wins,
            'win_rate': round((total_wins / total_trades * 100), 1) if total_trades > 0 else 0,
            'total_pnl': round(total_pnl, 4),
            'top_buys': top_buys,
        },
        'coins': {}
    }
    
    for symbol, analysis in all_data.items():
        state = coin_states[symbol]
        
        data['coins'][symbol] = {
            **analysis,
            'position': {
                'active': state.in_position,
                'entry_price': state.entry_price,
                'quantity': state.position_quantity,
                'current_value': round(state.position_quantity * analysis['price'], 2) if state.in_position else 0,
                'unrealized_pnl': round((analysis['price'] - state.entry_price) * state.position_quantity, 4) if state.in_position else 0,
                'unrealized_pnl_pct': round(((analysis['price'] - state.entry_price) / state.entry_price) * 100, 2) if state.in_position else 0,
                'highest_price': state.highest_price,
                'tp_price': round(state.entry_price * (1 + TAKE_PROFIT_PCT), 2) if state.in_position else 0,
                'sl_price': round(state.entry_price * (1 - STOP_LOSS_PCT), 2) if state.in_position else 0,
                'trailing_sl': round(state.highest_price * (1 - TRAILING_STOP_PCT), 2) if state.in_position and state.highest_price > 0 else 0,
                'distance_to_tp': round(((state.entry_price * (1 + TAKE_PROFIT_PCT) - analysis['price']) / analysis['price']) * 100, 2) if state.in_position else 0,
                'distance_to_sl': round(((analysis['price'] - state.entry_price * (1 - STOP_LOSS_PCT)) / analysis['price']) * 100, 2) if state.in_position else 0,
            },
            'stats': {
                'total_trades': state.total_trades,
                'wins': state.winning_trades,
                'losses': state.losing_trades,
                'win_rate': round((state.winning_trades / state.total_trades * 100), 1) if state.total_trades > 0 else 0,
                'total_pnl': round(state.total_pnl, 4),
                'best_trade': round(state.best_trade, 4),
                'worst_trade': round(state.worst_trade, 4),
            },
            'price_history': state.price_history[-50:],  # Ultimi 50 punti
        }
    
    with open(STATUS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def main():
    logger.info("="*60)
    logger.info(f"🚀 MULTI-COIN BOT COMPLETO - {len(TRADING_PAIRS)} CRYPTO")
    logger.info("="*60)
    
    init_client()
    
    while True:
        try:
            all_data = {}
            
            for symbol in TRADING_PAIRS:
                try:
                    df = get_data(symbol, 100)
                    if df is None:
                        continue
                    
                    df = calc_all_indicators(df)
                    analysis = analyze_coin(symbol, df)
                    state = coin_states[symbol]
                    state.last_update = datetime.now().isoformat()
                    
                    all_data[symbol] = analysis
                    
                    # Esegui trade
                    price = analysis['price']
                    
                    if analysis['signal'] in ['BUY', 'STRONG_BUY'] and not state.in_position:
                        balance = float(client.get_asset_balance(asset=QUOTE_ASSET)['free']) if not PAPER_TRADING else 100
                        qty = (balance * RISK_PER_TRADE) / price
                        if qty * price > 5:
                            if PAPER_TRADING:
                                logger.info(f"📝 [PAPER] BUY {symbol} @ ${price:.2f}")
                                state.in_position = True
                                state.entry_price = price
                                state.position_quantity = qty
                                state.highest_price = price
                            else:
                                try:
                                    order = client.create_order(symbol=symbol, side='BUY', type='MARKET', quantity=f"{qty:.8f}")
                                    state.in_position = True
                                    state.entry_price = price
                                    state.position_quantity = qty
                                    state.highest_price = price
                                    logger.info(f"🟢 BUY {symbol}: {qty:.6f} @ ${price:.2f}")
                                except Exception as e:
                                    logger.error(f"❌ Errore BUY {symbol}: {e}")
                    
                    elif state.in_position:
                        if price > state.highest_price:
                            state.highest_price = price
                        
                        # Check exit conditions
                        should_sell = False
                        sell_reason = ""
                        
                        tp = state.entry_price * (1 + TAKE_PROFIT_PCT)
                        sl = state.entry_price * (1 - STOP_LOSS_PCT)
                        trail = state.highest_price * (1 - TRAILING_STOP_PCT)
                        
                        if price >= tp:
                            should_sell, sell_reason = True, "TAKE_PROFIT"
                        elif price <= sl:
                            should_sell, sell_reason = True, "STOP_LOSS"
                        elif price <= trail and state.highest_price > state.entry_price * 1.01:
                            should_sell, sell_reason = True, "TRAILING_STOP"
                        elif analysis['signal'] in ['STRONG_SELL']:
                            should_sell, sell_reason = True, "SIGNAL_SELL"
                        
                        if should_sell:
                            pnl = (price - state.entry_price) * state.position_quantity
                            pct = ((price - state.entry_price) / state.entry_price) * 100
                            
                            if not PAPER_TRADING:
                                try:
                                    client.create_order(symbol=symbol, side='SELL', type='MARKET', quantity=f"{state.position_quantity:.8f}")
                                except Exception as e:
                                    logger.error(f"❌ Errore SELL {symbol}: {e}")
                            
                            state.total_trades += 1
                            if pnl > 0:
                                state.winning_trades += 1
                                state.best_trade = max(state.best_trade, pnl)
                            else:
                                state.losing_trades += 1
                                state.worst_trade = min(state.worst_trade, pnl)
                            state.total_pnl += pnl
                            
                            logger.info(f"🔴 SELL {symbol} ({sell_reason}): PnL={pnl:.4f} ({pct:+.2f}%)")
                            
                            state.in_position = False
                            state.entry_price = 0
                            state.position_quantity = 0
                            state.highest_price = 0
                    
                    # Log sintetico
                    emoji = "🟢" if 'BUY' in analysis['signal'] else ("🔴" if 'SELL' in analysis['signal'] else "⚪")
                    pos = "📍" if state.in_position else ""
                    logger.info(f"{emoji} {symbol}: ${price:.2f} | RSI:{analysis['indicators']['rsi']:.0f} | Score:{analysis['buy_score']}/7 {pos}")
                    
                except Exception as e:
                    logger.error(f"Errore {symbol}: {e}")
            
            update_dashboard(all_data)
            time.sleep(SLEEP_TIME)
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot fermato")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Errore: {e}")
            time.sleep(SLEEP_TIME)

if __name__ == "__main__":
    main()
