import random
import os
from decimal import Decimal
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import pyodbc
import json
import bcrypt
import re
import uuid
from datetime import datetime

app = Flask(__name__)
CORS(app, origins=[origin.strip() for origin in os.getenv('AAWCL_ALLOWED_ORIGINS', 'http://localhost:4200').split(',') if origin.strip()])
signing_key = os.environ.get('AAWCL_JWT_SECRET_KEY', '')
if len(signing_key) < 32:
    raise RuntimeError('Set a unique AAWCL_JWT_SECRET_KEY of at least 32 characters.')
app.config['JWT_SECRET_KEY'] = signing_key
jwt = JWTManager(app)

# Connection parameters
server = os.environ['AAWCL_DB_SERVER']
database = os.environ['AAWCL_DB_NAME']
username = os.environ['AAWCL_DB_USER']
password = os.environ['AAWCL_DB_PASSWORD']

# Establish connection
conn = pyodbc.connect('DRIVER={SQL Server};SERVER='+server+';DATABASE='+database+';UID='+username+';PWD='+ password)

# Create cursor
cursor = conn.cursor()

def hash_password(password):
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed_password.decode('utf-8')

def verify_password(password, hashed_password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def validate_username(username):
    # Define the regex pattern for the password
    pattern = r'^[a-zA-Z0-9]{8,}$'

    # Check if the password matches the pattern
    if re.match(pattern, username):
        return True
    else:
        return False

def validate_password(password):
    # Define the regex pattern for the password
    pattern = r'^[a-zA-Z0-9]{8,}$'

    # Check if the password matches the pattern
    if re.match(pattern, password):
        return True
    else:
        return False

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email):
        return True
    else:
        return False

def validate_phone_number(phone_number):
    # Regular expression to match phone numbers with optional country code
    pattern = re.compile(r'^(\+\d{1,3})?(\d{10})$')

    # Check if the phone number matches the pattern
    if pattern.match(phone_number):
        return True
    else:
        return False

# Create a new user for signup
@app.route('/signup', methods=['POST'])
def create_user():
    data = request.json
    Username = data.get('Username')
    Email = data.get('Email')
    PhoneNumber = data.get('PhoneNumber')
    Password = data.get('PasswordHash')
    cursor.execute('SELECT * FROM Users WHERE Username = ?', Username)
    user = cursor.fetchone()
    cursor.execute('SELECT * FROM Users WHERE Email = ?', Email)
    email = cursor.fetchone()
    cursor.execute('SELECT * FROM Users WHERE PhoneNumber = ?', PhoneNumber)
    phone = cursor.fetchone()

    if user or email or phone:
        return jsonify({'error': 'Username or Email or Phone Number Existed'}), 400

    if not validate_username(Username):
        return jsonify({'error': 'Username must be at least 8 characters(lower case, uppercase or digits) long'}), 401

    if not validate_password(Password):
        return jsonify({'error': 'Password must be at least 8 characters(lower case, uppercase or digits) long'}), 402

    if not validate_email(Email):
        return jsonify({'error': 'Please enter valid email address'}), 403

    if not validate_phone_number(PhoneNumber):
        return jsonify({'error': 'Please enter valid phone number'}), 404

    if not all(key in data for key in ('Username', 'PasswordHash')):
        return jsonify({'error': 'Missing username or password'}), 405

    # Insert into database
    cursor.execute(
        'INSERT INTO Users (Username, PasswordHash, Email, FullName, CurrAddr, PhoneNumber) VALUES (?, ?, ?, ?, ?, ?)',
        data['Username'], hash_password(Password), data['Email'], data['FullName'], data['CurrentAddress'], data['PhoneNumber'])
    conn.commit()

    return jsonify({'message': 'User created successfully'}), 200

