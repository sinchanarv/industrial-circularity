from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from pymongo import MongoClient
from web3 import Web3
import datetime
import json

# Import the Smart Contract setup
from blockchain_config import contract_abi, contract_bytecode

app = Flask(__name__)

# ============================================
# 1. SECURITY CONFIGURATION
# ============================================
app.secret_key = 'rvce_project_secret_key'

# ============================================
# 2. SQL DATABASE CONFIGURATION (XAMPP)
# ============================================
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'IndustrialCircularityDB'

mysql = MySQL(app)

# ============================================
# 3. MONGODB CONFIGURATION (NoSQL)
# ============================================
try:
    client = MongoClient('mongodb://localhost:27017/')
    mongo_db = client['CircularDB']
    impact_collection = mongo_db['ImpactReports']
    print("✅ Connected to MongoDB")
except:
    print("❌ Failed to connect to MongoDB. Is it running?")

# ============================================
# 4. BLOCKCHAIN CONFIGURATION (Ganache)
# ============================================
ganache_url = "http://127.0.0.1:7545" # Check your Ganache App for RPC Server
web3 = Web3(Web3.HTTPProvider(ganache_url))
deployed_contract = None

if web3.is_connected():
    print("✅ Connected to Ganache Blockchain")
    web3.eth.default_account = web3.eth.accounts[0]
    
    # Deploy Contract automatically on startup (Simulation for Project)
    try:
        SupplyChain = web3.eth.contract(abi=contract_abi, bytecode=contract_bytecode)
        tx_hash = SupplyChain.constructor().transact()
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        contract_address = tx_receipt.contractAddress
        deployed_contract = web3.eth.contract(address=contract_address, abi=contract_abi)
        print(f"📜 Smart Contract Deployed at: {contract_address}")
    except Exception as e:
        print(f"⚠️ Contract Deployment Failed: {e}")
else:
    print("❌ Failed to connect to Blockchain (Is Ganache Open?)")


# ============================================
# ROUTES (PAGES)
# ============================================

@app.route('/')
def home():
    # Check SQL Connection
    try:
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM Users')
        user_count = cursor.fetchone()[0]
        cursor.close()
        return render_template('index.html', count=user_count)
    except Exception as e:
        return f"<h1>Database Error</h1><p>Please ensure XAMPP MySQL is running.</p><p>Error: {e}</p>"

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['company_name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        location = request.form['location']

        cursor = mysql.connection.cursor()
        cursor.execute('''
            INSERT INTO Users (company_name, email, password_hash, role, location)
            VALUES (%s, %s, %s, %s, %s)
        ''', (name, email, password, role, location))
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM Users WHERE email = %s AND password_hash = %s', (email, password))
        user = cursor.fetchone()
        cursor.close()

        if user:
            session['loggedin'] = True
            session['id'] = user[0]
            session['name'] = user[1]
            session['role'] = user[4]
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid email or password!'

    return render_template('login.html', error=error)

@app.route('/dashboard')
def dashboard():
    if 'loggedin' in session:
        return render_template('dashboard.html')
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('name', None)
    session.pop('role', None)
    return redirect(url_for('login'))

@app.route('/post_material', methods=['GET', 'POST'])
def post_material():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['material_name']
        category = request.form['category']
        quantity = request.form['quantity']
        price = request.form['price']
        owner_id = session['id']

        cursor = mysql.connection.cursor()
        cursor.execute('''
            INSERT INTO Materials (owner_id, material_name, category, quantity_kg, price_per_kg)
            VALUES (%s, %s, %s, %s, %s)
        ''', (owner_id, name, category, quantity, price))
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('dashboard'))

    return render_template('post_material.html')

@app.route('/market')
def market():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute('''
        SELECT Materials.*, Users.company_name 
        FROM Materials 
        JOIN Users ON Materials.owner_id = Users.user_id 
        WHERE status = 'Available'
    ''')
    data = cursor.fetchall()
    cursor.close()
    return render_template('market.html', materials=data)

# ============================================
# THE CORE HYBRID & BLOCKCHAIN LOGIC
# ============================================
@app.route('/buy/<int:id>')
def buy_material(id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    buyer_id = session['id']
    
    # 1. FETCH DETAILS
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM Materials WHERE material_id = %s', (id,))
    material = cursor.fetchone()
    
    if not material:
        return "Material not found or already sold."

    seller_id = material[1]
    material_name = material[2]
    category = material[3]
    quantity = float(material[4])
    price = float(material[5])
    total_cost = quantity * price

    # 2. SQL: INSERT TRANSACTION
    cursor.execute('''
        INSERT INTO Transactions (buyer_id, seller_id, material_id, total_amount)
        VALUES (%s, %s, %s, %s)
    ''', (buyer_id, seller_id, id, total_cost))
    
    # Capture the ID immediately
    transaction_id = cursor.lastrowid

    # 3. SQL: UPDATE STATUS
    cursor.execute('UPDATE Materials SET status = "Sold" WHERE material_id = %s', (id,))
    mysql.connection.commit() # Save SQL changes first

    # 4. NOSQL: GENERATE IMPACT REPORT (MongoDB)
    co2_factor = 0.5 
    if category == 'Industrial': co2_factor = 0.8
    if category == 'Metal': co2_factor = 1.5
    
    impact_report = {
        "transaction_id": transaction_id,
        "material_type": category,
        "quantity_recycled": quantity,
        "sustainability_metrics": {
            "carbon_emissions_prevented_kg": quantity * co2_factor,
            "energy_conserved_kwh": quantity * 0.2
        },
        "generated_at": datetime.datetime.now()
    }
    impact_collection.insert_one(impact_report)

    # 5. BLOCKCHAIN: SMART CONTRACT CALL (Ganache)
    try:
        # Get Company Names for the Blockchain
        cursor.execute('SELECT company_name FROM Users WHERE user_id = %s', (buyer_id,))
        buyer_name = cursor.fetchone()[0]
        cursor.execute('SELECT company_name FROM Users WHERE user_id = %s', (seller_id,))
        seller_name = cursor.fetchone()[0]

        # Send to Ganache
        if deployed_contract:
            tx_hash = deployed_contract.functions.addTransaction(
                str(buyer_name),
                str(seller_name),
                str(material_name),
                int(total_cost)
            ).transact({
                'from': web3.eth.accounts[0], 
                'gas': 3000000
            })
            
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
            ganache_hash = receipt.transactionHash.hex()
            print(f"⛓️ Block Mined! Hash: {ganache_hash}")

            # Store the REAL Blockchain Hash in SQL
            cursor.execute('''
                INSERT INTO Blockchain_Ledger (transaction_id, prev_hash, curr_hash)
                VALUES (%s, %s, %s)
            ''', (transaction_id, 'GENESIS', ganache_hash))
            mysql.connection.commit()

    except Exception as e:
        print(f"⚠️ Blockchain Error: {e}")

    cursor.close()
    return redirect(url_for('dashboard'))

@app.route('/ledger')
def ledger():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM Blockchain_Ledger')
    data = cursor.fetchall()
    cursor.close()
    return render_template('ledger.html', blocks=data)

if __name__ == '__main__':
    app.run(debug=True)