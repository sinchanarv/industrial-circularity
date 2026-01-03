from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from pymongo import MongoClient
import datetime

app = Flask(__name__)

# SECURITY CONFIGURATION
# This key is needed to encrypt the session cookies. 
app.secret_key = 'your_secret_key_here'

# DATABASE CONFIGURATION
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'IndustrialCircularityDB'

mysql = MySQL(app)
client = MongoClient('mongodb://localhost:27017/')
mongo_db = client['CircularDB']         # Creates a DB named 'CircularDB'
impact_collection = mongo_db['ImpactReports'] # Creates a Collection
# ============================================
# ROUTES
# ============================================

@app.route('/')
def home():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT COUNT(*) FROM Users')
    user_count = cursor.fetchone()[0]
    cursor.close()
    return render_template('index.html', count=user_count)

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
        return redirect(url_for('login')) # Redirect to Login after registering

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        # Check if user exists
        cursor.execute('SELECT * FROM Users WHERE email = %s AND password_hash = %s', (email, password))
        user = cursor.fetchone()
        cursor.close()

        if user:
            # Create Session Data (This "logs them in")
            session['loggedin'] = True
            session['id'] = user[0]       # The User ID
            session['name'] = user[1]     # The Company Name
            session['role'] = user[4]     # The Role (Producer/Recycler)
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid email or password!'

    return render_template('login.html', error=error)

@app.route('/dashboard')
def dashboard():
    # Check if user is logged in
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

# Route for Producers to Post Waste
@app.route('/post_material', methods=['GET', 'POST'])
def post_material():
    # Security Check: Must be logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['material_name']
        category = request.form['category']
        quantity = request.form['quantity']
        price = request.form['price']
        owner_id = session['id']  # <--- IMPORTANT: We get this from the session!

        cursor = mysql.connection.cursor()
        cursor.execute('''
            INSERT INTO Materials (owner_id, material_name, category, quantity_kg, price_per_kg)
            VALUES (%s, %s, %s, %s, %s)
        ''', (owner_id, name, category, quantity, price))
        
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('dashboard'))

    return render_template('post_material.html')

# Route for Marketplace
@app.route('/market')
def market():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    # SQL JOIN to get the Company Name of the seller
    cursor.execute('''
        SELECT Materials.*, Users.company_name 
        FROM Materials 
        JOIN Users ON Materials.owner_id = Users.user_id 
        WHERE status = 'Available'
    ''')
    data = cursor.fetchall()
    cursor.close()
    
    return render_template('market.html', materials=data)

@app.route('/buy/<int:id>')
def buy_material(id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    buyer_id = session['id']
    
    # 1. FETCH MATERIAL DETAILS (SQL)
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM Materials WHERE material_id = %s', (id,))
    material = cursor.fetchone()
    
    # material structure: [id, owner_id, name, category, qty, price, status, date]
    seller_id = material[1]
    material_name = material[2]
    category = material[3]
    quantity = float(material[4])
    price = float(material[5])
    total_cost = quantity * price

    # 2. RECORD TRANSACTION & UPDATE STATUS (SQL)
    # Insert into Transactions table
    cursor.execute('''
        INSERT INTO Transactions (buyer_id, seller_id, material_id, total_amount)
        VALUES (%s, %s, %s, %s)
    ''', (buyer_id, seller_id, id, total_cost))

    transaction_id = cursor.lastrowid
    # Mark material as 'Sold' so it disappears from the market
    cursor.execute('UPDATE Materials SET status = "Sold" WHERE material_id = %s', (id,))
    
    # Get the Transaction ID we just created (Need this for linking!)
    
    
    mysql.connection.commit()
    cursor.close()

    # 3. GENERATE IMPACT REPORT (NoSQL - MongoDB)
    # Different materials save different amounts of CO2.
    # Logic: If 1kg of Fly Ash is recycled, we save approx 0.8kg CO2.
    co2_factor = 0.5 
    if category == 'Industrial': co2_factor = 0.8
    if category == 'Metal': co2_factor = 1.5
    if category == 'Textile': co2_factor = 0.3

    saved_carbon = quantity * co2_factor
    saved_energy = quantity * 0.2 # Dummy energy metric

    # Create the JSON Document
    impact_report = {
        "transaction_id": transaction_id,  # LINKING SQL ID TO NOSQL DOC
        "material_type": category,
        "quantity_recycled": quantity,
        "sustainability_metrics": {
            "carbon_emissions_prevented_kg": saved_carbon,
            "landfill_space_saved_m3": quantity * 0.01,
            "energy_conserved_kwh": saved_energy
        },
        "generated_at": datetime.datetime.now()
    }

    # Insert into MongoDB
    impact_collection.insert_one(impact_report)

    # 4. DONE! Redirect to Dashboard
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)