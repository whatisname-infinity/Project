from flask import Flask, render_template, request, session, redirect, url_for, flash
from flask_pymongo import PyMongo 
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_manager, LoginManager
from flask_login import login_required, current_user
from bson.objectid import ObjectId # Needed to handle MongoDB's unique IDs
from datetime import datetime
import json
import logging
import os

# Set up logging for better debugging
logging.basicConfig(level=logging.INFO)

# --- Configuration & Initialization ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_default_key")

# MongoDB Connection Configuration
app.config["MONGO_URI"] = "mongodb://mongo:27017/farmers"
mongo = PyMongo(app)

# Flask-Login Setup
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Custom MongoDB User Class for Flask-Login ---
class MongoUser(UserMixin):
    def __init__(self, user_data):
        # We use the MongoDB _id as the Flask-Login id (must be string)
        self.id = str(user_data['_id'])
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.password = user_data.get('password')
    
    def get_id(self):
        return self.id

@login_manager.user_loader
def load_user(user_id):
    try:
        # Query MongoDB using the string ID converted to an ObjectId
        user_data = mongo.db.user.find_one({'_id': ObjectId(user_id)})
        if user_data:
            return MongoUser(user_data)
        return None
    except Exception as e:
        logging.error(f"Error loading user {user_id}: {e}")
        return None

# --- Application-Level Trigger Mimicry ---
def log_trigger_action(reference_id, action):
    # Logs action using the MongoDB _id or rid as the reference_id
    mongo.db.trig.insert_one({
        'fid': str(reference_id),
        'action': action,
        'timestamp': datetime.utcnow()
    })


# --- Helper Function for AUTO_INCREMENT emulation ---
def get_next_rid():
    # Find the max 'rid' and increment it. Defaults to 1 if no records exist.
    last_farmer = mongo.db.register.find_one(sort=[('rid', -1)])
    return (last_farmer['rid'] + 1) if last_farmer and 'rid' in last_farmer else 1


# --- Routes ---

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/farmerdetails')
@login_required
def farmerdetails():
    query = list(mongo.db.register.find())
    return render_template('farmerdetails.html', query=query)

@app.route('/agroproducts')
def agroproducts():
    query = list(mongo.db.addagroproducts.find())
    return render_template('agroproducts.html', query=query)

@app.route('/addagroproduct',methods=['POST','GET'])
@login_required
def addagroproduct():
    if request.method=="POST":
        username=request.form.get('username')
        email=request.form.get('email')
        productname=request.form.get('productname')
        productdesc=request.form.get('productdesc')
        try:
            price=int(request.form.get('price'))
        except ValueError:
            flash("Price must be a number", "danger")
            return redirect('/addagroproduct')

        product_doc = {
            'username': username,
            'email': email,
            'productname': productname,
            'productdesc': productdesc,
            'price': price
        }
        mongo.db.addagroproducts.insert_one(product_doc)
        
        flash("Product Added","info")
        return redirect('/agroproducts')
   
    return render_template('addagroproducts.html')

@app.route('/triggers')
@login_required
def triggers():
    query = list(mongo.db.trig.find().sort('timestamp', -1))
    return render_template('triggers.html', query=query)

@app.route('/addfarming',methods=['POST','GET'])
@login_required
def addfarming():
    if request.method=="POST":
        farmingtype=request.form.get('farming')
        query=mongo.db.farming.find_one({'farmingtype': farmingtype})
        if query:
            flash("Farming Type Already Exist","warning")
            return redirect('/addfarming')
        
        mongo.db.farming.insert_one({'farmingtype': farmingtype})
        
        flash("Farming Added","success")
    return render_template('farming.html')


# UPDATED ROUTE: Accepts MongoDB's string _id (doc_id)
@app.route("/delete/<string:doc_id>",methods=['POST','GET'])
@login_required
def delete(doc_id):
    try:
        # Delete by MongoDB's primary key (_id)
        result = mongo.db.register.delete_one({'_id': ObjectId(doc_id)})
        
        if result.deleted_count == 1:
            log_trigger_action(doc_id, 'FARMER DELETED')
            flash("Slot Deleted Successful","warning")
        else:
            flash("Slot not found","danger")
            
    except Exception as e:
         logging.error(f"Error deleting record {doc_id}: {e}")
         flash("Error processing delete request.","danger")

    return redirect('/farmerdetails')


