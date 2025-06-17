import os
import json
from flask import Flask, request, jsonify
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from eth_account import Account

app = Flask(__name__)

# Setup mit Private Key aus Environment Variable
PRIVATE_KEY = os.environ.get('PRIVATE_KEY', '1163cee7c45378c47b75f9cb581af8aa8bca275d2dd60dc2b25f50147a48bb82')

wallet = Account.from_key(PRIVATE_KEY)
exchange = Exchange(
    wallet=wallet,
    base_url=constants.MAINNET_API_URL
)
info = Info(constants.MAINNET_API_URL, skip_ws=True)

@app.route('/')
def health_check():
    return jsonify({
        "status": "running",
        "message": "Hyperliquid Webhook Server"
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        action = data.get('action', '').lower()
        
        print(f"📨 Webhook received: {data}")
        
        if action not in ['buy', 'sell', 'close']:
            return jsonify({"error": "Invalid action. Use: buy, sell, close"}), 400
        
        # Alle offenen Orders schließen
        open_orders = info.open_orders(wallet.address)
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
    user_state = info.user_state(wallet.address)
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
    # Balance abrufen
    user_state = info.user_state(wallet.address)
    balance = float(user_state['marginSummary']['accountValue'])
    print(f"💰 Account Balance: ${balance}")
    
    # ETH Preis und Size berechnen
    eth_price = float(info.all_mids()['ETH'])
    target_size = (balance * 0.98) / eth_price
    target_size = round(target_size, 4)
    
    if target_size < 0.01:
        target_size = 0.01
        print(f"⚠️  Size angepasst auf Minimum: {target_size} ETH")
    
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
    
    # Market Order
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
