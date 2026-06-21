import sqlite3
import requests
from tkinter import *
from tkinter import messagebox
from tkinter import ttk
from tkcalendar import DateEntry
import datetime
import os
from tkinter import simpledialog
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import seaborn as sns

# Set style for better looking charts
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")

# Database setup - SQLite3
DB_PATH = "pharmacy_management.db"

def get_db_connection():
    """Get SQLite database connection"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"Cannot connect to database: {e}")
        return None

def initialize_database():
    """Initialize SQLite database with required tables"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        # Create medicines table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT,
                generic_name TEXT,
                manufacturer TEXT,
                dosage_form TEXT,
                our_selling_price REAL,
                stock_quantity INTEGER DEFAULT 0,
                external_id TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create purchases table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_name TEXT NOT NULL,
                purchase_date DATE,
                quantity INTEGER,
                price_per_unit REAL,
                invoice_number TEXT,
                manufacture_date DATE,
                expiry_date DATE,
                batch_number TEXT,
                wholesaler_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create customers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create sales table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                total_amount REAL NOT NULL,
                sale_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                payment_method TEXT DEFAULT 'Cash',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            )
        """)
        
        # Create sale_items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sale_items (
                sale_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER,
                medicine_id INTEGER,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales (sale_id),
                FOREIGN KEY (medicine_id) REFERENCES medicines (medicine_id)
            )
        """)
        
        # Create wholesalers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wholesalers (
                wholesaler_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                contact TEXT,
                address TEXT,
                deals_with TEXT,
                id_type TEXT,
                id_proof TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert sample data for demonstration
        cursor.execute("""
            INSERT OR IGNORE INTO medicines (name, brand, generic_name, manufacturer, dosage_form, our_selling_price, stock_quantity) 
            VALUES 
            ('Paracetamol', 'Panadol', 'Acetaminophen', 'GSK', 'Tablet', 2.5, 100),
            ('Amoxicillin', 'Amoxil', 'Amoxicillin', 'Pfizer', 'Capsule', 15.0, 50),
            ('Ibuprofen', 'Advil', 'Ibuprofen', 'Pfizer', 'Tablet', 5.0, 75),
            ('Vitamin C', 'Redoxon', 'Ascorbic Acid', 'Bayer', 'Tablet', 8.0, 200),
            ('Metformin', 'Glucophage', 'Metformin', 'Merck', 'Tablet', 12.0, 60)
        """)
        
        conn.commit()
        print("✅ SQLite database tables initialized successfully!")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database initialization error: {e}")
        return False
    finally:
        conn.close()

# Initialize database on startup
initialize_database()

class WorkingPharmacyAPI:
    def __init__(self):
        self.db_path = DB_PATH
    
    def search_medicines(self, search_term):
        """Search FDA API for medicines with proper error handling"""
        try:
            print(f"🔍 Searching for: {search_term}")
            
            url = f"https://api.fda.gov/drug/label.json?search=openfda.brand_name:{search_term}&limit=5"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self._simplify_response(data)
            else:
                return {"error": f"API returned status code: {response.status_code}"}
                
        except Exception as e:
            return {"error": f"API Error: {str(e)}"}
    
    def _simplify_response(self, api_data):
        """Simplify the complex FDA API response"""
        try:
            if 'results' not in api_data or not api_data['results']:
                return {"error": "No medicines found"}
            
            simplified_meds = []
            
            for medicine in api_data['results']:
                openfda = medicine.get('openfda', {})
                
                # Extract basic medicine info
                med_info = {
                    'brand_name': openfda.get('brand_name', ['Unknown'])[0] if openfda.get('brand_name') else 'Unknown',
                    'generic_name': openfda.get('generic_name', ['Unknown'])[0] if openfda.get('generic_name') else 'Unknown',
                    'manufacturer': ', '.join(openfda.get('manufacturer_name', ['Unknown'])),
                    'dosage_form': openfda.get('route', ['Unknown'])[0] if openfda.get('route') else 'Unknown',
                    'external_id': medicine.get('id', 'Unknown')
                }
                
                simplified_meds.append(med_info)
            
            return simplified_meds
            
        except Exception as e:
            return {"error": f"Error parsing API response: {str(e)}"}
    
    def add_medicine_to_inventory(self, medicine_data, selling_price, stock_quantity):
        """Add medicine to pharmacy inventory with duplicate prevention"""
        conn = get_db_connection()
        if not conn:
            return "error"
            
        cursor = conn.cursor()
        
        try:
            # FIRST: Check if medicine already exists using external_id
            check_query = "SELECT medicine_id FROM medicines WHERE external_id = ?"
            cursor.execute(check_query, (medicine_data['external_id'],))
            existing_medicine = cursor.fetchone()
            
            if existing_medicine:
                print(f"⚠️ Medicine already exists in database! ID: {existing_medicine[0]}")
                return "exists"
            
            # SECOND: If not exists, insert new medicine
            insert_query = """
            INSERT INTO medicines (name, brand, generic_name, manufacturer, dosage_form, 
                                 our_selling_price, stock_quantity, external_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            cursor.execute(insert_query, (
                medicine_data['brand_name'],
                medicine_data['brand_name'],
                medicine_data['generic_name'],
                medicine_data['manufacturer'],
                medicine_data['dosage_form'],
                selling_price,
                stock_quantity,
                medicine_data['external_id']
            ))
            
            conn.commit()
            print("✅ New medicine added successfully!")
            return "added"
            
        except sqlite3.Error as e:
            print(f"❌ Database Error: {e}")
            return "error"
        finally:
            conn.close()

# ----------------- AI-Powered Analytics Dashboard -----------------
class SmartPharmacyAnalytics:
    def __init__(self):
        self.db_path = DB_PATH
    
    def get_sales_data(self, date_range=None):
        """Get sales data with optional date filtering"""
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = """
        SELECT s.sale_id, s.sale_date, s.total_amount, c.name as customer_name, 
               m.name as medicine_name, si.quantity, m.our_selling_price
        FROM sales s
        JOIN customers c ON s.customer_id = c.customer_id
        JOIN sale_items si ON s.sale_id = si.sale_id
        JOIN medicines m ON si.medicine_id = m.medicine_id
        """
        
        if date_range:
            start_date, end_date = date_range
            query += f" WHERE s.sale_date BETWEEN '{start_date}' AND '{end_date}'"
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty:
            df['sale_date'] = pd.to_datetime(df['sale_date'])
            df['hour'] = df['sale_date'].dt.hour
            df['day_name'] = df['sale_date'].dt.day_name()
            df['month'] = df['sale_date'].dt.month_name()
            df['date'] = df['sale_date'].dt.date
            df['week'] = df['sale_date'].dt.isocalendar().week
        
        return df
    
    def get_medicine_data(self):
        """Get medicine data for analysis"""
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = "SELECT * FROM medicines WHERE is_active = 1"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def get_purchase_data(self):
        """Get purchase data for expiry analysis"""
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = "SELECT * FROM purchases"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty and 'expiry_date' in df.columns:
            df['expiry_date'] = pd.to_datetime(df['expiry_date'])
            df['days_until_expiry'] = (df['expiry_date'] - pd.Timestamp.now()).dt.days
        
        return df
    
    def get_customer_data(self):
        """Get customer purchase patterns"""
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = """
        SELECT c.customer_id, c.name, COUNT(s.sale_id) as visit_count, 
               SUM(s.total_amount) as total_spent, MAX(s.sale_date) as last_visit
        FROM customers c
        LEFT JOIN sales s ON c.customer_id = s.customer_id
        GROUP BY c.customer_id, c.name
        HAVING visit_count > 0
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df

    # AI-Powered Features
    def predict_sales_trend(self):
        """AI: Predict sales trend for next 7 days"""
        sales_data = self.get_sales_data()
        if sales_data.empty:
            return "Insufficient data for prediction"
        
        # Simple trend analysis (can be enhanced with ML models)
        daily_sales = sales_data.groupby('date')['total_amount'].sum()
        if len(daily_sales) < 3:
            return "Need more data for accurate prediction"
        
        avg_growth = daily_sales.pct_change().mean()
        if pd.isna(avg_growth):
            avg_growth = 0.05  # Default 5% growth
        
        last_sales = daily_sales.iloc[-1]
        prediction = last_sales * (1 + avg_growth)
        
        return f"📈 Predicted next day sales: Rs {prediction:,.2f} ({(avg_growth*100):.1f}% growth trend)"

    def smart_restock_recommendation(self):
        """AI: Smart restock recommendations based on sales velocity"""
        sales_data = self.get_sales_data()
        medicine_data = self.get_medicine_data()
        
        if sales_data.empty or medicine_data.empty:
            return "Insufficient data for recommendations"
        
        # Calculate sales velocity (units sold per day)
        sales_velocity = sales_data.groupby('medicine_name')['quantity'].sum()
        days_covered = (sales_data['sale_date'].max() - sales_data['sale_date'].min()).days
        if days_covered == 0:
            days_covered = 1
        
        daily_velocity = sales_velocity / days_covered
        
        recommendations = []
        for med in medicine_data.itertuples():
            if med.stock_quantity <= 10:
                urgency = "🚨 URGENT"
            elif med.stock_quantity <= 20:
                urgency = "⚠️ SOON"
            else:
                urgency = "💡 PLANNED"
            
            velocity = daily_velocity.get(med.name, 0)
            days_remaining = med.stock_quantity / velocity if velocity > 0 else 999
            
            if days_remaining < 7:
                recommendations.append(f"{urgency} Restock {med.name} - {med.stock_quantity} left (~{days_remaining:.1f} days)")
        
        return recommendations if recommendations else ["✅ All medicines have sufficient stock"]

    def customer_retention_insights(self):
        """AI: Customer retention and loyalty insights"""
        customer_data = self.get_customer_data()
        if customer_data.empty:
            return "No customer data available"
        
        avg_visits = customer_data['visit_count'].mean()
        top_customers = customer_data.nlargest(3, 'total_spent')
        
        insights = [
            f"👥 Average customer visits: {avg_visits:.1f}",
            f"💰 Top 3 customers by spending:"
        ]
        
        for cust in top_customers.itertuples():
            insights.append(f"   • {cust.name}: Rs {cust.total_spent:,.2f} ({cust.visit_count} visits)")
        
        return insights

    def seasonal_trend_analysis(self):
        """AI: Analyze seasonal trends in medicine sales"""
        sales_data = self.get_sales_data()
        if sales_data.empty:
            return "No sales data for seasonal analysis"
        
        monthly_sales = sales_data.groupby(sales_data['sale_date'].dt.month)['total_amount'].sum()
        if len(monthly_sales) < 2:
            return "Need more data for seasonal analysis"
        
        peak_month = monthly_sales.idxmax()
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        return f"📊 Peak sales month: {month_names[peak_month-1]} (Rs {monthly_sales.max():,.2f})"



