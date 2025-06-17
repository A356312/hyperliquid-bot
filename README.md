# Hyperliquid TradingView Webhook

Automatisches Trading auf Hyperliquid basierend auf TradingView Alerts.

## Features
- Long/Short Positionen über Webhooks
- Automatisches Schließen aller Positionen
- 98% Balance Investment
- Order-Cancelling vor neuen Trades

## Setup

### 1. GitHub Repository erstellen
1. Neues Repository auf GitHub erstellen
2. Alle Files hochladen:
   - `main.py`
   - `requirements.txt` 
   - `Procfile`
   - `.gitignore`
   - `README.md`

### 2. Railway Deployment
1. [Railway.app](https://railway.app) → "Deploy from GitHub"
2. Repository auswählen
3. Environment Variable setzen:
   - `PRIVATE_KEY` = dein_hyperliquid_private_key
4. Deploy

### 3. TradingView Setup
**Webhook URL:** `https://your-app.railway.app/webhook`

**Alert Message Beispiele:**
```json
{"action": "buy"}   # Long Position
{"action": "sell"}  # Short Position  
{"action": "close"} # Alle Positionen schließen
```

## Testing
```bash
curl -X POST https://your-app.railway.app/webhook \
  -H "Content-Type: application/json" \
  -d '{"action": "buy"}'
```

## Sicherheit
- Private Key NIEMALS in Code committen
- Nur über Environment Variables
- .gitignore schützt sensitive Daten
