import os
import json
from flask import Flask, request, jsonify
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from eth_account import Account

app = Flask(__name__)

# DEBUG: Environment Variables prüfen
print("🔍 DEBUG - Alle Environment Variables:")
for key, value in os.environ.items():
    if 'WALLET' in key or 'AGENT' in key or 'PRIVATE' in key:
        print(f"  {key} = {value[:10] if value else 'NONE'}...")

print(f"🔍 MAIN_WALLET_ADDRESS = {os.environ.get('MAIN_WALLET_ADDRESS', 'NICHT GEFUNDEN')}")
print(f"🔍 AGENT_PRIVATE_KEY = {os.environ.get('AGENT_PRIVATE_KEY', 'NICHT GEFUNDEN')}")
print(f"🔍 WEBHOOK_PASSWORD = {os.environ.get('WEBHOOK_PASSWORD', 'NICHT GEFUNDEN')}")

# Setup mit Agent API Wallet (SICHER!)
# Environment Variables für Railway - MÜSSEN gesetzt sein!
MAIN_WALLET_ADDRESS = os.environ.get('MAIN_WALLET_ADDRESS')
AGENT_PRIVATE_KEY = os.environ.get('AGENT_PRIVATE_KEY')
WEBHOOK_PASSWORD = os.environ.get('WEBHOOK_PASSWORD')  # 🔐 NEU: Passwort-Schutz

# Prüfen ob Keys gesetzt sind
if not MAIN_WALLET_ADDRESS or not AGENT_PRIVATE_KEY:
    print("❌ FEHLER: MAIN_WALLET_ADDRESS oder AGENT_PRIVATE_KEY nicht gesetzt!")
    print("Railway Environment Variables prüfen!")
    exit(1)

if not WEBHOOK_PASSWORD:
    print("❌ FEHLER: WEBHOOK_PASSWORD nicht gesetzt!")
    print("Setze Environment Variable: WEBHOOK_PASSWORD=dein_sicheres_passwort")
    exit(1)

print(f"🔑 Main Wallet: {MAIN_WALLET_ADDRESS[:6]}...{MAIN_WALLET_ADDRESS[-4:]}")
print(f"🤖 Agent Wallet wird geladen...")
print(f"🔐 Webhook Passwort: {'*' * len(WEBHOOK_PASSWORD)}")

# Agent Wallet für Trading (kann nur traden, kein Geld abheben!)
agent_wallet = Account.from_key(AGENT_PRIVATE_KEY)
exchange = Exchange(
    wallet=agent_wallet,  # Agent zum Signieren
    base_url=constants.MAINNET_API_URL
)

# Info für Balance (verwendet Haupt-Wallet-Adresse)
info = Info(constants.MAINNET_API_URL, skip_ws=True)