# ----------------- Analytics Dashboard Functions -----------------
class PharmacyAnalytics:
    def __init__(self):
        self.db_path = DB_PATH
    
    def get_sales_data(self):
        """Get sales data for analysis"""
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = """
        SELECT s.sale_id, s.sale_date, s.total_amount, c.name as customer_name, 
               m.name as medicine_name, si.quantity
        FROM sales s
        JOIN customers c ON s.customer_id = c.customer_id
        JOIN sale_items si ON s.sale_id = si.sale_id
        JOIN medicines m ON si.medicine_id = m.medicine_id
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty:
            df['sale_date'] = pd.to_datetime(df['sale_date'])
            df['hour'] = df['sale_date'].dt.hour
            df['day_name'] = df['sale_date'].dt.day_name()
            df['month'] = df['sale_date'].dt.month_name()
        
        return df
    
    def get_medicine_data(self):
        """Get medicine data for analysis"""
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = "SELECT * FROM medicines WHERE is_active = 1"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def get_purchase_data(self):
        """Get purchase data for expiry analysis"""
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = "SELECT * FROM purchases"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty and 'expiry_date' in df.columns:
            df['expiry_date'] = pd.to_datetime(df['expiry_date'])
            df['days_until_expiry'] = (df['expiry_date'] - pd.Timestamp.now()).dt.days
        
        return df
    
    def get_customer_data(self):
        """Get customer purchase patterns"""
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = """
        SELECT c.customer_id, c.name, COUNT(s.sale_id) as visit_count, 
               SUM(s.total_amount) as total_spent, MAX(s.sale_date) as last_visit
        FROM customers c
        LEFT JOIN sales s ON c.customer_id = s.customer_id
        GROUP BY c.customer_id, c.name
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df

# ----------------- Custom Gradient Scrollbar -----------------
class GradientScrollbar(Canvas):
    def __init__(self, parent, target, orient='vertical', width=14, height=14,
                 gradient_colors=None, **kwargs):
        self.set = lambda first, last: None
        self.parent = parent
        self.target = target
        self.orient = orient
        if gradient_colors is None:
            gradient_colors = ['#20C997', '#17A2B8', '#008080']
        self.gradient_colors = gradient_colors
        if orient == 'vertical':
            Canvas.__init__(self, parent, width=width, highlightthickness=0, **kwargs)
            self.config(cursor='hand2')
        else:
            Canvas.__init__(self, parent, height=height, highlightthickness=0, **kwargs)
            self.config(cursor='hand2')
        self._dragging = False
        self.bind("<Button-1>", self.click)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)
        self.bind("<Enter>", lambda e: self.target.bind_all("<MouseWheel>", self._on_wheel))
        self.bind("<Leave>", lambda e: self.target.unbind_all("<MouseWheel>"))
        self.draw_gradient()

    def draw_gradient(self):
        self.delete("all")
        if self.orient == 'vertical':
            h = self.winfo_height() or 200
            w = self.winfo_width() or 14
            for i in range(h):
                t = i / max(1, h - 1)
                color = self._interp_color(t)
                self.create_line(0, i, w, i, fill=color)
        else:
            w = self.winfo_width() or 200
            h = self.winfo_height() or 14
            for i in range(w):
                t = i / max(1, w - 1)
                color = self._interp_color(t)
                self.create_line(i, 0, i, h, fill=color)

    def _on_wheel(self, event):
        if hasattr(self.target, 'yview'):
            self.target.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _interp_color(self, t):
        stops = self.gradient_colors
        n = len(stops)
        pos = t * (n - 1)
        i = int(pos)
        j = min(i + 1, n - 1)
        frac = pos - i
        c1 = stops[i].lstrip('#')
        c2 = stops[j].lstrip('#')
        r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
        r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
        r = int(r1 + (r2 - r1) * frac)
        g = int(g1 + (g2 - g1) * frac)
        b = int(b1 + (b2 - b1) * frac)
        return f'#{r:02x}{g:02x}{b:02x}'

    def click(self, event):
        self._dragging = True
        self.move_to_event(event)

    def drag(self, event):
        if self._dragging:
            self.move_to_event(event)

    def release(self, event):
        self._dragging = False

    def move_to_event(self, event):
        if self.orient == 'vertical':
            h = self.winfo_height() or 1
            y = max(0, min(event.y, h))
            frac = y / max(1, h)
            try:
                self.target.yview_moveto(frac)
            except Exception:
                pass
        else:
            w = self.winfo_width() or 1
            x = max(0, min(event.x, w))
            frac = x / max(1, w)
            try:
                self.target.xview_moveto(frac)
            except Exception:
                pass

# ----------------- MAIN WINDOW -----------------
root = Tk()
root.geometry("1200x700")
root.title("Wellora Pharmacy System")
root.configure(bg="#F0F8FF")

# Header
header = Frame(root, bg="#FFF5BA")
header.pack(fill="x")

title_lbl = Label(header, text="WELLORA PHARMACY SYSTEM 🌿",
                  bg="#FFF5BA", fg="#087f5b", font=('Arial', 22, 'bold italic'))
title_lbl.pack(padx=20, pady=10)

time_lbl = Label(header, bg="#FFF5BA", fg="#3A3A3A", font=('Arial', 16, 'italic'))
time_lbl.pack(side="right", padx=20)

def update_time_main():
    time_lbl.config(text=datetime.datetime.now().strftime("%H:%M:%S"))
    root.after(1000, update_time_main)
update_time_main()

# Tagline
tag = Label(root, text="Your Health, Our Priority", bg="#F25C54",
            fg="white", font=('Arial', 20, 'bold italic'))
tag.pack(fill="x", pady=6)

# Login Frame (centered)
login_frame = Frame(root, bg="#F0F8FF", padx=30, pady=25, highlightbackground="#C3C3C3", highlightthickness=2)
login_frame.pack(expand=True)

Label(login_frame, text="Login Page", bg="#F0F8FF",
      fg="#333", font=('Arial', 20, 'bold')).grid(row=0, column=0, columnspan=2, pady=(0, 15))

role = StringVar(value="None")
def set_role(selected):
    role.set(selected)
    if selected == "Employee":
        login_frame.config(bg="#E6F4EA")
        header.config(bg="#B9F3B5")
        title_lbl.config(bg="#B9F3B5")
        time_lbl.config(bg="#B9F3B5")
        employee_btn.config(bg="#00A36C", fg="white", relief="sunken")
        admin_btn.config(bg="#E0E0E0", fg="black", relief="raised")
    elif selected == "Admin":
        login_frame.config(bg="#FFE6CC")
        header.config(bg="#FFD8A9")
        title_lbl.config(bg="#FFD8A9")
        time_lbl.config(bg="#FFD8A9")
        admin_btn.config(bg="#E67E22", fg="white", relief="sunken")
        employee_btn.config(bg="#E0E0E0", fg="black", relief="raised")

employee_btn = Button(login_frame, text="Employee", width=12, font=('Arial', 12, 'bold'),
                      bg="#E0E0E0", command=lambda: set_role("Employee"))
employee_btn.grid(row=1, column=0, padx=10, pady=10)

admin_btn = Button(login_frame, text="Admin", width=12, font=('Arial', 12, 'bold'),
                   bg="#E0E0E0", command=lambda: set_role("Admin"))
admin_btn.grid(row=1, column=1, padx=10, pady=10)

Label(login_frame, text="Enter Details Below",
      bg="#F0F8FF", fg="#333", font=('Arial', 14, 'bold italic')).grid(row=2, column=0, columnspan=2, pady=(20, 10))

Label(login_frame, text="Username:", bg="#F0F8FF", font=('Arial', 12)).grid(row=3, column=0, pady=5, sticky="e")
username_entry = Entry(login_frame, width=25, font=('Arial', 12))
username_entry.grid(row=3, column=1, pady=5)

Label(login_frame, text="Password:", bg="#F0F8FF", font=('Arial', 12)).grid(row=4, column=0, pady=5, sticky="e")
password_entry = Entry(login_frame, width=25, font=('Arial', 12), show="*")
password_entry.grid(row=4, column=1, pady=5)

# credentials
valid_credentials = {
    "Employee": [{"username": f"emp{i}", "password": f"pass{i}"} for i in range(1, 6)],
    "Admin": [{"username": f"admin{i}", "password": f"admin{i}"} for i in range(1, 6)]
}

