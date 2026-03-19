# 🤖 Binance Trading Bot Multi-Coin

Bot di trading automatico per Binance Spot con strategia multi-indicator e supporto multi-coin.

## 🚀 Caratteristiche

### Strategie di Trading
- **RSI (Relative Index Strength)** - Rileva ipercomprato/ipervenduto
- **MACD (Moving Average Convergence Divergence)** - Conferma trend
- **EMA (Exponential Moving Average)** - Analisi trend a breve/lungo termine
- **Volume Spike** - Rileva movimenti anomali di volume

### Modalità
1. **Single Coin** (`binance_bot_aggressive.py`) - Focus su BTCUSDT
2. **Multi Coin** (`binance_bot_multi.py`) - 10 crypto simultaneee

### Risk Management
- ✅ Stop Loss automatico (2%)
- ✅ Take Profit automatico (4%)
- ✅ Trailing Stop (2.5%)
- ✅ Position sizing basato su % del saldo

## 📊 Crypto Monitorate (Multi-Coin)

| Coin | Pair |
|------|------|
| Bitcoin | BTCUSDT |
| Ethereum | ETHUSDT |
| Solana | SOLUSDT |
| XRP | XRPUSDT |
| Dogecoin | DOGEUSDT |
| Cardano | ADAUSDT |
| Avalanche | AVAXUSDT |
| Polygon | MATICUSDT |
| Chainlink | LINKUSDT |
| Polkadot | DOTUSDT |

## 🛠️ Installazione

### 1. Requisiti
```bash
python3 --version  # Python 3.10+
```

### 2. Installa Dipendenze
```bash
pip install python-binance pandas pandas_ta python-dotenv
```

### 3. Configura API Keys
Crea il file `.env`:
```env
BINANCE_API_KEY=la_tua_api_key
BINANCE_API_SECRET=la_tua_secret_key
```

> 🔑 Ottieni le API key su: https://www.binance.com/en/my/settings/api-management

### 4. Avvia il Bot

**Single Coin (BTC):**
```bash
python3 binance_bot_aggressive.py
```

**Multi Coin (10 crypto):**
```bash
python3 binance_bot_multi.py
```

## 📊 Dashboard Web

Il bot include una dashboard web che mostra in tempo reale:
- Prezzo di ogni crypto
- Indicatori tecnici (RSI, MACD, EMA)
- Segnali di acquisto/vendita
- Posizioni aperte
- Statistiche e PnL

### Avvia Dashboard
```bash
python3 dashboard_server.py
```

Poi apri: `http://localhost:8080`

## 🖥️ Deploy come Servizio (Linux)

Crea il file `/etc/systemd/system/binance-bot.service`:

```ini
[Unit]
Description=Binance Trading Bot
After=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/binance-trading-bot
ExecStart=/usr/bin/python3 /path/to/binance-trading-bot/binance_bot_multi.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Abilita e avvia:
```bash
sudo systemctl daemon-reload
sudo systemctl enable binance-bot
sudo systemctl start binance-bot
```

## 📈 Come Funziona

### Segnali di Acquisto (BUY)
Il bot compra quando almeno **3 su 4** condizioni sono soddisfatte:
1. RSI < 40 (sovra venduto)
2. MACD bullish o istogramma positivo
3. Prezzo sopra EMA short
4. Volume spike (> 1.5x media)

### Segnali di Vendita (SELL)
- **Take Profit**: +4% dal prezzo di ingresso
- **Stop Loss**: -2% dal prezzo di ingresso
- **Trailing Stop**: -2.5% dal massimo raggiunto

## ⚠️ Disclaimer

Questo software è fornito "così com'è". Il trading comporta rischi significativi. Non investire più di quanto puoi permetterti di perdere. Non sono responsabile di perdite finanziarie.

## 📝 Licenza

MIT License

## 👨‍💻 Autore

**grivetto** - [GitHub](https://github.com/grivetto)

---

## 📊 Grid Trading Bot

Una strategia alternativa: Spot Grid Trading.

### Come funziona:
1. Definisci un range di prezzo (es. $68,000 - $75,000)
2. Dividi in N livelli (es. 10 griglie)
3. Il bot piazza ordini BUY sotto il prezzo corrente
4. Il bot piazza ordini SELL sopra il prezzo corrente
5. Quando un BUY esegue → piazza SELL al livello sopra
6. Quando un SELL esegue → piazza BUY al livello sotto

### Avvio:
```bash
# Modifica i parametri in binance_grid_bot.py
LOWER_BOUND = 68000.0    # Prezzo minimo
UPPER_BOUND = 75000.0    # Prezzo massimo
GRID_LEVELS = 10         # Numero di griglie

# Avvia
python3 binance_grid_bot.py
```

### Dashboard Grid:
```bash
python3 dashboard_server.py
# Apri: http://localhost:8080/grid
```