@app.route('/')
def health_check():
    return jsonify({
        "status": "running",
        "message": "Hyperliquid Webhook Server (Secure Agent API)",
        "main_wallet": MAIN_WALLET_ADDRESS[:6] + "..." + MAIN_WALLET_ADDRESS[-4:],
        "agent_wallet": agent_wallet.address[:6] + "..." + agent_wallet.address[-4:],
        "security": "🔒 Password Protection Active"
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        # 🔐 PASSWORT-CHECK ZUERST!
        provided_password = data.get('password', '')
        if provided_password != WEBHOOK_PASSWORD:
            print(f"❌ UNAUTHORIZED: Falsches Passwort! Bereitgestellt: '{provided_password}'")
            return jsonify({
                "error": "Unauthorized: Invalid password",
                "status": "denied"
            }), 401
        
        action = data.get('action', '').lower()
        
        print(f"📨 Webhook received: {data}")
        
        if action not in ['buy', 'sell', 'close']:
            return jsonify({"error": "Invalid action. Use: buy, sell, close"}), 400
        
        # Alle offenen Orders schließen (Main Wallet für Abfragen)
        open_orders = info.open_orders(MAIN_WALLET_ADDRESS)
        if open_orders:
            print(f"🚫 Cancelling {len(open_orders)} open orders...")
            for order in open_orders:
                exchange.cancel(order['coin'], order['oid'])
        
        if action == "close":
            return handle_close()
        else:
            return handle_trade(action)
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def handle_close():
    user_state = info.user_state(MAIN_WALLET_ADDRESS)  # Main Wallet für Abfragen
    positions = user_state.get('assetPositions', [])
    
    closed_positions = []
    
    for pos in positions:
        if float(pos['position']['szi']) != 0:
            coin = pos['position']['coin']
            position_size = abs(float(pos['position']['szi']))
            is_long = float(pos['position']['szi']) > 0
            
            print(f"🔄 Closing {coin} position: {position_size}")
            
            result = exchange.market_open(coin, not is_long, position_size)
            
            if result['status'] == 'ok':
                closed_positions.append(f"{coin}: {position_size}")
                print(f"✅ {coin} position closed")
            else:
                print(f"❌ Failed to close {coin}: {result}")
    
    if not closed_positions:
        return "ℹ️ No positions to close"
    
    return f"✅ Closed positions: {', '.join(closed_positions)}"

def handle_trade(action):
    # Balance abrufen (Main Wallet für Abfragen)
    user_state = info.user_state(MAIN_WALLET_ADDRESS)
    margin_summary = user_state['marginSummary']
    
    account_value = float(margin_summary['accountValue'])
    
    print(f"💰 Account Value: ${account_value}")
    print(f"🔍 Komplette User State: {json.dumps(user_state, indent=2)}")
    
    # EINFACHE LÖSUNG: Festen Hebel setzen oder aus Environment Variable
    # Du kannst den Hebel manuell in Railway als Environment Variable setzen
    leverage = float(os.environ.get('LEVERAGE', '1.0'))  # Default: 1x
    
    print(f"🚀 Using Leverage: {leverage}x (set via LEVERAGE env var)")
    
    # ETH Preis und Size mit Hebel berechnen
    eth_price = float(info.all_mids()['ETH'])
    target_size = (account_value * 0.998 * leverage) / eth_price
    target_size = round(target_size, 4)
    
    print(f"📊 Target Size (mit {leverage}x Hebel): {target_size} ETH")
    
    # KEIN MINIMUM CHECK! Verwende die berechnete Size direkt
    
    # Aktuelle ETH Position checken
    current_position_size = 0
    positions = user_state.get('assetPositions', [])
    for pos in positions:
        if pos['position']['coin'] == 'ETH' and float(pos['position']['szi']) != 0:
            current_position_size = float(pos['position']['szi'])
            break
    
    is_buy = action == "buy"
    direction = "Long" if is_buy else "Short"
    
    print(f"📈 ETH Preis: ${eth_price}")
    if current_position_size != 0:
        print(f"📊 Aktuelle Position: {abs(current_position_size)} ETH {'Long' if current_position_size > 0 else 'Short'}")
    
    # Berechne die Order-Größe
    if current_position_size == 0:
        # Keine Position -> normale Order
        order_size = target_size
        print(f"🆕 Neue {direction} Position: {order_size} ETH")
    else:
        # Position vorhanden -> Schließen + neue Position
        order_size = target_size + abs(current_position_size)
        print(f"🔄 Wechsel zu {direction}: {order_size} ETH Order")
        print(f"   -> Schließt {abs(current_position_size)} ETH + öffnet {target_size} ETH {direction}")
    
    # Market Order (Agent Wallet signiert)
    result = exchange.market_open("ETH", is_buy, order_size)
    
    print(f"📊 {direction} Order Result: {result}")
    
    if result['status'] == 'ok':
        print(f"✅ Order successful!")
        return f"✅ {direction} Order executed: {order_size} ETH @${eth_price}"
    else:
        print(f"❌ Order failed: {result}")
        return f"❌ Order failed: {result.get('response', 'Unknown error')}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