# ---------- Admin Portal ----------
def open_admin_portal(username):
    adm = Toplevel(root)
    adm.title("Wellora - Admin Dashboard")
    adm.geometry("1300x800")
    adm.configure(bg="#FFEEDB")

    Label(adm, text=f"Admin Portal — {username}",
          bg="#FFD8A9", fg="#E67E22",
          font=('Arial', 22, 'bold italic'), pady=10).pack(fill="x")

    # main_frame contains sidebar + content
    main_frame = Frame(adm, bg="#FFEEDB")
    main_frame.pack(fill="both", expand=True)

    # ---------------- SIDEBAR ----------------
    sidebar_container = Frame(main_frame, bg="#FFD8A9", width=280)
    sidebar_container.pack(side="left", fill="y")

    sidebar_canvas = Canvas(sidebar_container, bg="#FFD8A9", highlightthickness=0)
    sidebar_scrollbar = Scrollbar(sidebar_container, orient="vertical", command=sidebar_canvas.yview)
    sidebar_canvas.configure(yscrollcommand=sidebar_scrollbar.set)

    scrollable_frame = Frame(sidebar_canvas, bg="#FFD8A9")
    scrollable_frame.bind(
        "<Configure>",
        lambda e: sidebar_canvas.configure(scrollregion=sidebar_canvas.bbox("all"))
    )
    sidebar_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    sidebar_canvas.pack(side="left", fill="y", expand=True)
    sidebar_scrollbar.pack(side="right", fill="y")

    def sidebar_mouse_enter(e):
        sidebar_canvas.bind_all("<MouseWheel>", on_sidebar_wheel)

    def sidebar_mouse_leave(e):
        sidebar_canvas.unbind_all("<MouseWheel>")

    def on_sidebar_wheel(event):
        sidebar_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    scrollable_frame.bind("<Enter>", sidebar_mouse_enter)
    scrollable_frame.bind("<Leave>", sidebar_mouse_leave)

    # ---------------- CONTENT ----------------
    content = Frame(main_frame, bg="#FFF8E1", relief="ridge", bd=2)
    content.pack(side="right", fill="both", expand=True)

    Label(content, text="Welcome to Admin Dashboard 👋",
          bg="#FFF8E1", fg="#E67E22", font=('Arial', 20, 'bold')).pack(pady=30)

    # sidebar hover effects
    def on_enter(e):
        e.widget['bg'] = "#E67E22"
        e.widget['fg'] = "white"

    def on_leave(e):
        if e.widget['text'] != "Logout":
            e.widget['bg'] = "#FFD8A9"
            e.widget['fg'] = "#4A4A4A"
        else:
            e.widget['bg'] = "#F25C54"
            e.widget['fg'] = "white"

    # ---------------- ANALYTICAL DASHBOARD SECTION ----------------
    def analytical_dashboard_section(parent):
        for widget in parent.winfo_children():
            widget.destroy()
        
        heading = Label(parent, text="📊 ANALYTICAL DASHBOARD", bg="#00A36C", fg="white",
                        font=('Arial', 18, 'bold'))
        heading.pack(fill="x", pady=(0, 8))

        # Create analytics instance
        analytics = PharmacyAnalytics()
        
        # Main container with scrollbar
        main_container = Frame(parent, bg="#F0F8FF")
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Canvas for scrolling
        canvas = Canvas(main_container, bg="#F0F8FF", highlightthickness=0)
        scrollbar = Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollable_frame = Frame(canvas, bg="#F0F8FF")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def create_chart_frame(title, row, col):
            frame = Frame(scrollable_frame, bg="white", relief="ridge", bd=2)
            frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            Label(frame, text=title, bg="white", fg="#333", 
                  font=('Arial', 12, 'bold')).pack(pady=5)
            return frame

        # Configure grid weights
        for i in range(3):
            scrollable_frame.grid_columnconfigure(i, weight=1)
        for i in range(4):
            scrollable_frame.grid_rowconfigure(i, weight=1)

        # Chart 1: Sales Over Time
        try:
            sales_data = analytics.get_sales_data()
            if not sales_data.empty:
                fig1, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
                
                # Daily sales trend
                daily_sales = sales_data.groupby(sales_data['sale_date'].dt.date)['total_amount'].sum()
                ax1.plot(daily_sales.index, daily_sales.values, marker='o', linewidth=2, color='#FF6B6B')
                ax1.set_title('Daily Sales Trend', fontsize=12, fontweight='bold')
                ax1.set_xlabel('Date')
                ax1.set_ylabel('Total Sales (Rs)')
                ax1.tick_params(axis='x', rotation=45)
                
                # Sales by hour
                hourly_sales = sales_data.groupby('hour')['total_amount'].sum()
                ax2.bar(hourly_sales.index, hourly_sales.values, color='#4ECDC4', alpha=0.7)
                ax2.set_title('Sales by Hour of Day', fontsize=12, fontweight='bold')
                ax2.set_xlabel('Hour')
                ax2.set_ylabel('Total Sales (Rs)')
                
                plt.tight_layout()
                
                chart_frame1 = create_chart_frame("Sales Analysis", 0, 0)
                canvas1 = FigureCanvasTkAgg(fig1, chart_frame1)
                canvas1.draw()
                canvas1.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
            else:
                no_data_frame = create_chart_frame("Sales Analysis", 0, 0)
                Label(no_data_frame, text="No sales data available", bg="white").pack(expand=True)
        except Exception as e:
            print(f"Error creating sales chart: {e}")

        # Chart 2: Top Selling Medicines
        try:
            if not sales_data.empty:
                top_medicines = sales_data.groupby('medicine_name')['quantity'].sum().nlargest(5)
                
                fig2, ax = plt.subplots(figsize=(8, 4))
                colors = ['#FF9F1C', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
                bars = ax.barh(top_medicines.index, top_medicines.values, color=colors)
                ax.set_title('Top 5 Selling Medicines', fontsize=12, fontweight='bold')
                ax.set_xlabel('Quantity Sold')
                
                # Add value labels on bars
                for bar in bars:
                    width = bar.get_width()
                    ax.text(width, bar.get_y() + bar.get_height()/2, f'{int(width)}', 
                           ha='left', va='center', fontweight='bold')
                
                plt.tight_layout()
                
                chart_frame2 = create_chart_frame("Top Selling Medicines", 0, 1)
                canvas2 = FigureCanvasTkAgg(fig2, chart_frame2)
                canvas2.draw()
                canvas2.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
        except Exception as e:
            print(f"Error creating top medicines chart: {e}")

        # Chart 3: Customer Visit Patterns
        try:
            customer_data = analytics.get_customer_data()
            if not customer_data.empty and not customer_data['visit_count'].isna().all():
                regular_customers = customer_data.nlargest(5, 'visit_count')
                
                fig3, ax = plt.subplots(figsize=(8, 4))
                bars = ax.bar(regular_customers['name'], regular_customers['visit_count'], 
                             color=['#E67E22', '#F39C12', '#D35400', '#E74C3C', '#C0392B'])
                ax.set_title('Top 5 Regular Customers', fontsize=12, fontweight='bold')
                ax.set_ylabel('Number of Visits')
                ax.tick_params(axis='x', rotation=45)
                
                # Add value labels on bars
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{int(height)}', ha='center', va='bottom', fontweight='bold')
                
                plt.tight_layout()
                
                chart_frame3 = create_chart_frame("Customer Analysis", 0, 2)
                canvas3 = FigureCanvasTkAgg(fig3, chart_frame3)
                canvas3.draw()
                canvas3.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
        except Exception as e:
            print(f"Error creating customer chart: {e}")

        # Chart 4: Stock Status
        try:
            medicine_data = analytics.get_medicine_data()
            if not medicine_data.empty:
                low_stock = medicine_data[medicine_data['stock_quantity'] <= 10]
                
                fig4, ax = plt.subplots(figsize=(8, 4))
                if not low_stock.empty:
                    colors = ['#FF4444' if qty <= 5 else '#FFA500' for qty in low_stock['stock_quantity']]
                    bars = ax.bar(low_stock['name'], low_stock['stock_quantity'], color=colors)
                    ax.set_title('Low Stock Alert', fontsize=12, fontweight='bold', color='red')
                    ax.set_ylabel('Remaining Quantity')
                    ax.tick_params(axis='x', rotation=45)
                    
                    # Add value labels
                    for bar in bars:
                        height = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2., height,
                               f'{int(height)}', ha='center', va='bottom', fontweight='bold')
                else:
                    ax.text(0.5, 0.5, 'No Low Stock Items\n✅ All Good!', 
                           ha='center', va='center', transform=ax.transAxes, fontsize=14,
                           fontweight='bold', color='green')
                    ax.set_title('Stock Status', fontsize=12, fontweight='bold')
                
                plt.tight_layout()
                
                chart_frame4 = create_chart_frame("Stock Monitoring", 1, 0)
                canvas4 = FigureCanvasTkAgg(fig4, chart_frame4)
                canvas4.draw()
                canvas4.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
        except Exception as e:
            print(f"Error creating stock chart: {e}")

        # Chart 5: Expiry Alerts
        try:
            purchase_data = analytics.get_purchase_data()
            if not purchase_data.empty and 'days_until_expiry' in purchase_data.columns:
                expiring_soon = purchase_data[purchase_data['days_until_expiry'] <= 30]
                
                fig5, ax = plt.subplots(figsize=(8, 4))
                if not expiring_soon.empty:
                    colors = ['#FF4444' if days <= 7 else '#FFA500' for days in expiring_soon['days_until_expiry']]
                    bars = ax.bar(expiring_soon['medicine_name'], expiring_soon['days_until_expiry'], color=colors)
                    ax.set_title('Medicines Expiring Soon', fontsize=12, fontweight='bold')
                    ax.set_ylabel('Days Until Expiry')
                    ax.tick_params(axis='x', rotation=45)
                    
                    # Add value labels
                    for bar in bars:
                        height = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2., height,
                               f'{int(height)}', ha='center', va='bottom', fontweight='bold')
                else:
                    ax.text(0.5, 0.5, 'No Expiring Medicines\n✅ All Good!', 
                           ha='center', va='center', transform=ax.transAxes, fontsize=14,
                           fontweight='bold', color='green')
                    ax.set_title('Expiry Status', fontsize=12, fontweight='bold')
                
                plt.tight_layout()
                
                chart_frame5 = create_chart_frame("Expiry Monitoring", 1, 1)
                canvas5 = FigureCanvasTkAgg(fig5, chart_frame5)
                canvas5.draw()
                canvas5.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
        except Exception as e:
            print(f"Error creating expiry chart: {e}")

        # Chart 6: Sales by Day of Week
        try:
            if not sales_data.empty:
                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                sales_by_day = sales_data.groupby('day_name')['total_amount'].sum().reindex(day_order, fill_value=0)
                
                fig6, ax = plt.subplots(figsize=(8, 4))
                bars = ax.bar(sales_by_day.index, sales_by_day.values, 
                             color=['#45B7D1', '#96CEB4', '#FECA57', '#FF9FF3', '#54A0FF', '#5F27CD', '#00D2D3'])
                ax.set_title('Sales by Day of Week', fontsize=12, fontweight='bold')
                ax.set_ylabel('Total Sales (Rs)')
                ax.tick_params(axis='x', rotation=45)
                
                plt.tight_layout()
                
                chart_frame6 = create_chart_frame("Weekly Patterns", 1, 2)
                canvas6 = FigureCanvasTkAgg(fig6, chart_frame6)
                canvas6.draw()
                canvas6.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
        except Exception as e:
            print(f"Error creating weekly chart: {e}")

        # Refresh button
        refresh_btn = Button(scrollable_frame, text="🔄 Refresh Dashboard", 
                           bg="#3498DB", fg="white", font=('Arial', 12, 'bold'),
                           command=lambda: analytical_dashboard_section(parent))
        refresh_btn.grid(row=2, column=0, columnspan=3, pady=20)

    # ---------------- PURCHASES SECTION (Updated with Calendar and Expiry Alerts) ----------------
    def purchases_section(parent):
        for widget in parent.winfo_children():
            widget.destroy()
        heading = Label(parent, text="PURCHASES SECTION", bg="#00A36C", fg="white",
                        font=('Arial', 18, 'bold'))
        heading.pack(fill="x", pady=(0, 8))

        body = Frame(parent, bg="#F0F8FF")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        left = Frame(body, bg="#E6F4EA", bd=2, relief="ridge")
        left.pack(side="left", fill="y", padx=8, pady=8)

        Label(left, text="Manage Purchases", bg="#E6F4EA", fg="#087f5b", font=('Arial', 14, 'bold')).pack(pady=10)

        fields = ["Medicine Name", "Date of Purchase", "Quantity", "Price per Unit",
                  "Invoice Number", "Manufacture Date", "Expiry Date", "Batch No", "Wholesaler No"]
        entries = {}

        for f in fields:
            row = Frame(left, bg="#E6F4EA")
            row.pack(fill="x", padx=12, pady=4)
            Label(row, text=f + ":", bg="#E6F4EA", width=18, anchor="w",
                  font=('Arial', 11, 'bold')).pack(side="left")
            if f in ["Date of Purchase", "Manufacture Date", "Expiry Date"]:
                e = DateEntry(row, width=20, background='darkblue', foreground='white', 
                             borderwidth=2, date_pattern='yyyy-mm-dd')
                e.set_date(datetime.date.today())
            else:
                e = Entry(row, width=22, font=('Arial', 11))
            e.pack(side="left", padx=5)
            entries[f] = e

        btn_frame = Frame(left, bg="#E6F4EA")
        btn_frame.pack(pady=12)
        btn_style = {"font": ('Arial', 11, 'bold'), "width": 14, "height": 1}

        # Right: Table with vertical + horizontal scrollbars and search
        right = Frame(body, bg="#FFF5BA", bd=2, relief="ridge")
        right.pack(side="right", fill="both", expand=True, padx=8, pady=8)
        Label(right, text="Purchase Records", bg="#FFF5BA", fg="#2E8B57", font=('Arial', 14, 'bold')).pack(pady=8)

        # Search and Alert Frame
        search_frame = Frame(right, bg="#FFF5BA")
        search_frame.pack(fill="x", padx=10, pady=5)
        
        Label(search_frame, text="Search:", bg="#FFF5BA").pack(side="left", padx=(0,6))
        purchases_search_var = StringVar()
        purchases_search_entry = Entry(search_frame, textvariable=purchases_search_var, width=30)
        purchases_search_entry.pack(side="left", padx=(0,6))

        # Expiry Alert Button with real functionality
        def check_expiry_alerts():
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            
            # Check for medicines expiring within 30 days
            cursor.execute("""
                SELECT medicine_name, expiry_date, batch_number,
                julianday(expiry_date) - julianday('now') as days_remaining 
                FROM purchases 
                WHERE expiry_date BETWEEN date('now') AND date('now', '+30 days')
                ORDER BY expiry_date
            """)
            
            expiring_meds = cursor.fetchall()
            conn.close()
            
            if not expiring_meds:
                messagebox.showinfo("Expiry Alerts", "✅ No medicines expiring within 30 days!")
                return
            
            # Create detailed alert window
            alert_win = Toplevel(adm)
            alert_win.title("⚠️ MEDICINE EXPIRY ALERTS")
            alert_win.geometry("600x400")
            alert_win.configure(bg="#FFE6E6")
            
            Label(alert_win, text="🚨 MEDICINES EXPIRING SOON!", 
                  bg="#FF4444", fg="white", font=('Arial', 16, 'bold')).pack(fill="x", pady=10)
            
            # Create treeview for expiring medicines
            cols = ("Medicine", "Expiry Date", "Batch No", "Days Remaining", "Status")
            tree = ttk.Treeview(alert_win, columns=cols, show="headings", height=15)
            
            for col in cols:
                tree.heading(col, text=col)
                tree.column(col, width=120)
            
            # Add data with color coding
            for med in expiring_meds:
                days_left = int(med[3]) if med[3] else 0
                if days_left <= 7:
                    status = "CRITICAL"
                    tag = "critical"
                elif days_left <= 15:
                    status = "HIGH ALERT"
                    tag = "warning"
                else:
                    status = "ALERT"
                    tag = "alert"
                
                tree.insert("", "end", values=(
                    med[0], med[1], med[2], f"{days_left} days", status
                ), tags=(tag,))
            
            # Configure tags for colors
            tree.tag_configure("critical", background="#FFB3B3")  # Red
            tree.tag_configure("warning", background="#FFE0B3")   # Orange
            tree.tag_configure("alert", background="#FFFFB3")     # Yellow
            
            tree.pack(fill="both", expand=True, padx=10, pady=10)
            
            Label(alert_win, text="🚨 Red: <7 days | 🟠 Orange: <15 days | 🟡 Yellow: <30 days",
                  bg="#FFE6E6", fg="#333", font=('Arial', 10, 'bold')).pack(pady=5)

        Button(search_frame, text="🚨 Check Expiry Alerts", bg="#FF4444", fg="white",
               font=('Arial', 10, 'bold'), command=check_expiry_alerts).pack(side="right", padx=10)

        table_frame = Frame(right)
        table_frame.pack(fill="both", expand=True, padx=10, pady=8)

        cols = ("Medicine", "Date", "Qty", "Price", "Invoice", "Mfg", "Exp", "Batch", "Wholesaler")
        purchases_tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        for col in cols:
            purchases_tree.heading(col, text=col)
            purchases_tree.column(col, width=120, anchor="center")

        # Scrollbars
        vsb_frame = Frame(table_frame)
        vsb_frame.pack(side="right", fill="y")
        custom_v = GradientScrollbar(vsb_frame, target=purchases_tree, orient='vertical', width=16)
        custom_v.pack(fill="y", expand=True)

        hsb_frame = Frame(table_frame)
        hsb_frame.pack(side="bottom", fill="x")
        custom_h = GradientScrollbar(hsb_frame, target=purchases_tree, orient='horizontal', height=16)
        custom_h.pack(fill="x")

        purchases_tree.pack(fill="both", expand=True)

        def clear_form():
            for f, e in entries.items():
                if f in ["Date of Purchase", "Manufacture Date", "Expiry Date"]:
                    e.set_date(datetime.date.today())
                else:
                    e.delete(0, END)

        def refresh_purchases():
            for item in purchases_tree.get_children():
                purchases_tree.delete(item)
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT medicine_name, purchase_date, quantity, price_per_unit, invoice_number, manufacture_date, expiry_date, batch_number, wholesaler_id FROM purchases ORDER BY purchase_date DESC")
            
            for purchase in cursor.fetchall():
                purchase_data = tuple(purchase)
                purchases_tree.insert("", "end", values=purchase_data)
            
            conn.close()

        def add_purchase():
            medicine_name = entries["Medicine Name"].get().strip()
            purchase_date = entries["Date of Purchase"].get()
            quantity = entries["Quantity"].get()
            price_per_unit = entries["Price per Unit"].get()
            invoice_number = entries["Invoice Number"].get().strip()
            manufacture_date = entries["Manufacture Date"].get()
            expiry_date = entries["Expiry Date"].get()
            batch_number = entries["Batch No"].get().strip()
            wholesaler_id = entries["Wholesaler No"].get().strip()
            
            if not medicine_name:
                messagebox.showerror("Error", "Medicine Name is required!")
                return
            try:
                quantity = int(quantity)
                price_per_unit = float(price_per_unit)
            except ValueError:
                messagebox.showerror("Error", "Quantity and Price must be numbers!")
                return
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO purchases (medicine_name, purchase_date, quantity, price_per_unit, 
                invoice_number, manufacture_date, expiry_date, batch_number, wholesaler_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (medicine_name, purchase_date, quantity, price_per_unit, invoice_number, 
                 manufacture_date, expiry_date, batch_number, wholesaler_id)
            )
            
            # Update medicine stock - FIXED STOCK DEDUCTION ISSUE
            cursor.execute("SELECT medicine_id FROM medicines WHERE name = ?", (medicine_name,))
            medicine = cursor.fetchone()
            
            if medicine:
                # Medicine exists, update stock
                cursor.execute(
                    "UPDATE medicines SET stock_quantity = stock_quantity + ? WHERE name = ?",
                    (quantity, medicine_name)
                )
            else:
                # Medicine doesn't exist, insert new
                cursor.execute(
                    "INSERT INTO medicines (name, stock_quantity, our_selling_price) VALUES (?, ?, ?)",
                    (medicine_name, quantity, price_per_unit * 1.2)
                )
            
            conn.commit()
            conn.close()
            
            refresh_purchases()
            clear_form()
            messagebox.showinfo("Success", "Purchase added successfully and stock updated!")

        def delete_purchase():
            sel = purchases_tree.selection()
            if not sel:
                messagebox.showwarning("Select Row", "Select a row to delete")
                return
            
            item = purchases_tree.item(sel[0])
            purchase_data = item['values']
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM purchases WHERE medicine_name = ? AND purchase_date = ? AND invoice_number = ?",
                (purchase_data[0], purchase_data[1], purchase_data[4])
            )
            conn.commit()
            conn.close()
            
            refresh_purchases()
            messagebox.showinfo("Deleted", "Purchase record deleted!")

        def update_purchase():
            sel = purchases_tree.selection()
            if not sel:
                messagebox.showwarning("Select Row", "Select a row to update")
                return
            
            item = purchases_tree.item(sel[0])
            old_data = item['values']
            
            entries["Medicine Name"].delete(0, END)
            entries["Medicine Name"].insert(0, old_data[0])
            
            try:
                purchase_date = datetime.datetime.strptime(old_data[1], "%Y-%m-%d").date()
                entries["Date of Purchase"].set_date(purchase_date)
            except:
                entries["Date of Purchase"].set_date(datetime.date.today())
            
            entries["Quantity"].delete(0, END)
            entries["Quantity"].insert(0, str(old_data[2]))
            
            entries["Price per Unit"].delete(0, END)
            entries["Price per Unit"].insert(0, str(old_data[3]))
            
            entries["Invoice Number"].delete(0, END)
            entries["Invoice Number"].insert(0, old_data[4])
            
            if len(old_data) > 5 and old_data[5]:
                try:
                    mfg_date = datetime.datetime.strptime(old_data[5], "%Y-%m-%d").date()
                    entries["Manufacture Date"].set_date(mfg_date)
                except:
                    pass
            
            if len(old_data) > 6 and old_data[6]:
                try:
                    exp_date = datetime.datetime.strptime(old_data[6], "%Y-%m-%d").date()
                    entries["Expiry Date"].set_date(exp_date)
                except:
                    pass
            
            if len(old_data) > 7:
                entries["Batch No"].delete(0, END)
                entries["Batch No"].insert(0, old_data[7] if old_data[7] else "")
            
            if len(old_data) > 8:
                entries["Wholesaler No"].delete(0, END)
                entries["Wholesaler No"].insert(0, old_data[8] if old_data[8] else "")

        def _on_purchases_search(*args):
            query = purchases_search_var.get().strip().lower()
            for item in purchases_tree.get_children():
                purchases_tree.delete(item)
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT medicine_name, purchase_date, quantity, price_per_unit, invoice_number, manufacture_date, expiry_date, batch_number, wholesaler_id FROM purchases")
            
            for purchase in cursor.fetchall():
                purchase_data = tuple(purchase)
                if query == "" or any(query in str(field).lower() for field in purchase_data):
                    purchases_tree.insert("", "end", values=purchase_data)
            
            conn.close()

        purchases_search_var.trace_add("write", _on_purchases_search)

        Button(btn_frame, text="Add Purchase", bg="#3AA6B9", fg="white",
               command=add_purchase, **btn_style).grid(row=0, column=0, padx=6, pady=4)
        Button(btn_frame, text="Delete Purchase", bg="#F25C54", fg="white",
               command=delete_purchase, **btn_style).grid(row=0, column=1, padx=6, pady=4)
        Button(btn_frame, text="Update Purchase", bg="#00A36C", fg="white",
               command=update_purchase, **btn_style).grid(row=1, column=0, padx=6, pady=4)
        Button(btn_frame, text="Clear Form", bg="#FFD8A9", fg="#333",
               command=clear_form, **btn_style).grid(row=1, column=1, padx=6, pady=4)

        refresh_purchases()

    # ---------------- INVENTORY SECTION ----------------
    def inventory_section(parent):
        for widget in parent.winfo_children():
            widget.destroy()
        heading = Label(parent, text="INVENTORY SECTION", bg="#00A36C", fg="white", font=('Arial', 18, 'bold'))
        heading.pack(fill="x", pady=(0, 8))
        body = Frame(parent, bg="#F0F8FF")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        left = Frame(body, bg="#E6F4EA", bd=2, relief="ridge")
        left.pack(side="left", fill="y", padx=8, pady=8)

        Label(left, text="Manage Inventory", bg="#E6F4EA", fg="#087f5b", font=('Arial', 14, 'bold')).pack(pady=10)
        fields = ["Medicine Name", "Quantity", "Cost"]
        entries = {}
        for f in fields:
            row = Frame(left, bg="#E6F4EA")
            row.pack(fill="x", padx=15, pady=5)
            Label(row, text=f + ":", bg="#E6F4EA", width=15, anchor="w",
                  font=('Arial', 11, 'bold')).pack(side="left")
            e = Entry(row, width=25)
            e.pack(side="left", padx=5)
            entries[f] = e

        btn_frame = Frame(left, bg="#E6F4EA")
        btn_frame.pack(pady=15)
        btn_style = {"font": ('Arial', 11, 'bold'), "width": 14, "height": 1}

        right = Frame(body)
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        search_frame = Frame(right, bg="#F0F8FF")
        search_frame.pack(fill="x")
        Label(search_frame, text="Search:", bg="#F0F8FF").pack(side="left", padx=(0,6))
        inventory_search_var = StringVar()
        inventory_search_entry = Entry(search_frame, textvariable=inventory_search_var, width=30)
        inventory_search_entry.pack(side="left", padx=(0,6))

        tree_frame = Frame(right)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=8)

        cols = ("Medicine Name", "Quantity", "Cost")
        inventory_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        for col in cols:
            inventory_tree.heading(col, text=col)
            inventory_tree.column(col, width=140, anchor="center")

        vsb_frame = Frame(tree_frame)
        vsb_frame.pack(side="right", fill="y")
        custom_v = GradientScrollbar(vsb_frame, target=inventory_tree, orient='vertical', width=16)
        custom_v.pack(fill="y", expand=True)

        hsb_frame = Frame(tree_frame)
        hsb_frame.pack(side="bottom", fill="x")
        custom_h = GradientScrollbar(hsb_frame, target=inventory_tree, orient='horizontal', height=16)
        custom_h.pack(fill="x")

        inventory_tree.pack(fill="both", expand=True)

        def refresh_table():
            for item in inventory_tree.get_children():
                inventory_tree.delete(item)
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT name, stock_quantity, our_selling_price FROM medicines WHERE is_active = 1 ORDER BY stock_quantity ASC")
            
            for medicine in cursor.fetchall():
                medicine_data = tuple(medicine)
                inventory_tree.insert("", "end", values=medicine_data)
            
            conn.close()
        
        def clear_entries():
            for e in entries.values():
                e.delete(0, END)
        
        def add_item():
            name = entries["Medicine Name"].get().strip()
            qty = entries["Quantity"].get().strip()
            cost = entries["Cost"].get().strip()
            if not name or not qty or not cost:
                messagebox.showwarning("Missing Data", "Fill all fields!")
                return
            
            try:
                qty_int = int(qty)
                cost_float = float(cost)
            except ValueError:
                messagebox.showerror("Error", "Quantity and Cost must be numbers!")
                return
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO medicines (name, stock_quantity, our_selling_price) VALUES (?, ?, ?)",
                (name, qty_int, cost_float)
            )
            conn.commit()
            conn.close()
            
            refresh_table()
            clear_entries()
            messagebox.showinfo("Success", "Medicine added to inventory!")
        
        def delete_item():
            selected = inventory_tree.selection()
            if not selected:
                messagebox.showwarning("Select Row", "Select a row to delete")
                return
            
            item = inventory_tree.item(selected[0])
            medicine_name = item['values'][0]
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("UPDATE medicines SET is_active = 0 WHERE name = ?", (medicine_name,))
            conn.commit()
            conn.close()
            
            refresh_table()
            messagebox.showinfo("Deleted", "Medicine removed from inventory!")

        def update_item():
            selected = inventory_tree.selection()
            if not selected:
                messagebox.showwarning("Select Row", "Select a medicine to update")
                return
            
            item = inventory_tree.item(selected[0])
            medicine_data = item['values']
            medicine_name = medicine_data[0]
            
            clear_entries()
            entries["Medicine Name"].insert(0, medicine_data[0])
            entries["Quantity"].insert(0, str(medicine_data[1]))
            entries["Cost"].insert(0, str(medicine_data[2]))

        def save_updated_item():
            selected = inventory_tree.selection()
            if not selected:
                messagebox.showwarning("Select Row", "Select a medicine to update")
                return
            
            item = inventory_tree.item(selected[0])
            old_medicine_name = item['values'][0]
            
            new_name = entries["Medicine Name"].get().strip()
            new_qty = entries["Quantity"].get().strip()
            new_cost = entries["Cost"].get().strip()
            
            if not new_name or not new_qty or not new_cost:
                messagebox.showwarning("Missing Data", "Fill all fields to update!")
                return
            
            try:
                new_qty_int = int(new_qty)
                new_cost_float = float(new_cost)
            except ValueError:
                messagebox.showerror("Error", "Quantity and Cost must be numbers!")
                return
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE medicines SET name = ?, stock_quantity = ?, our_selling_price = ? WHERE name = ?",
                (new_name, new_qty_int, new_cost_float, old_medicine_name)
            )
            conn.commit()
            conn.close()
            
            refresh_table()
            clear_entries()
            messagebox.showinfo("Success", "Medicine updated successfully!")
        
        def check_low_stock():
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT name, stock_quantity FROM medicines WHERE stock_quantity <= 10 AND is_active = 1 ORDER BY stock_quantity ASC")
            
            low_items = cursor.fetchall()
            conn.close()
            
            if low_items:
                msg = "🚨 LOW STOCK ALERT:\n\n"
                for med in low_items:
                    msg += f"• {med[0]}: {med[1]} units left\n"
                messagebox.showwarning("Low Stock Alert", msg)
            else:
                messagebox.showinfo("Stock Status", "✅ No low stock items!")

        Button(btn_frame, text="Add", bg="#3AA6B9", fg="white", command=add_item, **btn_style).grid(row=0, column=0, padx=5, pady=5)
        Button(btn_frame, text="Delete", bg="#F25C54", fg="white", command=delete_item, **btn_style).grid(row=0, column=1, padx=5, pady=5)
        Button(btn_frame, text="Update", bg="#00A36C", fg="white", command=update_item, **btn_style).grid(row=0, column=2, padx=5, pady=5)
        Button(btn_frame, text="Save Update", bg="#FF8800", fg="white", command=save_updated_item, **btn_style).grid(row=1, column=0, padx=5, pady=5)
        Button(btn_frame, text="Clear Form", bg="#FFD8A9", fg="#333", command=clear_entries, **btn_style).grid(row=1, column=1, padx=5, pady=5)
        Button(btn_frame, text="🚨 Low Stock Items", bg="#FF4444", fg="white", command=check_low_stock,
               font=('Arial', 11, 'bold'), width=32).grid(row=2, column=0, columnspan=3, pady=10)

        refresh_table()

        def on_inventory_search(*args):
            query = inventory_search_var.get().strip().lower()
            for item in inventory_tree.get_children():
                inventory_tree.delete(item)
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT name, stock_quantity, our_selling_price FROM medicines WHERE is_active = 1")
            
            for medicine in cursor.fetchall():
                medicine_data = tuple(medicine)
                if query == "" or any(query in str(field).lower() for field in medicine_data):
                    inventory_tree.insert("", "end", values=medicine_data)
            
            conn.close()

        inventory_search_var.trace_add("write", on_inventory_search)

    # ---------------- WHOLESALER SECTION ----------------
    def wholesaler_section(parent):
        for widget in parent.winfo_children():
            widget.destroy()
        heading = Label(parent, text="WHOLESALER MANAGEMENT", bg="#00A36C", fg="white", font=('Arial', 18, 'bold'))
        heading.pack(fill="x", pady=(0, 8))

        body = Frame(parent, bg="#F0F8FF")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        form_frame = Frame(body, bg="#E6F4EA", bd=2, relief="ridge")
        form_frame.pack(side="left", fill="y", padx=8, pady=8)

        Label(form_frame, text="Wholesaler Details", bg="#E6F4EA", fg="#087f5b", font=('Arial', 14, 'bold')).pack(pady=10)

        fields = ["Wholesaler Name", "Contact", "Address", "Deals With"]
        entries = {}
        for f in fields:
            row = Frame(form_frame, bg="#E6F4EA")
            row.pack(fill="x", padx=12, pady=6)
            Label(row, text=f + ":", bg="#E6F4EA", width=16, anchor="w", font=('Arial', 11, 'bold')).pack(side="left")
            e = Entry(row, width=30)
            e.pack(side="left", padx=6)
            entries[f] = e

        row = Frame(form_frame, bg="#E6F4EA")
        row.pack(fill="x", padx=12, pady=6)
        Label(row, text="ID Type:", bg="#E6F4EA", width=16, anchor="w", font=('Arial', 11, 'bold')).pack(side="left")
        id_var = StringVar(value="CNIC")
        OptionMenu(row, id_var, "CNIC", "Driving License", "B Form", "Other").pack(side="left", padx=6)
        entries["ID Type"] = id_var

        row = Frame(form_frame, bg="#E6F4EA")
        row.pack(fill="x", padx=12, pady=6)
        Label(row, text="ID Proof:", bg="#E6F4EA", width=16, anchor="w", font=('Arial', 11, 'bold')).pack(side="left")
        id_proof_entry = Entry(row, width=30)
        id_proof_entry.pack(side="left", padx=6)
        entries["ID Proof"] = id_proof_entry

        btn_frame = Frame(form_frame, bg="#E6F4EA")
        btn_frame.pack(pady=12)
        btn_style = {"font": ('Arial', 11, 'bold'), "width": 14, "height": 1}

        table_container = Frame(body, bg="#FFF5BA", bd=2, relief="ridge")
        table_container.pack(side="right", fill="both", expand=True, padx=8, pady=8)

        search_frame = Frame(table_container, bg="#FFF5BA")
        search_frame.pack(fill="x", padx=8, pady=(6,0))
        Label(search_frame, text="Search:", bg="#FFF5BA").pack(side="left", padx=(0,6))
        wholesaler_search_var = StringVar()
        wholesaler_search_entry = Entry(search_frame, textvariable=wholesaler_search_var, width=30)
        wholesaler_search_entry.pack(side="left", padx=(0,6))

        cols = ("Name", "Contact", "Address", "Deals With", "ID Type", "ID Proof")
        wholesaler_tree = ttk.Treeview(table_container, columns=cols, show="headings")
        for col in cols:
            wholesaler_tree.heading(col, text=col)
            wholesaler_tree.column(col, width=140, anchor="center")

        vsb_frame = Frame(table_container)
        vsb_frame.pack(side="right", fill="y")
        custom_v = GradientScrollbar(vsb_frame, target=wholesaler_tree, orient='vertical', width=16)
        custom_v.pack(fill="y", expand=True)

        hsb_frame = Frame(table_container)
        hsb_frame.pack(side="bottom", fill="x")
        custom_h = GradientScrollbar(hsb_frame, target=wholesaler_tree, orient='horizontal', height=16)
        custom_h.pack(fill="x")

        wholesaler_tree.pack(fill="both", expand=True)

        def refresh_wholesalers():
            for item in wholesaler_tree.get_children():
                wholesaler_tree.delete(item)
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT name, contact, address, deals_with, id_type, id_proof FROM wholesalers WHERE is_active = 1")
            
            for wholesaler in cursor.fetchall():
                wholesaler_data = tuple(wholesaler)
                wholesaler_tree.insert("", "end", values=wholesaler_data)
            
            conn.close()

        def clear_wholesaler_entries():
            for k, v in entries.items():
                if k == "ID Type":
                    v.set("CNIC")
                else:
                    v.delete(0, END)

        def add_wholesaler():
            name = entries["Wholesaler Name"].get().strip()
            contact = entries["Contact"].get().strip()
            address = entries["Address"].get().strip()
            deals_with = entries["Deals With"].get().strip()
            id_type = entries["ID Type"].get()
            id_proof = entries["ID Proof"].get().strip()
            
            if not all([name, contact, address, deals_with, id_proof]):
                messagebox.showwarning("Missing Data", "Fill all fields!")
                return
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO wholesalers (name, contact, address, deals_with, id_type, id_proof) VALUES (?, ?, ?, ?, ?, ?)",
                (name, contact, address, deals_with, id_type, id_proof)
            )
            conn.commit()
            conn.close()
            
            refresh_wholesalers()
            clear_wholesaler_entries()
            messagebox.showinfo("Success", "Wholesaler added successfully!")

        def delete_wholesaler():
            sel = wholesaler_tree.selection()
            if not sel:
                messagebox.showwarning("Select Row", "Select a row to delete")
                return
            
            item = wholesaler_tree.item(sel[0])
            wholesaler_data = item['values']
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("UPDATE wholesalers SET is_active = 0 WHERE name = ? AND contact = ?", (wholesaler_data[0], wholesaler_data[1]))
            conn.commit()
            conn.close()
            
            refresh_wholesalers()
            messagebox.showinfo("Deleted", "Wholesaler removed!")

        def update_wholesaler():
            sel = wholesaler_tree.selection()
            if not sel:
                messagebox.showwarning("Select Row", "Select a row to update")
                return
            
            item = wholesaler_tree.item(sel[0])
            wholesaler_data = item['values']
            
            clear_wholesaler_entries()
            entries["Wholesaler Name"].insert(0, wholesaler_data[0])
            entries["Contact"].insert(0, wholesaler_data[1])
            entries["Address"].insert(0, wholesaler_data[2])
            entries["Deals With"].insert(0, wholesaler_data[3])
            entries["ID Type"].set(wholesaler_data[4])
            entries["ID Proof"].insert(0, wholesaler_data[5])

        def save_updated_wholesaler():
            sel = wholesaler_tree.selection()
            if not sel:
                messagebox.showwarning("Select Row", "Select a row to update")
                return
            
            item = wholesaler_tree.item(sel[0])
            old_data = item['values']
            
            name = entries["Wholesaler Name"].get().strip()
            contact = entries["Contact"].get().strip()
            address = entries["Address"].get().strip()
            deals_with = entries["Deals With"].get().strip()
            id_type = entries["ID Type"].get()
            id_proof = entries["ID Proof"].get().strip()
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE wholesalers SET 
                name = ?, contact = ?, address = ?, deals_with = ?, id_type = ?, id_proof = ?
                WHERE name = ? AND contact = ?""",
                (name, contact, address, deals_with, id_type, id_proof, old_data[0], old_data[1])
            )
            conn.commit()
            conn.close()
            
            refresh_wholesalers()
            clear_wholesaler_entries()
            messagebox.showinfo("Success", "Wholesaler updated successfully!")

        Button(btn_frame, text="Add", bg="#3AA6B9", fg="white", command=add_wholesaler, **btn_style).grid(row=0, column=0, padx=6, pady=4)
        Button(btn_frame, text="Delete", bg="#F25C54", fg="white", command=delete_wholesaler, **btn_style).grid(row=0, column=1, padx=6, pady=4)
        Button(btn_frame, text="Update", bg="#00A36C", fg="white", command=update_wholesaler, **btn_style).grid(row=1, column=0, padx=6, pady=4)
        Button(btn_frame, text="Save Update", bg="#FF8800", fg="white", command=save_updated_wholesaler, **btn_style).grid(row=1, column=1, padx=6, pady=4)
        Button(btn_frame, text="Clear", bg="#FFD8A9", fg="#333", command=clear_wholesaler_entries, **btn_style).grid(row=2, column=0, columnspan=2, pady=4)

        refresh_wholesalers()

        def on_wholesaler_search(*args):
            query = wholesaler_search_var.get().strip().lower()
            for item in wholesaler_tree.get_children():
                wholesaler_tree.delete(item)
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT name, contact, address, deals_with, id_type, id_proof FROM wholesalers WHERE is_active = 1")
            
            for wholesaler in cursor.fetchall():
                wholesaler_data = tuple(wholesaler)
                if query == "" or any(query in str(field).lower() for field in wholesaler_data):
                    wholesaler_tree.insert("", "end", values=wholesaler_data)
            
            conn.close()

        wholesaler_search_var.trace_add("write", on_wholesaler_search)

    # ---------------- FDA API MEDICINE SEARCH SECTION ----------------
    def api_search_section(parent):
        for widget in parent.winfo_children():
            widget.destroy()
        
        heading = Label(parent, text="FDA API MEDICINE SEARCH", bg="#00A36C", fg="white", font=('Arial', 18, 'bold'))
        heading.pack(fill="x", pady=(0, 8))

        body = Frame(parent, bg="#F0F8FF")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        search_frame = Frame(body, bg="#E6F4EA", bd=2, relief="ridge")
        search_frame.pack(fill="x", padx=8, pady=8)
        
        Label(search_frame, text="Search FDA Database:", bg="#E6F4EA", font=('Arial', 12, 'bold')).pack(pady=5)
        
        search_row = Frame(search_frame, bg="#E6F4EA")
        search_row.pack(pady=10)
        
        Label(search_row, text="Medicine Name:", bg="#E6F4EA").pack(side=LEFT, padx=5)
        api_search_entry = Entry(search_row, width=30, font=('Arial', 11))
        api_search_entry.pack(side=LEFT, padx=5)
        
        def search_api():
            search_term = api_search_entry.get().strip()
            if not search_term:
                messagebox.showwarning("Input Needed", "Enter a medicine name to search")
                return
            
            api = WorkingPharmacyAPI()
            results = api.search_medicines(search_term)
            
            for item in results_tree.get_children():
                results_tree.delete(item)
            
            if 'error' in results:
                messagebox.showerror("API Error", results['error'])
            elif not results:
                messagebox.showinfo("No Results", "No medicines found in FDA database")
            else:
                for med in results:
                    results_tree.insert("", "end", values=(
                        med['brand_name'],
                        med['generic_name'], 
                        med['manufacturer'],
                        med['dosage_form']
                    ))
        
        Button(search_row, text="Search FDA", bg="#3AA6B9", fg="white", 
               font=('Arial', 11, 'bold'), command=search_api).pack(side=LEFT, padx=10)

        results_frame = Frame(body, bg="#FFF5BA", bd=2, relief="ridge")
        results_frame.pack(fill="both", expand=True, padx=8, pady=8)
        
        Label(results_frame, text="Search Results from FDA Database", bg="#FFF5BA", 
              font=('Arial', 14, 'bold')).pack(pady=8)

        cols = ("Brand Name", "Generic Name", "Manufacturer", "Dosage Form")
        results_tree = ttk.Treeview(results_frame, columns=cols, show="headings", height=8)
        for col in cols:
            results_tree.heading(col, text=col)
            results_tree.column(col, width=150)
        
        def add_selected_to_inventory():
            selected = results_tree.selection()
            if not selected:
                messagebox.showwarning("Select Medicine", "Select a medicine from search results")
                return
            
            item = results_tree.item(selected[0])
            medicine_data = {
                'brand_name': item['values'][0],
                'generic_name': item['values'][1],
                'manufacturer': item['values'][2],
                'dosage_form': item['values'][3],
                'external_id': f"FDA_{item['values'][0].replace(' ', '_')}"
            }
            
            price = simpledialog.askfloat("Selling Price", f"Enter selling price for {medicine_data['brand_name']}:")
            if price is None:
                return
                
            quantity = simpledialog.askinteger("Stock Quantity", f"Enter initial stock quantity for {medicine_data['brand_name']}:")
            if quantity is None:
                return
            
            api = WorkingPharmacyAPI()
            result = api.add_medicine_to_inventory(medicine_data, price, quantity)
            
            if result == "added":
                messagebox.showinfo("Success", f"{medicine_data['brand_name']} added to inventory!")
            elif result == "exists":
                messagebox.showwarning("Exists", "Medicine already in inventory")
            else:
                messagebox.showerror("Error", "Failed to add medicine to inventory")

        btn_frame = Frame(results_frame, bg="#FFF5BA")
        btn_frame.pack(pady=10)
        
        Button(btn_frame, text="Add Selected to Inventory", bg="#00A36C", fg="white",
               font=('Arial', 11, 'bold'), command=add_selected_to_inventory).pack(pady=5)

        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=results_tree.yview)
        results_tree.configure(yscrollcommand=scrollbar.set)
        
        results_tree.pack(side=LEFT, fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side=RIGHT, fill="y")

    # ---------------- SALES HISTORY SECTION ----------------
    def sales_history_section(parent):
        for widget in parent.winfo_children():
            widget.destroy()
        heading = Label(parent, text="SALES HISTORY", bg="#00A36C", fg="white", font=('Arial', 18, 'bold'))
        heading.pack(fill="x", pady=(0, 8))

        body = Frame(parent, bg="#F0F8FF")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        ctrl = Frame(body, bg="#F0F8FF")
        ctrl.pack(fill="x", padx=6, pady=6)
        Label(ctrl, text="Search (Customer Name or ID):", bg="#F0F8FF").pack(side="left", padx=(0,6))
        sales_search_var = StringVar()
        sales_search_entry = Entry(ctrl, textvariable=sales_search_var, width=40)
        sales_search_entry.pack(side="left", padx=(0,6))

        table_frame = Frame(body)
        table_frame.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("Sale ID", "Customer Name", "Contact", "Medicine", "Qty", "Total", "Date/Time")
        sales_tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        for col in cols:
            sales_tree.heading(col, text=col)
            sales_tree.column(col, width=140, anchor="center")

        vsb_frame = Frame(table_frame)
        vsb_frame.pack(side="right", fill="y")
        custom_v = GradientScrollbar(vsb_frame, target=sales_tree, orient='vertical', width=16)
        custom_v.pack(fill="y", expand=True)

        sales_tree.pack(fill="both", expand=True)

        def refresh_sales():
            for item in sales_tree.get_children():
                sales_tree.delete(item)
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.sale_id, c.name, c.phone, m.name, si.quantity, s.total_amount, s.sale_date 
                FROM sales s
                JOIN customers c ON s.customer_id = c.customer_id
                JOIN sale_items si ON s.sale_id = si.sale_id
                JOIN medicines m ON si.medicine_id = m.medicine_id
                ORDER BY s.sale_date DESC
            """)
            
            for sale in cursor.fetchall():
                sale_data = tuple(sale)
                sales_tree.insert("", "end", values=(
                    f"S{sale_data[0]}",
                    sale_data[1],
                    sale_data[2],
                    sale_data[3],
                    sale_data[4],
                    f"Rs {sale_data[5]:.2f}",
                    sale_data[6]
                ))
            
            conn.close()

        def search_sales():
            query = sales_search_var.get().strip().lower()
            for item in sales_tree.get_children():
                sales_tree.delete(item)
            
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.sale_id, c.name, c.phone, m.name, si.quantity, s.total_amount, s.sale_date 
                FROM sales s
                JOIN customers c ON s.customer_id = c.customer_id
                JOIN sale_items si ON s.sale_id = si.sale_id
                JOIN medicines m ON si.medicine_id = m.medicine_id
                WHERE LOWER(c.name) LIKE ? OR s.sale_id LIKE ?
                ORDER BY s.sale_date DESC
            """, (f"%{query}%", f"%{query.replace('s', '').replace('S', '')}%"))
            
            for sale in cursor.fetchall():
                sale_data = tuple(sale)
                sales_tree.insert("", "end", values=(
                    f"S{sale_data[0]}",
                    sale_data[1],
                    sale_data[2],
                    sale_data[3],
                    sale_data[4],
                    f"Rs {sale_data[5]:.2f}",
                    sale_data[6]
                ))
            
            conn.close()

        action_frame = Frame(body, bg="#F0F8FF")
        action_frame.pack(fill="x", padx=6, pady=6)

        def delete_sale():
            selected = sales_tree.selection()
            if not selected:
                messagebox.showwarning("Select Sale", "Please select a sale record to delete")
                return
    
            item = sales_tree.item(selected[0])
            sale_data = item['values']
            sale_id = sale_data[0].replace('S', '')
    
            if messagebox.askyesno("Confirm Delete", f"Delete sale {sale_data[0]}?\nThis will restore stock quantity."):
                try:
                    conn = get_db_connection()
                    if not conn:
                        return
                
                    cursor = conn.cursor()
            
                    cursor.execute("""
                        SELECT si.medicine_id, si.quantity 
                        FROM sale_items si 
                        WHERE si.sale_id = ?
                    """, (sale_id,))
                    sale_item = cursor.fetchone()
            
                    if sale_item:
                        medicine_id, quantity = sale_item
                        cursor.execute("""
                            UPDATE medicines 
                            SET stock_quantity = stock_quantity + ? 
                            WHERE medicine_id = ?
                        """, (quantity, medicine_id))
            
                        cursor.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale_id,))
                        cursor.execute("DELETE FROM sales WHERE sale_id = ?", (sale_id,))
            
                        conn.commit()
                        messagebox.showinfo("Success", "Sale record deleted and stock restored!")
                        refresh_sales()
            
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete sale: {str(e)}")
                finally:
                    conn.close()

        Button(action_frame, text="Delete Selected Sale", bg="#F25C54", fg="white",
            font=('Arial', 11, 'bold'), command=delete_sale).pack(side="left", padx=5)

        sales_search_var.trace_add("write", lambda *a: search_sales())
        refresh_sales()

    # ---------------- SIDEBAR BUTTONS ----------------
    sections = ["Analytical Dashboard", "Purchases", "Inventory Management", "Wholesalers/Suppliers","FDA API Search", "Sales History", "Logout"]
    def show_section(name):
        for widget in content.winfo_children():
            widget.destroy()
        if name == "Analytical Dashboard":
            analytical_dashboard_section(content)
        elif name == "Purchases":
            purchases_section(content)
        elif name == "Inventory Management":
            inventory_section(content)
        elif name == "Wholesalers/Suppliers":
            wholesaler_section(content)
        elif name == "FDA API Search":
            api_search_section(content)    
        elif name == "Sales History":
            sales_history_section(content)
        elif name == "Logout":
            adm.destroy()
            root.deiconify()
        else:
            Label(content, text=f"{name} Section", bg="#FFF8E1", fg="#E67E22", font=('Arial', 18, 'bold')).pack(pady=40)

    for sec in sections:
        btn = Button(scrollable_frame, text=sec, font=('Arial', 11, 'bold'),
                     bg="#FFD8A9", fg="#4A4A4A", bd=0, activebackground="#E67E22", activeforeground="white",
                     anchor="w", command=lambda s=sec: show_section(s))
        btn.pack(fill="x", pady=6, padx=8)
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        if sec == "Logout":
            btn.config(bg="#F25C54", fg="white")

    # Show analytical dashboard by default
    analytical_dashboard_section(content)

# ---------------- Employee Portal (Billing System) ----------------
def open_employee_portal(username):
    emp_win = Toplevel(root)
    emp_win.title(f"Wellora - Employee Billing ({username})")
    emp_win.geometry("1000x620")
    emp_win.configure(bg="#E6F4EA")

    Label(emp_win, text="Empowering Care, One Prescription at a Time 🌿",
          bg="#E6F4EA", fg="#087f5b", font=('Arial', 18, 'bold italic')).pack(pady=(12,4))
    Label(emp_win, text="Billing Area", bg="#E6F4EA", fg="#2E8B57", font=('Arial', 14, 'bold')).pack()

    left = Frame(emp_win, bg="#E6F4EA", bd=2, relief="ridge")
    left.place(x=40, y=120, width=450, height=420)

    right = Frame(emp_win, bg="#FFF5BA", bd=2, relief="ridge")
    right.place(x=520, y=120, width=420, height=420)

    Label(left, text="Enter Patient Details", bg="#E6F4EA", font=('Arial', 14, 'bold')).pack(pady=8)

    fields = [
        ("Patient Name", ""),
        ("Patient Contact", ""),
        ("Medicine Name", ""),
        ("Date (DD-MM-YYYY)", datetime.datetime.now().strftime("%d-%m-%Y")),
        ("Quantity", "1"),
        ("Cost per Unit", "0"),
        ("Manufacture Date", ""),
        ("Expiry Date", "")
    ]
    entry_widgets = {}
    for label_text, default in fields:
        row = Frame(left, bg="#E6F4EA")
        row.pack(fill="x", pady=4, padx=10)
        Label(row, text=label_text + ":", bg="#E6F4EA", width=18, anchor="w", font=('Arial', 10)).pack(side=LEFT)

        if label_text == "Quantity":
            qty_frame = Frame(row, bg="#E6F4EA")
            qty_frame.pack(side=LEFT)
            def increase_qty(e=None):
               try:
                    val = int(entry_widgets["Quantity"].get())
               except:
                   val = 0
               entry_widgets["Quantity"].delete(0, END)
               entry_widgets["Quantity"].insert(0, str(val + 1))
            def decrease_qty(e=None):
               try:
                   val = int(entry_widgets["Quantity"].get())
               except:
                  val = 0
               if val > 0:
                   entry_widgets["Quantity"].delete(0, END)
                   entry_widgets["Quantity"].insert(0, str(val - 1))
            e = Entry(qty_frame, width=6, font=('Arial', 10), justify="center")
            e.pack(side=LEFT, padx=5)
            e.insert(0, "0")
            Button(qty_frame, text="+", width=3, bg="#B9F3B5", command=increase_qty).pack(side=LEFT, padx=2)
            Button(qty_frame, text="-", width=3, bg="#F25C54", fg="white", command=decrease_qty).pack(side=LEFT, padx=2)
            entry_widgets[label_text] = e
        elif label_text == "Medicine Name":
            medicine_var = StringVar()
            medicine_dropdown = ttk.Combobox(row, textvariable=medicine_var, width=20, font=('Arial', 10))
            medicine_dropdown.pack(side=LEFT, padx=5)

            all_medicines = []
            medicine_data_loaded = False

            def load_medicine_data():
                nonlocal medicine_data_loaded
                if not medicine_data_loaded:
                    try:
                        conn = get_db_connection()
                        if conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT name FROM medicines WHERE is_active = 1 AND stock_quantity > 0 ORDER BY name")
                            all_medicines.clear()
                            for row in cursor.fetchall():
                                all_medicines.append(row[0])
                            conn.close()
                            medicine_data_loaded = True
                    except Exception as e:
                        print(f"Error loading medicines: {e}")

            def filter_medicines(event=None):
                load_medicine_data()
                if event and event.keysym in ('Up', 'Down', 'Left', 'Right', 'Tab', 'Return', 'Escape'):
                    return
                typed = medicine_var.get().lower()
                if typed:
                    filtered = [med for med in all_medicines if typed in med.lower()]
                    medicine_dropdown['values'] = filtered
                else:
                    medicine_dropdown['values'] = all_medicines
        
            def on_focus(event):
                load_medicine_data()
                filter_medicines()

            def on_click(event):
                medicine_dropdown.event_generate('<Down>')

            medicine_dropdown.bind('<FocusIn>', on_focus)
            medicine_dropdown.bind('<KeyRelease>', filter_medicines)
            medicine_dropdown.bind('<Button-1>', on_click)
            
            def on_medicine_select(event):
                selected = medicine_var.get()
                if selected:
                    try:
                        conn = get_db_connection()
                        if conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT our_selling_price FROM medicines WHERE name = ?", (selected,))
                            result = cursor.fetchone()
                            if result:
                                entry_widgets["Cost per Unit"].delete(0, END)
                                entry_widgets["Cost per Unit"].insert(0, str(result[0]))
                            conn.close()
                    except Exception as e:
                        print(f"Error fetching price: {e}")

            medicine_dropdown.bind('<<ComboboxSelected>>', on_medicine_select)
            entry_widgets[label_text] = medicine_dropdown

        else:
            e = Entry(row, width=22, font=('Arial', 10))
            e.pack(side=LEFT, padx=5)
            e.insert(0, default)
            entry_widgets[label_text] = e

       
    bills_dir = "bills"
    if not os.path.exists(bills_dir):
        os.makedirs(bills_dir)

    Label(right, text="Bill Area", bg="#FFF5BA", font=('Arial', 12, 'bold')).pack(pady=10)
    caption = Label(right, text="Welcome to Wellora Pharmacy\n123 Wellness Street, Karachi\nContact: 0300-1234567 | 021-5678901",
                    bg="#FFF5BA", fg="#087f5b", font=('Arial', 9), justify="center")
    caption.pack()
    bill_text = Text(right, font=("Consolas", 11), bd=2, relief="sunken", wrap="word")
    bill_text.pack(expand=True, fill="both", padx=8, pady=8)

    def clear_form():
        for k, w in entry_widgets.items():
            if k == "Date (DD-MM-YYYY)":
                w.delete(0, END)
                w.insert(0, datetime.datetime.now().strftime("%d-%m-%Y"))
            elif k == "Medicine Name":
                w.set("")
            else:
                w.delete(0, END)

    def reset_all():
        clear_form()
        bill_text.delete(1.0, END)

    def compute_total():
        try:
            qty = float(entry_widgets["Quantity"].get() or 0)
            cost = float(entry_widgets["Cost per Unit"].get() or 0)
            total = qty * cost
            messagebox.showinfo("Total", f"Total = Rs {total:.2f}")
            return total
        except:
            messagebox.showerror("Error", "Quantity and Cost must be numbers.")

    def generate_bill():
        patient = entry_widgets["Patient Name"].get().strip()
        contact = entry_widgets["Patient Contact"].get().strip()
        med = entry_widgets["Medicine Name"].get().strip()
        date = entry_widgets["Date (DD-MM-YYYY)"].get().strip()
        qty = entry_widgets["Quantity"].get().strip()
        cost = entry_widgets["Cost per Unit"].get().strip()
        mfg = entry_widgets["Manufacture Date"].get().strip()
        exp = entry_widgets["Expiry Date"].get().strip()
        
        if not patient or not med:
            messagebox.showerror("Missing Data", "Please enter at least Patient Name and Medicine Name.")
            return
        
        try:
            qtyf = float(qty or 0)
            costf = float(cost or 0)
            total = qtyf * costf
        except ValueError:
            messagebox.showerror("Invalid Number", "Quantity and Cost must be numeric.")
            return
        
        try:
            conn = get_db_connection()
            if not conn:
                return
                
            cursor = conn.cursor()
            
            cursor.execute("SELECT medicine_id, name, stock_quantity, our_selling_price FROM medicines WHERE name = ? AND is_active = 1", (med,))
            medicine = cursor.fetchone()
            
            if not medicine:
                messagebox.showerror("Medicine Not Found", 
                    f"❌ Medicine '{med}' not found in inventory!\n\n"
                    f"Please:\n"
                    f"1. Check spelling\n" 
                    f"2. Ask admin to add this medicine\n"
                    f"3. Use available medicines from inventory")
                conn.close()
                return
            
            medicine_id, medicine_name, current_stock, selling_price = medicine
            
            if current_stock < qtyf:
                messagebox.showerror("Insufficient Stock", 
                    f"⚠️ Not enough stock available!\n\n"
                    f"Medicine: {medicine_name}\n"
                    f"Requested: {qtyf} units\n" 
                    f"Available: {current_stock} units\n\n"
                    f"Please reduce quantity or ask admin to restock.")
                conn.close()
                return
            
            cursor.execute("INSERT INTO customers (name, phone) VALUES (?, ?)", (patient, contact))
            customer_id = cursor.lastrowid

            cursor.execute("INSERT INTO sales (customer_id, total_amount, payment_method) VALUES (?, ?, ?)", (customer_id, total, 'Cash'))
            sale_id = cursor.lastrowid
    
            cursor.execute("INSERT INTO sale_items (sale_id, medicine_id, quantity, price) VALUES (?, ?, ?, ?)", (sale_id, medicine_id, qtyf, costf))
            
            # FIXED STOCK DEDUCTION - This is where the issue was!
            cursor.execute("UPDATE medicines SET stock_quantity = stock_quantity - ? WHERE medicine_id = ?", (qtyf, medicine_id))
            
            now = datetime.datetime.now().strftime("%d-%m-%Y %I:%M %p")
            
            header_lines = [
                "       WELLORA PHARMACY",
                "       123 Wellness Street, Karachi",
                "       Contact: 0300-1234567 | 021-5678901",
                "============================================================",
                f"Date: {now}",
                f"Patient: {patient}    Contact: {contact}",
                "------------------------------------------------------------",
                f"Medicine: {med}",
                f"Stock Before: {current_stock}    Sold: {qtyf}",
                f"Remaining Stock: {current_stock - qtyf}",
                f"Manufacture Date: {mfg}    Expiry Date: {exp}",
                f"Qty: {qtyf}    Unit Cost: Rs {costf:.2f}",
                "------------------------------------------------------------",
                f"TOTAL: Rs {total:.2f}",
                "============================================================",
                "Thank you for choosing Wellora Pharmacy 🌿",
            ]
            
            bill_text.delete(1.0, END)
            bill_text.insert(END, "\n".join(header_lines))
            
            conn.commit()
            messagebox.showinfo("Success ✅", 
                f"Bill generated & stock updated!\n\n"
                f"Medicine: {medicine_name}\n" 
                f"Stock: {current_stock} → {current_stock - qtyf} units\n"
                f"Sale ID: S{sale_id}")
            
        except Exception as e:
            print(f"Database error: {e}")
            messagebox.showerror("Error", f"Database error: {str(e)}")
        finally:
            conn.close()
            
    def save_bill():
        content = bill_text.get(1.0, END).strip()
        if not content:
            messagebox.showerror("No Bill", "No bill to save. Generate the bill first.")
            return
        patient = entry_widgets["Patient Name"].get().strip() or "unknown"
        tstamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{bills_dir}/{patient}_{tstamp}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        messagebox.showinfo("Saved", f"Bill saved as {filename}")

    def print_bill():
        save_bill()
        messagebox.showinfo("Print", "Bill sent to printer (simulated).")

    def search_bills():
        query = entry_widgets["Patient Name"].get().strip().lower()
        if not query:
            messagebox.showerror("Search", "Enter patient name to search saved bills.")
            return
        found = []
        for fname in os.listdir(bills_dir):
            if fname.lower().startswith(query):
                found.append(fname)
        if not found:
            messagebox.showinfo("Search", "No saved bills found for that patient.")
            return
        first = found[0]
        with open(os.path.join(bills_dir, first), "r", encoding="utf-8") as f:
            content = f.read()
        bill_text.delete(1.0, END)
        bill_text.insert(END, content)
        messagebox.showinfo("Search", f"Loaded {first}")

    btn_frame = Frame(left, bg="#E6F4EA")
    btn_frame.pack(pady=12)
    common = {"font": ('Arial', 10, 'bold'), "width": 10, "height": 1, "bg": "white", "relief": "solid", "bd": 1}
    Button(btn_frame, text="Clear", command=clear_form, highlightbackground="#F25C54", **common).grid(row=0, column=0, padx=6, pady=6)
    Button(btn_frame, text="Generate", command=generate_bill, highlightbackground="#B9F3B5", **common).grid(row=0, column=1, padx=6, pady=6)
    Button(btn_frame, text="Save", command=save_bill, highlightbackground="#B3E5FC", **common).grid(row=0, column=2, padx=6, pady=6)
    Button(btn_frame, text="Total", command=compute_total, highlightbackground="#FFF5BA", **common).grid(row=1, column=0, padx=6, pady=6)
    Button(btn_frame, text="Reset", command=reset_all, highlightbackground="#FFD8A9", **common).grid(row=1, column=1, padx=6, pady=6)
    Button(btn_frame, text="Print", command=print_bill, highlightbackground="#FFE6CC", **common).grid(row=1, column=2, padx=6, pady=6)
    Button(btn_frame, text="Search", command=search_bills, highlightbackground="#00A36C", **common).grid(row=2, column=1, pady=8)

    Label(emp_win, text=f"Logged in as: {username}", bg="#E6F4EA", fg="#087f5b", font=('Arial', 10, 'italic')).place(x=40, y=100)
    logout_btn = Button(emp_win, text="Logout", bg="#F25C54", fg="white",
                        font=('Arial', 12, 'bold'), width=15, command=emp_win.destroy)
    logout_btn.pack(side=BOTTOM, pady=20)

# Login validation
def login_user():
    selected_role = role.get()
    if selected_role == "None":
        messagebox.showwarning("Select Role", "Choose Employee or Admin")
        return
    username = username_entry.get().strip()
    password = password_entry.get().strip()
    valid_list = valid_credentials[selected_role]
    for cred in valid_list:
        if cred["username"] == username and cred["password"] == password:
            messagebox.showinfo("Login Success", f"Welcome {username}")
            root.withdraw()
            if selected_role == "Admin":
                open_admin_portal(username)
            else:
                open_employee_portal(username)
            return
    messagebox.showerror("Invalid", "Incorrect credentials")

Button(login_frame, text="Login", bg="#00A36C", fg="white", font=('Arial', 12, 'bold'),
       width=25, command=login_user).grid(row=5, column=0, columnspan=2, pady=20)

root.mainloop()