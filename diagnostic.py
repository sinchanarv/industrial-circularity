from web3 import Web3

# 1. Connect
ganache_url = "http://127.0.0.1:7545"
web3 = Web3(Web3.HTTPProvider(ganache_url))

if not web3.is_connected():
    print("❌ Not Connected")
    exit()

print("✅ Connected to Ganache.")
account = web3.eth.accounts[0]

# 2. Prepare Data to Write
print("2. Attempting Direct Ledger Write...")
message = "Buyer:RV|Seller:Steel|Item:Metal|Amt:500"
# Convert text to Hex (Blockchain language)
hex_data = web3.to_hex(text=message)

try:
    # 3. Send Transaction (Send 0 ETH to self, but attach the DATA)
    tx_hash = web3.eth.send_transaction({
        'from': account,
        'to': account,  # Sending to self just to save the record
        'value': 0,
        'data': hex_data # <--- THIS IS YOUR RECORD
    })
    
    # 4. Wait for receipt
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"✅ SUCCESS! Data written to Block #{receipt.blockNumber}")
    print(f"🔗 Hash: {receipt.transactionHash.hex()}")
    print(">>> THIS METHOD WORKS. UPDATE APP.PY NOW. <<<")

except Exception as e:
    print(f"❌ Failed: {e}")