# UPDATED ROUTE: Accepts MongoDB's string _id (doc_id)
@app.route("/edit/<string:doc_id>",methods=['POST','GET'])
@login_required
def edit(doc_id):
    try:
        post_id = ObjectId(doc_id)
    except Exception:
        flash("Invalid Farmer ID","danger")
        return redirect('/farmerdetails')
        
    if request.method=="POST":
        farmername=request.form.get('farmername')
        adharnumber=request.form.get('adharnumber')
        
        try:
            age=int(request.form.get('age'))
        except ValueError:
            flash("Age must be a number", "danger")
            return redirect(url_for('edit', doc_id=doc_id))
            
        gender=request.form.get('gender')
        phonenumber=request.form.get('phonenumber')
        address=request.form.get('address')
        farmingtype=request.form.get('farmingtype')     
        
        update_data = {
            'farmername': farmername,
            'adharnumber': adharnumber,
            'age': age,
            'gender': gender,
            'phonenumber': phonenumber,
            'address': address,
            'farming': farmingtype
        }
        
        # Update Query: Find by _id and set new values
        result = mongo.db.register.update_one(
            {'_id': post_id},
            {'$set': update_data}
        )
        
        if result.modified_count == 1:
            # log_trigger_action uses the doc_id (ObjectId string) as the reference
            log_trigger_action(doc_id, 'FARMER UPDATED')
            flash("Slot is Updated","success")
        else:
            flash("Slot update failed or no changes made","warning")
            
        return redirect('/farmerdetails')
        
    # GET Request: Find by _id for display
    posts = mongo.db.register.find_one({'_id': post_id})
    farming = list(mongo.db.farming.find())
    
    if not posts:
        flash("Farmer record not found.","danger")
        return redirect('/farmerdetails')
        
    return render_template('edit.html',posts=posts,farming=farming)


@app.route('/signup',methods=['POST','GET'])
def signup():
    if request.method == "POST":
        username=request.form.get('username')
        email=request.form.get('email')
        password=request.form.get('password')
        
        user=mongo.db.user.find_one({'email': email})
        
        if user:
            flash("Email Already Exist","warning")
            return render_template('signup.html')

        encpassword = password # Using plain text as per your existing login logic
        
        new_user_doc = {
            'username': username,
            'email': email,
            'password': encpassword 
        }
        mongo.db.user.insert_one(new_user_doc)
        
        flash("Signup Success. Please Login","success")
        return render_template('login.html')

    return render_template('signup.html')

@app.route('/login',methods=['POST','GET'])
def login():
    if request.method == "POST":
        email=request.form.get('email')
        password=request.form.get('password')
        
        user_data = mongo.db.user.find_one({'email': email})

        if user_data:
            if user_data.get('password') == password:
                user = MongoUser(user_data)
                login_user(user)
                flash("Login Success","primary")
                return redirect(url_for('index'))
            else:
                 flash("invalid credentials","warning")
                 return render_template('login.html') 
        else:
            flash("invalid credentials","warning")
            return render_template('login.html')    

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logout SuccessFul","warning")
    return redirect(url_for('login'))


@app.route('/register',methods=['POST','GET'])
@login_required
def register():
    farming = list(mongo.db.farming.find())
    
    if request.method=="POST":
        farmername=request.form.get('farmername')
        adharnumber=request.form.get('adharnumber')
        age=request.form.get('age')
        gender=request.form.get('gender')
        phonenumber=request.form.get('phonenumber')
        address=request.form.get('address')
        farmingtype=request.form.get('farmingtype')     
        
        new_rid = get_next_rid() # Use the helper function to get next rid
        
        farmer_doc = {
            'rid': new_rid,
            'farmername': farmername,
            'adharnumber': adharnumber,
            'age': int(age),
            'gender': gender,
            'phonenumber': phonenumber,
            'address': address,
            'farming': farmingtype
        }
        
        result = mongo.db.register.insert_one(farmer_doc)
        
        # log_trigger_action uses the generated ObjectId
        log_trigger_action(result.inserted_id, 'Farmer Inserted') 
        
        flash("Your Record Has Been Saved","success")
        return redirect('/farmerdetails')
        
    return render_template('farmer.html',farming=farming)

@app.route('/test')
def test():
    try:
        mongo.db.test.find_one()
        return 'My database is Connected'
    except Exception as e:
        return f'My db is not Connected. Error: {e}'


if __name__ == "__main__":
    # Ensure MongoDB server is running before starting the app
    # This is often done externally, but added a check here for awareness
    try:
        mongo.cx.admin.command('ping')
        print("MongoDB connection is active.")
    except Exception as e:
        print(f"ERROR: Could not connect to MongoDB at startup. Ensure mongod is running. Error: {e}")
        
    app.run(debug=True, host = '0.0.0.0')