# Check for login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    Username = data.get('Username')
    Password = data.get('PasswordHash')
    cursor.execute('SELECT * FROM Users WHERE Username = ?', Username)
    user = cursor.fetchone()
    if not user:
        return jsonify({'message': 'User does not exist'}), 401

    if not Username or not Password:
        return jsonify({'message': 'Missing username or password'}), 400

    if verify_password(Password, user.PasswordHash):
        access_token = create_access_token(identity=user.UserID)
        return jsonify(access_token=access_token), 200
    else:
        return jsonify({'message': 'Invalid username or password'}), 401

# Listing all banking users is not a public API operation.
@app.route('/users', methods=['GET'])
@jwt_required()
def get_all_users():
    return jsonify({'error': 'Bulk user listing is disabled.'}), 403

# Only the authenticated user can view their limited profile.
@app.route('/users/<string:Username>', methods=['GET'])
@jwt_required()
def get_user(Username):
    current_id = get_jwt_identity()
    cursor.execute(
        'SELECT UserID, Username, Email, FullName, CurrAddr, PhoneNumber FROM Users '
        'WHERE Username = ? AND UserID = ?', Username, current_id
    )
    user = cursor.fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    fields = ('UserID', 'Username', 'Email', 'FullName', 'CurrAddr', 'PhoneNumber')
    return jsonify({'user': dict(zip(fields, user))}), 200

# Account profile edits require a matching token subject.
@app.route('/users/<int:UserID>', methods=['PUT'])
@jwt_required()
def update_user(UserID):
    if str(get_jwt_identity()) != str(UserID):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json(silent=True)
    fields = ('Email', 'FullName', 'CurrAddr', 'PhoneNumber')
    if not isinstance(data, dict) or any(field not in data for field in fields):
        return jsonify({'error': 'A complete profile is required.'}), 400
    cursor.execute('SELECT 1 FROM Users WHERE UserID = ?', UserID)
    if not cursor.fetchone():
        return jsonify({'error': 'User not found'}), 404
    cursor.execute(
        'UPDATE Users SET Email=?, FullName=?, CurrAddr=?, PhoneNumber=? WHERE UserID=?',
        data['Email'], data['FullName'], data['CurrAddr'], data['PhoneNumber'], UserID
    )
    conn.commit()
    return jsonify({'message': 'Profile updated.'}), 200

# Deleting banking accounts requires identity verification and ledger cleanup.
@app.route('/users/<int:UserID>', methods=['DELETE'])
@jwt_required()
def delete_user(UserID):
    return jsonify({'error': 'Account deletion is disabled pending a safe workflow.'}), 501

