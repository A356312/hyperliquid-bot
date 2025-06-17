import os
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from eth_account import Account
from flask import Flask, request, jsonify

# Setup mit Private Key aus Environment Variable
private_key = os.getenv('PRIVATE_KEY')
if not private_key:
    raise ValueError("PRIVATE_KEY environment variable nicht gesetzt!")

wallet = Account.from_key(private_key)
exchange = Exchange(wallet=wallet, base_url=constants.MAINNET_API_URL)
info = Info(constants.MAINNET_API_URL, skip_ws=True)

app = Flask(__name__)

def execute_trade(action):
    """Führt den Trade aus (buy/sell/close)"""
    print(f"📈 Webhook empfangen: {action}")
    
    # Alle offenen Orders schließen
    open_orders = info.open_orders(wallet.address)
    if open_orders:
        print(f"Schließe {len(open_orders)} offene Orders...")
        for order in open_orders:
            exchange.cancel(order['coin'], order['oid'])

    if action == "close":
        # Alle Positionen schließen
        user_state = info.user_state(wallet.address)
        positions = user_state.get('assetPositions', [])
        
        for pos in positions:
            if float(pos['position']['szi']) != 0:
                coin = pos['position']['coin']
                position_size = abs(float(pos['position']['szi']))
                is_long = float(pos['position']['szi']) > 0
                
                result = exchange.market_open(coin, not is_long, position_size)
                print(f"{coin} Position geschlossen: {result['status']}")

    elif action in ["buy", "sell"]:
        # Balance und Size berechnen
        user_state = info.user_state(wallet.address)
        balance = float(user_state['marginSummary']['accountValue'])
        eth_price = float(info.all_mids()['ETH'])
        size = (balance * 0.98) / eth_price
        size = round(size, 4)
        
        if size < 0.01:
            size = 0.01
        
        is_buy = action == "buy"
        direction = "Long" if is_buy else "Short"
        
        result = exchange.market_open("ETH", is_buy, size)
        print(f"{direction}: {size} ETH - {result['status']}")

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView Webhook Endpoint"""
    try:
        data = request.get_json()
        action = data.get('action', '').lower()
        
        if action in ['buy', 'sell', 'close']:
            execute_trade(action)
            return jsonify({"status": "success", "action": action}), 200
        else:
            return jsonify({"error": "Invalid action"}), 400
            
    except Exception as e:
        print(f"Fehler: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def health():
    """Health Check"""
    return jsonify({"status": "running", "message": "Hyperliquid Webhook Server"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
