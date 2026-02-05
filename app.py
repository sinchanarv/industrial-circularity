from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from pymongo import MongoClient
from web3 import Web3
import datetime
import json
from fpdf import FPDF
import os
from werkzeug.utils import secure_filename

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
app.config['UPLOAD_FOLDER'] = 'static/uploads'

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
@app.route('/dashboard')
def dashboard():
    # 1. Security Check
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    user_id = session['id']

    # 2. FETCH TRANSACTION HISTORY (SQL)
    # We find all transactions where the current user is EITHER the buyer OR the seller
    cursor = mysql.connection.cursor()
    cursor.execute('''
        SELECT t.transaction_id, t.transaction_date, m.material_name, m.quantity_kg, 
               CASE WHEN t.buyer_id = %s THEN 'Bought' ELSE 'Sold' END as role_in_tx
        FROM Transactions t
        JOIN Materials m ON t.material_id = m.material_id
        WHERE t.buyer_id = %s OR t.seller_id = %s
        ORDER BY t.transaction_date DESC
    ''', (user_id, user_id, user_id))
    
    tx_data = cursor.fetchall()
    
    # Convert database rows to a clean list for HTML
    history = []
    for row in tx_data:
        history.append({
            'id': row[0],
            'date': row[1],
            'material': row[2],
            'qty': row[3],
            'type': row[4]
        })

    # 3. FETCH ANALYTICS FOR CHART (MongoDB)
    # (Optional: If you haven't bought anything, this might be empty, which is fine)
    labels = []
    values = []
    try:
        pipeline = [
            {"$group": {"_id": "$material_type", "total_qty": {"$sum": "$quantity_recycled"}}}
        ]
        results = list(impact_collection.aggregate(pipeline))
        labels = [row['_id'] for row in results]
        values = [row['total_qty'] for row in results]
    except:
        pass # Ignore errors if MongoDB is empty

    cursor.close()
    
    # 4. SEND DATA TO TEMPLATE
    return render_template('dashboard.html', history=history, labels=labels, values=values)

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

        # --- NEW IMAGE LOGIC START ---
        image_filename = 'default.png' # Default if no image uploaded
        
        if 'material_image' in request.files:
            file = request.files['material_image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                # Save the file to: static/uploads/filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename
        # --- NEW IMAGE LOGIC END ---

        cursor = mysql.connection.cursor()
        # Note: We added 'image_file' to the query
        cursor.execute('''
            INSERT INTO Materials (owner_id, material_name, category, quantity_kg, price_per_kg, image_file)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (owner_id, name, category, quantity, price, image_filename))
        
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('dashboard'))

    return render_template('post_material.html')

@app.route('/market')
def market():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    # Get the category from the URL (e.g., /market?category=Metal)
    category_filter = request.args.get('category')

    cursor = mysql.connection.cursor()

    # Base Query
    query = '''
        SELECT Materials.*, Users.company_name 
        FROM Materials 
        JOIN Users ON Materials.owner_id = Users.user_id 
        WHERE status = 'Available'
    '''
    
    query_params = ()

    # If user selected a category, add to the query
    if category_filter and category_filter != "":
        query += " AND category = %s"
        query_params = (category_filter,)

    # Execute the dynamic query
    cursor.execute(query, query_params)
    data = cursor.fetchall()
    cursor.close()
    
    return render_template('market.html', materials=data)

# ============================================
# THE CORE HYBRID & BLOCKCHAIN LOGIC
# ============================================
@app.route('/buy/<int:id>')
def buy_material(id):
    if 'loggedin' not in session: return redirect(url_for('login'))
    buyer_id = session['id']
    
    print(f"--- STARTING BUY PROCESS FOR MATERIAL ID {id} ---")

    # 1. FETCH & VALIDATE
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM Materials WHERE material_id = %s', (id,))
    material = cursor.fetchone()
    
    if not material:
        cursor.close()
        print("❌ Material not found")
        return "Material not found"

    seller_id = material[1]
    material_name = str(material[2])
    category = material[3]
    quantity = float(material[4])
    price = float(material[5])
    total_cost = int(quantity * price)

    # 2. SQL INSERT TRANSACTION
    try:
        cursor.execute('''
            INSERT INTO Transactions (buyer_id, seller_id, material_id, total_amount)
            VALUES (%s, %s, %s, %s)
        ''', (buyer_id, seller_id, id, total_cost))
        transaction_id = cursor.lastrowid
        print(f"✅ Transaction ID generated: {transaction_id}")
        
        # 3. SQL UPDATE STATUS
        cursor.execute('UPDATE Materials SET status = "Sold" WHERE material_id = %s', (id,))
        mysql.connection.commit() # Commit immediately
        cursor.close()
        print("✅ SQL Transaction Saved & Committed")
    except Exception as e:
        print(f"❌ SQL ERROR: {e}")
        return f"Database Error: {e}"

    # 4. BLOCKCHAIN DIRECT WRITE
    try:
        # Re-open connection for names
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT company_name FROM Users WHERE user_id = %s', (buyer_id,))
        buyer_name = cursor.fetchone()[0]
        cursor.execute('SELECT company_name FROM Users WHERE user_id = %s', (seller_id,))
        seller_name = cursor.fetchone()[0]
        cursor.close()

        if web3.is_connected():
            print("⏳ Sending to Blockchain...")
            data_str = f"Buy:{buyer_name}|Sell:{seller_name}|Item:{material_name}|Amt:{total_cost}"
            hex_data = web3.to_hex(text=data_str)
            
            # Send Transaction
            tx_hash = web3.eth.send_transaction({
                'from': web3.eth.accounts[0],
                'to': web3.eth.accounts[0],
                'value': 0,
                'data': hex_data
            })
            
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
            ganache_hash = receipt.transactionHash.hex()
            print(f"✅ Block Mined! Hash: {ganache_hash}")
            
            # --- CRITICAL SAVE STEP ---
            print("⏳ Attempting to save Hash to SQL...")
            try:
                cursor = mysql.connection.cursor()
                cursor.execute('''
                    INSERT INTO Blockchain_Ledger (transaction_id, prev_hash, curr_hash) 
                    VALUES (%s, %s, %s)
                ''', (transaction_id, 'GENESIS', ganache_hash))
                mysql.connection.commit()
                cursor.close()
                print("✅✅✅ HASH SAVED TO SQL SUCCESSFULLY! ✅✅✅")
            except Exception as sql_e:
                print(f"❌ FAILED TO SAVE HASH TO SQL: {sql_e}")
                
    except Exception as e:
        print(f"⚠️ Blockchain Error: {e}")

    return redirect(url_for('dashboard'))

@app.route('/ledger')
def ledger():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM Blockchain_Ledger')
    data = cursor.fetchall()
    cursor.close()
    return render_template('ledger.html', blocks=data)


@app.route('/download_certificate/<int:tx_id>')
def download_certificate(tx_id):
    if 'loggedin' not in session: return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    
    # FIX: Changed 'JOIN Blockchain_Ledger' to 'LEFT JOIN'
    # This ensures the certificate generates even if the Blockchain Hash is missing.
    cursor.execute('''
        SELECT t.transaction_date, b.company_name, s.company_name, m.material_name, m.quantity_kg, bl.curr_hash
        FROM Transactions t
        JOIN Users b ON t.buyer_id = b.user_id
        JOIN Users s ON t.seller_id = s.user_id
        JOIN Materials m ON t.material_id = m.material_id
        LEFT JOIN Blockchain_Ledger bl ON t.transaction_id = bl.transaction_id
        WHERE t.transaction_id = %s
    ''', (tx_id,))
    data = cursor.fetchone()
    cursor.close()
    
    if not data: return "Transaction not found in Database"

    # Handle cases where Hash might be None (because of LEFT JOIN)
    blockchain_hash = data[5] if data[5] else "PENDING / NOT RECORDED ON CHAIN"

    # Create PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 22)
    pdf.set_text_color(34, 139, 34) # Green
    pdf.cell(200, 20, "Green Circularity Certificate", ln=True, align='C')
    
    pdf.set_text_color(0, 0, 0) # Black
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(200, 10, f"Transaction Date: {data[0]}", ln=True, align='C')
    
    pdf.ln(10)
    pdf.cell(0, 10, f"Issued To (Buyer): {data[1]}", ln=True)
    pdf.cell(0, 10, f"Sourced From (Seller): {data[2]}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f"Material Recycled: {data[4]} kg of {data[3]}", ln=True)
    
    pdf.ln(15)
    pdf.set_font("Courier", size=8)
    pdf.multi_cell(0, 5, f"Blockchain Proof Hash:\n{blockchain_hash}")
    
    # Save
    if not os.path.exists('static'): os.makedirs('static')
    filename = f"static/Certificate_{tx_id}.pdf"
    pdf.output(filename)
    
    return redirect(url_for('static', filename=f'Certificate_{tx_id}.pdf'))
if __name__ == '__main__':
    app.run(debug=True)