@app.route('/openaccount', methods=['POST'])
@jwt_required()
def open_account():
    try:
        data = request.json
        # Validate input data
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        required_field = 'AccountType'
        if required_field not in data:
            return jsonify({'error': f'Missing required field: {required_field}'}), 400

        # Generate a unique 16-digit Account Number
        account_number = str(uuid.uuid4().int)[:16]

        # Get the UserID from the JWT token
        user_id = get_jwt_identity()

        cursor.execute('SELECT * FROM Users WHERE UserID = ?', user_id)
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Extract account data
        account_type = data['AccountType']
        opening_date = datetime.now()
        acc_status = data.get('AccStatus', 'Activated')  # Default to 'Active' if not provided

        cursor.execute('INSERT INTO Accounts (AccountNumber, UserID, AccountType, Balance, OpeningDate, AccStatus) VALUES (?, ?, ?, ?, ?, ?)'
                   , account_number, int(user_id), account_type, 100.00, opening_date, acc_status)
        conn.commit()
        return jsonify({'message': 'Account created successfully'}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/myaccounts', methods=['GET'])
@jwt_required()
def my_accounts():
    user_id = get_jwt_identity()

    cursor.execute('SELECT * FROM Accounts WHERE UserID = ?', user_id)
    accounts = cursor.fetchall()
    result_list = []
    if not accounts:
        return jsonify({'error': 'no account exists'}), 400
    for account in accounts:
        account_dict = dict(zip([column[0] for column in cursor.description], account))

        # Convert decimal values to float
        account_dict['Balance'] = str(account_dict['Balance'])
        account_dict['AccountNumber'] = str(account_dict['AccountNumber'])

        # Convert datetime objects to ISO format string
        account_dict['OpeningDate'] = account_dict['OpeningDate'].isoformat()

        result_list.append(account_dict)
    json_result = json.dumps(result_list)
    return jsonify(json_result), 200

@app.route('/changestatus', methods=['POST'])
@jwt_required()
def change_status():
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    user_id = get_jwt_identity()
    account_number = data['AccountNumber']
    cursor.execute('SELECT * FROM Accounts WHERE UserID = ? AND AccountNumber = ?', user_id, account_number)
    account = cursor.fetchone()
    if not account:
        return jsonify({'error': 'Account not found'}), 404
    cursor.execute('UPDATE Accounts SET AccStatus = ? WHERE AccountNumber = ?', data['AccountStatus'], data['AccountNumber'])
    conn.commit()
    return jsonify({'message': 'Account status updated successfully!'}), 200

@app.route('/accoverview', methods=['GET'])
@jwt_required()
def accounts_overview():
    try:
        user_id = get_jwt_identity()

        cursor.execute('SELECT * FROM Accounts WHERE UserID = ?', user_id)
        accounts = cursor.fetchall()
        result_list = []
        if not accounts:
            return jsonify({'message': 'no account exists'}), 400
        for account in accounts:
            account_dict = {
                'AccountNumber': str(account[0]),
                'AccountType': account[2],
                'Balance': str(account[3])
            }
            result_list.append(account_dict)
        json_result = json.dumps(result_list)
        return jsonify(json_result), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500

def generate_transaction_id():
    return ''.join(random.choices('0123456789', k = random.randint(6,8)))

def generate_description(transaction_type, sender, recipient, amount):
    if transaction_type == 'transfer':
        description = f"Transferred from {sender} to {recipient}"
    elif transaction_type == 'deposit':
        description = f"Deposited to {recipient}"
    elif transaction_type == 'withdrawal':
        description = f"Witidrew from {sender}"
    elif transaction_type == 'receive':
        description = f"Received from {sender}"
    else:
        description = "UNKNOWN"

    description += f", Amount: {amount}"

    return description

@app.route('/transactions', methods=['POST'])
@jwt_required()
def make_transaction():
    # The original endpoint committed the debit, credit, and ledger rows separately.
    # Leave transfers disabled unless an operator explicitly enables a test sandbox.
    if os.environ.get('AAWCL_ENABLE_SIMULATED_TRANSFERS') != '1':
        return jsonify({'error': 'Transfers are disabled pending database staging verification.'}), 503

    from transfer_service import TransferError, transfer_funds
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Expected a JSON object.'}), 400

    # A separate, transaction-scoped connection avoids reusing a global cursor
    # across concurrent requests. Credentials never appear in source code.
    connection = None
    try:
        connection = pyodbc.connect(
            'DRIVER={ODBC Driver 18 for SQL Server};SERVER=' + server
            + ';DATABASE=' + database + ';UID=' + username
            + ';PWD=' + password + ';Encrypt=yes;TrustServerCertificate=no',
            autocommit=False,
            timeout=10,
        )
        result = transfer_funds(
            connection, get_jwt_identity(), data.get('sender_account_number'),
            data.get('recipient_account_number'), data.get('amount')
        )
        return jsonify(result), 200
    except TransferError as exc:
        return jsonify({'error': str(exc)}), exc.status_code
    except Exception:
        app.logger.exception('Transfer failed')
        return jsonify({'error': 'Unable to complete the transfer.'}), 500
    finally:
        if connection is not None:
            connection.close()

@app.route('/logs', methods=['POST'])
@jwt_required()
def get_log_history():
    try:
        data = request.json
        account_number = int(data['account_number'])
        cursor.execute('SELECT * FROM TransactionLogs WHERE AccountNumber = ?', (account_number,))
        logs = cursor.fetchall()
        if not logs:
            return jsonify({'error': 'No logs exist'}), 400

        history = []
        for log in logs:
            log_dict = dict(zip([column[0] for column in cursor.description], log))

            log_dict['Amount'] = float(log_dict['Amount'])

            log_dict['LogTime'] = log_dict['LogTime'].isoformat()

            history.append(log_dict)

        json_result = json.dumps(history)
        return jsonify(json_result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_expiration_date():
    # Get the current year
    current_year = datetime.now().year

    # Generate a random year between the current year and the next 10 years
    expiration_year = random.randint(current_year, current_year + 10)

    # Generate a random month
    expiration_month = random.randint(1, 12)

    # If the expiration month is February, limit the expiration day to 28
    if expiration_month == 2:
        expiration_day = random.randint(1, 28)
    # For other months, set the maximum day to 30 or 31 depending on the month
    elif expiration_month in [4, 6, 9, 11]:
        expiration_day = random.randint(1, 30)
    else:
        expiration_day = random.randint(1, 31)

    # Create a datetime object for the expiration date
    expiration_date = datetime(expiration_year, expiration_month, expiration_day)

    # Format the expiration date as MM/YYYY
    expiration_date_formatted = expiration_date.strftime("%m-%Y")

    return expiration_date_formatted

def generate_cvv():
    return ''.join(random.choices('0123456789', k=3))

@app.route('/opencard', methods=['POST'])
@jwt_required()
def open_card():
    data = request.json
    # Validate input data
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    required_field = 'CardType'
    if required_field not in data:
        return jsonify({'error': f'Missing required field: {required_field}'}), 400

    # Generate a unique 16-digit Account Number
    card_number = str(uuid.uuid4().int)[:16]

    # Get the UserID from the JWT token
    user_id = get_jwt_identity()

    cursor.execute('SELECT * FROM Users WHERE UserID = ?', user_id)
    user = cursor.fetchone()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Extract account data
    card_holder = user[4]
    expiration = datetime.strptime(generate_expiration_date(), "%m-%Y")
    cvv = generate_cvv()
    card_type = data['CardType']
    opening_date = datetime.now()
    issued = "AAWCLBank"
    card_status = 'OnHold'

    cursor.execute('INSERT INTO Creditcard (CardNumber, CardHolder, ExpirationDate, OpeningDate, Cvv, CardType, IssuedBy, CardStatus, UserID) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
                , card_number, card_holder, expiration, opening_date, cvv, card_type, issued, card_status, user_id)
    conn.commit()
    return jsonify({'message': 'Credit card created successfully'}), 201

@app.route('/cardstatus', methods=['POST'])
@jwt_required()
def card_status():
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    user_id = get_jwt_identity()
    card_number = data['CardNumber']
    cursor.execute('SELECT * FROM CreditCard WHERE UserID = ? AND CardNumber = ?', user_id, card_number)
    card = cursor.fetchone()
    if not card:
        return jsonify({'error': 'Card not found'}), 404
    cursor.execute('UPDATE CreditCard SET CardStatus = ? WHERE CardNumber = ?', data['CardStatus'], data['CardNumber'])
    conn.commit()
    return jsonify({'message': 'Card status updated successfully!'}), 200

@app.route('/mycards', methods=['GET'])
@jwt_required()
def my_cards():
    user_id = get_jwt_identity()
    cursor.execute('SELECT * FROM Users WHERE UserID = ?', user_id)
    user = cursor.fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    cursor.execute('SELECT * FROM CreditCard WHERE UserID = ?', user_id)
    cards = cursor.fetchall()
    if not cards:
        return jsonify({'error': 'No cards exist'}), 404
    result_list = []
    for card in cards:
        card_dict = {
            'CardNumber': card[0],
            'CardHolder': card[1],
            'ExpirationDate': card[2],
                'CardType': card[5],
            'Balance': float(card[7]),
            'CardStatus': card[8]
        }
        result_list.append(card_dict)
    json_result = json.dumps(result_list)
    return jsonify(json_result), 200

if __name__ == '__main__':
    app.run(debug=False)