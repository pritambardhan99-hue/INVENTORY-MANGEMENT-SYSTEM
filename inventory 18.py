
# Inventory Management System — cleaned and fixed
# Consolidated imports, removed duplicate function definitions,
# fixed minor logic bugs, and made the UI code consistent.
# NOTE: This file expects external packages: pillow, reportlab, qrcode, pandas, matplotlib, openpyxl.
# If any are missing, install via pip.

import os
import re
import sqlite3
import datetime as dt
import json
import platform

from typing import Optional, Tuple, List, Any

# GUI
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# Images / PDF / charts
from PIL import Image, ImageTk
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Table, TableStyle, SimpleDocTemplate, Spacer
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import qr as qr_barcode

import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Optional imports used in functions (import in-place if not installed).
# qrcode and openpyxl are imported inside functions where used.

APP_TITLE = "Inventory Management System"

THEME = {
    "primary": "#1ABC9C",  # teal
    "dark": "#2C3E50",  # navy
    "accent": "#E67E22",  # orange
    "bg": "#F7F9FA",
    "text": "#2C3E50",
    "danger": "#E74C3C",
    "success": "#27AE60",
    "warning": "#F1C40F"
}
FONT_LG = ("Segoe UI", 14)
FONT_XL = ("Segoe UI", 18, "bold")
FONT_MD = ("Segoe UI", 12)

DB_PATH = "inventory18.db"

# ---------- Helpers ----------

def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def today_str() -> str:
    return dt.date.today().isoformat()

def now_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def init_db():
    con = db()
    cur = con.cursor()

    # USERS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('Admin','Employee')),
            is_online INTEGER DEFAULT 0,
            last_login TEXT,
            security_question TEXT,
            security_answer TEXT
        )
    """)

    # EMPLOYEES
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees(
            emp_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT CHECK(role IN ('Admin','Employee')),
            join_date TEXT NOT NULL
        )
    """)

    # SUPPLIERS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers(
            supplier_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            company TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            address TEXT
        )
    """)

    # CUSTOMERS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers(
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE,
            email TEXT UNIQUE
        )
    """)

    # PRODUCTS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products(
            product_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            supplier_id TEXT NOT NULL,
            quantity INTEGER DEFAULT 0,
            cost_price REAL DEFAULT 0.0,
            unit_price REAL DEFAULT 0.0,
            gst REAL DEFAULT 18,
            mrp REAL DEFAULT 0.0,
            reorder_level INTEGER DEFAULT 0,
            qr_code TEXT,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(supplier_id)
        )
    """)
    cur.execute("""
            CREATE TABLE IF NOT EXISTS sales_master(
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                sold_by TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT,
                subtotal REAL NOT NULL,
                grand_total REAL NOT NULL,
                FOREIGN KEY(sold_by) REFERENCES users(username)
            )
            """)



    # SALES ITEMS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_items(
            item_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT,
            sale_id        INTEGER NOT NULL,
            product_id     TEXT NOT NULL,
            product_name   TEXT NOT NULL,
            category       TEXT,
            quantity       INTEGER NOT NULL DEFAULT 1,
            mrp            REAL NOT NULL,
            total_price    REAL NOT NULL,
            discount_type  TEXT,
            discount_value REAL DEFAULT 0,
            effective_total REAL NOT NULL,
            FOREIGN KEY (sale_id) REFERENCES sales_master(sale_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
    """)

    # RETURNS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS returns(
            return_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            refund_amount REAL NOT NULL,
            date TEXT NOT NULL,
            reason TEXT,
            FOREIGN KEY(sale_id) REFERENCES sales_master(sale_id),
            FOREIGN KEY(product_id) REFERENCES products(product_id)
        )
    """)
    # STOCK LOGS
    cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                change_type TEXT CHECK(change_type IN ('IN','OUT')) NOT NULL,
                quantity INTEGER NOT NULL,
                reason TEXT,
                changed_by TEXT NOT NULL,
                date TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(product_id),
                FOREIGN KEY(changed_by) REFERENCES users(username)
            )
        """)

    # Seed admin if missing
    cur.execute("SELECT 1 FROM users WHERE username=?", ("admin",))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users(username,password,role,is_online,last_login) VALUES(?,?,?,?,?)",
                    ("admin", "admin123", "Admin", 0, None))

    con.commit()
    con.close()

def padded_id(prefix_table: str, id_col: str, width: int = 3) -> str:
    con = db()
    cur = con.cursor()
    try:
        cur.execute(f"SELECT {id_col} FROM {prefix_table}")
    except Exception:
        con.close()
        # In case table doesn't exist or column missing
        return "1".zfill(width)
    ids = []
    for row in cur.fetchall():
        try:
            ids.append(int(str(row[0]).lstrip("0") or "0"))
        except Exception:
            pass
    nxt = (max(ids) + 1) if ids else 1
    con.close()
    return str(nxt).zfill(width)

def validate_email(email: str) -> bool:
    return re.fullmatch(r"^[A-Za-z0-9._%+-]+@(gmail\.com|yahoo\.com)$", email) is not None

def validate_phone(phone: str) -> bool:
    return re.fullmatch(r"^[6-9]\d{9}$", phone) is not None

def employee_default_password(emp_name: str) -> str:
    token = re.sub(r"\s+", "", emp_name).lower()[:3]
    if len(token) < 3:
        token = (token + "xxx")[:3]
    return f"{token}123"

# ---------- PDF: Invoice (re-usable) ----------
def generate_invoice_pdf(filename, company_name, company_address, invoice_no, invoice_date,
                         customer_name, customer_phone, items, discount_type, discount_value,
                         gst_percent, subtotal, grand_total):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()

    story.append(Paragraph(f"<b>{company_name}</b>", styles["Title"]))
    story.append(Paragraph(company_address.replace("\n", "<br/>"), styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>Invoice No:</b> {invoice_no}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date:</b> {invoice_date}", styles["Normal"]))
    story.append(Paragraph(f"<b>Customer:</b> {customer_name}", styles["Normal"]))
    story.append(Paragraph(f"<b>Phone:</b> {customer_phone}", styles["Normal"]))
    story.append(Spacer(1, 12))

    data = [["Product", "Category", "Qty", "MRP", "Line Total (₹)"]]
    for n, c, q, m, t in items:
        data.append([n, c, q, f"{m:.2f}", f"{t:.2f}"])

    table = Table(data, colWidths=[180, 100, 60, 80, 100])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    totals_data = []
    totals_data.append(["Subtotal", f"₹ {subtotal:.2f}"])
    if discount_type == "Flat":
        totals_data.append([f"Discount (Flat ₹{discount_value:.2f})", f"- ₹ {discount_value:.2f}"])
    else:
        totals_data.append([f"Discount ({discount_value:.2f}%)", f"- ₹ {(subtotal * discount_value / 100):.2f}"])
    after_disc = subtotal - (discount_value if discount_type == "Flat" else subtotal * discount_value / 100)
    gst_amt = after_disc * (gst_percent / 100)
    totals_data.append([f"GST ({gst_percent:.1f}%)", f"+ ₹ {gst_amt:.2f}"])
    totals_data.append(["", ""])
    totals_data.append(["Grand Total", f"₹ {grand_total:.2f}"])

    totals_table = Table(totals_data, colWidths=[300, 200])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTNAME", (-1, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (-1, -1), (-1, -1), colors.green),
        ("FONTSIZE", (-1, -1), (-1, -1), 14),
    ]))
    story.append(totals_table)

    doc.build(story)

# ---------- Generic exports ----------
def export_treeview_to_excel(tree: ttk.Treeview, suggested_name: str):
    save_path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=suggested_name,
                                             filetypes=[("Excel Workbook", "*.xlsx")])
    if not save_path:
        return
    cols = tree["columns"]
    data = []
    for child in tree.get_children():
        vals = tree.item(child, "values")
        data.append(list(vals))
    df = pd.DataFrame(data, columns=cols)
    try:
        with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        messagebox.showinfo("Export", f"Excel exported:\n{save_path}")
    except Exception as e:
        messagebox.showerror("Export Error", str(e))

def export_treeview_to_pdf(tree: ttk.Treeview, suggested_name: str, title: str):
    save_path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=suggested_name,
                                             filetypes=[("PDF", "*.pdf")])
    if not save_path:
        return

    cols = tree["columns"]
    data = [list(cols)]
    for child in tree.get_children():
        vals = tree.item(child, "values")
        data.append(list(vals))

    doc = SimpleDocTemplate(save_path, pagesize=A4, rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"<b>{title}</b>", styles["Title"]), Spacer(1, 8)]

    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONT', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(tbl)
    doc.build(story)
    messagebox.showinfo("Export", f"PDF exported:\n{save_path}")

# ---------- Main App ----------
class InventoryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x750")
        self.configure(bg=THEME["bg"])
        self.minsize(1100, 720)

        self.current_user = None  # (username, role)

        self.container = tk.Frame(self, bg=THEME["bg"])
        self.container.pack(fill="both", expand=True)

        self.login_frame = LoginFrame(self.container, self)
        self.login_frame.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def show_dashboard(self):
        self.login_frame.pack_forget()
        self.dashboard = Dashboard(self.container, self)
        self.dashboard.pack(fill="both", expand=True)

    def logout(self):
        if self.current_user:
            con = db()
            cur = con.cursor()
            cur.execute("UPDATE users SET is_online=0 WHERE username=?", (self.current_user[0],))
            con.commit()
            con.close()

        for w in self.container.winfo_children():
            w.destroy()
        self.current_user = None
        self.login_frame = LoginFrame(self.container, self)
        self.login_frame.pack(fill="both", expand=True)

    def on_close(self):
        try:
            if self.current_user:
                con = db()
                cur = con.cursor()
                cur.execute("UPDATE users SET is_online=0 WHERE username=?", (self.current_user[0],))
                con.commit()
                con.close()
        except:
            pass
        self.destroy()

# ---------- Login ----------
class LoginFrame(tk.Frame):
    def __init__(self, parent, app: InventoryApp):
        super().__init__(parent, bg=THEME["bg"])
        self.app = app
        self.attempts = 0

        # --- Main two-column layout ---
        main_frame = tk.Frame(self, bg=THEME["bg"])
        main_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Left: big branding logo (logo2.png)
        try:
            logo2_img = Image.open("logo2.png").resize((420, 480))
            self.logo2 = ImageTk.PhotoImage(logo2_img)
            tk.Label(main_frame, image=self.logo2, bg=THEME["bg"]).grid(
                row=0, column=0, padx=(0, 40), pady=10, sticky="n"
            )
        except Exception:
            pass

        # Right: login panel
        wrapper = tk.Frame(main_frame, bg=THEME["bg"])
        wrapper.grid(row=0, column=1, sticky="n")

        # Top small logo (logo.png)
        try:
            logo_img = Image.open("logo.png").resize((140, 140))
            self.logo = ImageTk.PhotoImage(logo_img)
            tk.Label(wrapper, image=self.logo, bg=THEME["bg"]).grid(
                row=0, column=0, columnspan=2, pady=(0, 10)
            )
        except Exception:
            pass

        # 🚀 Professional Title
        tk.Label(wrapper, text="INVENTORY MANAGEMENT SYSTEM",
                 font=("Segoe UI", 18, "bold"),
                 fg=THEME["dark"], bg=THEME["bg"]).grid(
            row=1, column=0, columnspan=2, pady=(0, 16)
        )

        # Username (dropdown combobox)
        tk.Label(wrapper, text="Username", font=FONT_LG, bg=THEME["bg"]).grid(
            row=2, column=0, sticky="e", padx=8, pady=6
        )
        usr_holder = tk.Frame(wrapper, bg="#FFF59D", bd=2, relief="flat")
        usr_holder.grid(row=2, column=1, sticky="w", padx=8, pady=6)
        self.username_var = tk.StringVar()
        self.username_cmb = ttk.Combobox(
            usr_holder, textvariable=self.username_var, state="readonly", width=25
        )
        self.username_cmb.pack(padx=4, pady=2)

        # Password
        tk.Label(wrapper, text="Password", font=FONT_LG, bg=THEME["bg"]).grid(
            row=3, column=0, sticky="e", padx=8, pady=6
        )
        pwd_holder = tk.Frame(wrapper, bg="#C8E6C9", bd=2, relief="flat")
        pwd_holder.grid(row=3, column=1, sticky="w", padx=8, pady=6)
        self.password_var = tk.StringVar()
        self.password_entry = tk.Entry(
            pwd_holder, textvariable=self.password_var,
            show="•", font=FONT_LG, bd=0, width=25
        )
        self.password_entry.pack(padx=4, pady=2)

        # Clock
        self.clock_lbl = tk.Label(wrapper, text="", font=FONT_MD, fg="red", bg=THEME["bg"])
        self.clock_lbl.grid(row=4, column=0, columnspan=2, pady=8)
        self.update_clock()

        # Login Button
        self.login_btn = tk.Button(
            wrapper, text="Login", font=FONT_LG,
            bg=THEME["primary"], fg="white", activebackground=THEME["accent"],
            height=2, command=self.try_login, cursor="hand2"
        )
        self.login_btn.grid(row=5, column=0, columnspan=2, sticky="ew", pady=8)

        # Hover effect
        self.login_btn.bind("<Enter>", lambda e: self.login_btn.config(bg="#16A085"))
        self.login_btn.bind("<Leave>", lambda e: self.login_btn.config(bg=THEME["primary"]))

        # Forgot Password Button
        fp_btn = tk.Button(wrapper, text="Forgot Password?", font=("Segoe UI", 10, "underline"),
                           bg=THEME["bg"], fg="blue", bd=0, cursor="hand2",
                           command=self.forgot_password)
        fp_btn.grid(row=6, column=0, columnspan=2)

        # Load usernames into dropdown
        self.refresh_usernames()

    # ---------------- Helper Methods ----------------
    def update_clock(self):
        self.clock_lbl.config(text=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.after(1000, self.update_clock)

    def refresh_usernames(self):
        con = db()
        cur = con.cursor()
        cur.execute("SELECT username FROM users ORDER BY username")
        users = [r[0] for r in cur.fetchall()]
        con.close()
        self.username_cmb["values"] = users
        if users:
            self.username_cmb.current(0)

    def try_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        if not username or not password:
            messagebox.showerror("Login", "Please select username and enter password.")
            return

        con = db()
        cur = con.cursor()
        cur.execute("SELECT username,password,role FROM users WHERE username=?", (username,))
        row = cur.fetchone()

        if not row or row["password"] != password:
            self.attempts += 1
            if self.attempts >= 5:
                self.ask_security_question(username)
            else:
                messagebox.showerror("Login", f"Invalid credentials. Attempts: {self.attempts}/5")
            con.close()
            return

        # ✅ success
        self.attempts = 0
        cur.execute("UPDATE users SET is_online=1, last_login=? WHERE username=?", (now_str(), username))
        con.commit()
        con.close()
        self.app.current_user = (row["username"], row["role"])
        self.app.show_dashboard()

    def ask_security_question(self, username):
        con = db()
        cur = con.cursor()
        cur.execute("SELECT security_question, security_answer FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        con.close()

        if not row or not row["security_question"]:
            messagebox.showerror("Security", "No security question set for this user.")
            return

        question, answer = row["security_question"], row["security_answer"]

        def check_answer():
            ans = ans_var.get().strip().lower()
            if ans == (answer or "").lower():
                messagebox.showinfo("Security", "✅ Correct! You may try again.")
                self.attempts = 0
                win.destroy()
            else:
                messagebox.showerror("Security", "❌ Wrong answer. Access denied.")

        win = tk.Toplevel(self)
        win.title("Security Check")
        tk.Label(win, text=question, font=FONT_LG, wraplength=300).pack(pady=10)
        ans_var = tk.StringVar()
        tk.Entry(win, textvariable=ans_var, font=FONT_MD).pack(pady=5)
        tk.Button(win, text="Submit", command=check_answer).pack(pady=5)

    def forgot_password(self):
        win = tk.Toplevel(self)
        win.title("Forgot Password")
        tk.Label(win, text="Enter your username:", font=FONT_MD).pack(pady=5)
        user_var = tk.StringVar()
        tk.Entry(win, textvariable=user_var, font=FONT_MD).pack(pady=5)

        def step2():
            uname = user_var.get().strip()
            if not uname:
                return
            con = db()
            cur = con.cursor()
            cur.execute("SELECT security_question, security_answer, password FROM users WHERE username=?", (uname,))
            row = cur.fetchone()
            con.close()
            if not row or not row["security_question"]:
                messagebox.showerror("Error", "No security question set for this user.")
                return

            def verify():
                ans = ans_var.get().strip().lower()
                if ans == (row["security_answer"] or "").lower():
                    messagebox.showinfo("Password", f"✅ Your password is: {row['password']}")
                    win.destroy()
                else:
                    messagebox.showerror("Error", "❌ Wrong answer.")

            tk.Label(win, text=row["security_question"], font=FONT_MD, wraplength=300).pack(pady=5)
            ans_var = tk.StringVar()
            tk.Entry(win, textvariable=ans_var, font=FONT_MD).pack(pady=5)
            tk.Button(win, text="Submit", command=verify).pack(pady=5)

        tk.Button(win, text="Next", command=step2).pack(pady=5)


# ---------- Dashboard & Sections ----------
class Dashboard(tk.Frame):
    def __init__(self, parent, app: InventoryApp):
        super().__init__(parent, bg=THEME["bg"])
        self.app = app
        self.current_section_frame: Optional[tk.Frame] = None

        header = tk.Frame(self, bg=THEME["dark"], height=60)
        header.pack(side="top", fill="x")

        tk.Label(header, text=APP_TITLE, font=FONT_XL, fg="white", bg=THEME["dark"]).pack(side="left", padx=16)

        self.dt_lbl = tk.Label(header, text=now_str(), font=FONT_MD, fg="white", bg=THEME["dark"])
        self.dt_lbl.pack(side="left", padx=16)
        self.update_header_clock()

        user_txt = f"{self.app.current_user[0]} ({self.app.current_user[1]})"
        tk.Label(header, text=user_txt, font=FONT_LG, fg="white", bg=THEME["dark"]).pack(side="right", padx=16)

        logout_btn = tk.Button(header, text="Logout", font=FONT_MD, bg=THEME["danger"], fg="white",
                               command=self.app.logout, cursor="hand2")
        logout_btn.pack(side="right", padx=8, pady=8)

        body = tk.Frame(self, bg=THEME["bg"])
        body.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(body, bg="#ECF0F1", width=200)
        self.sidebar.pack(side="left", fill="y")

        def add_btn(text, cmd):
            b = tk.Button(self.sidebar, text=text, command=cmd,
                          font=FONT_LG, bg=THEME["primary"], fg="white",
                          activebackground=THEME["accent"],
                          height=2, cursor="hand2", relief="flat")
            b.pack(fill="x", padx=8, pady=6)

        add_btn("Dashboard Home", self.show_home)
        add_btn("Employees", self.show_employees)
        add_btn("Suppliers", self.show_suppliers)
        add_btn("Products", self.show_products)
        add_btn("Sales", self.show_sales)
        add_btn("Customer", self.show_customers)
        add_btn("Reports", self.show_reports)
        add_btn("Stock Logs", self.show_stock_logs)

        self.main = tk.Frame(body, bg=THEME["bg"])
        self.main.pack(side="left", fill="both", expand=True)

        self.show_home()

    def update_header_clock(self):
        self.dt_lbl.config(text=now_str())
        self.after(1000, self.update_header_clock)

    def clear_main(self):
        if self.current_section_frame:
            self.current_section_frame.destroy()
        self.current_section_frame = tk.Frame(self.main, bg=THEME["bg"])
        self.current_section_frame.pack(fill="both", expand=True)

    def show_home(self):
        self.clear_main()
        f = self.current_section_frame

        kpi_wrap = tk.Frame(f, bg=THEME["bg"])
        kpi_wrap.pack(fill="x", padx=16, pady=16)

        def kpi(title, value, bgc):
            card = tk.Frame(kpi_wrap, bg=bgc, bd=0, relief="ridge")
            card.pack(side="left", padx=8, pady=8, fill="x", expand=True)
            tk.Label(card, text=title, font=FONT_LG, fg="white", bg=bgc).pack(anchor="w", padx=12, pady=(12, 4))
            tk.Label(card, text=value, font=("Segoe UI", 22, "bold"), fg="white", bg=bgc).pack(anchor="w", padx=12, pady=(0, 12))

        con = db(); cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM employees")
        total_emps = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM products")
        total_products = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM suppliers")
        total_suppliers = cur.fetchone()[0]
        cur.execute("SELECT IFNULL(SUM(quantity*mrp),0) FROM products")
        total_inventory_price = cur.fetchone()[0] or 0.0
        # Today's sales
        cur.execute("SELECT IFNULL(SUM(grand_total),0) FROM sales_master WHERE date LIKE ?", (today_str() + "%",))
        todays_sales = cur.fetchone()[0] or 0.0
        cur.execute("SELECT COUNT(*) FROM products WHERE quantity < reorder_level")
        low_stock_count = cur.fetchone()[0]
        con.close()

        kpi("Total Employees", total_emps, "#2196F3")
        kpi("Total Products", total_products, "#E53935")
        kpi("Total Suppliers", total_suppliers, "#43A047")
        kpi("Today’s Sales", f"₹{todays_sales:.2f}", "#FBC02D")
        kpi("Low Stock Count", low_stock_count, THEME["accent"])

        if self.app.current_user[1] == "Admin":
            online_frame = tk.LabelFrame(f, text="Online Status (Admin)", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
            online_frame.pack(fill="x", padx=16, pady=8)
            cols = ("username", "role", "is_online", "last_login")
            tv = ttk.Treeview(online_frame, columns=cols, show="headings", height=4)
            for c in cols:
                tv.heading(c, text=c.title())
                tv.column(c, width=160)
            tv.pack(fill="x", padx=8, pady=8)

            con = db(); cur = con.cursor()
            cur.execute("SELECT username, role, is_online, IFNULL(last_login,'') last_login FROM users ORDER BY role DESC, username")
            for r in cur.fetchall():
                tv.insert("", "end", values=(r["username"], r["role"], "Online" if r["is_online"] else "Offline", r["last_login"]))
            con.close()

        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        def show_graph(parent_frame):
            # Connect to DB
            con = db()
            cur = con.cursor()

            start_date = (dt.date.today() - dt.timedelta(days=13)).isoformat()
            cur.execute("""
                SELECT substr(date,1,10) AS d, SUM(grand_total) AS total
                FROM sales_master
                WHERE d >= ?
                GROUP BY d
                ORDER BY d
            """, (start_date,))
            rows = {r["d"]: r["total"] or 0.0 for r in cur.fetchall()}

            # Prepare 14-day data
            dates = [(dt.date.today() - dt.timedelta(days=13 - i)).isoformat() for i in range(14)]
            totals = [rows.get(d, 0.0) for d in dates]

            # Create matplotlib Figure
            fig = Figure(figsize=(7, 4), dpi=100)
            ax = fig.add_subplot(111)
            ax.plot(dates, totals, marker="o", color="#1ABC9C")
            ax.set_title("Sales – Last 14 Days")
            ax.set_xlabel("Date")
            ax.set_ylabel("Revenue (₹)")
            ax.tick_params(axis="x", rotation=45)

            # Clear previous graph widgets if any
            for widget in parent_frame.winfo_children():
                widget.destroy()

            # Embed graph in Tkinter
            canvas = FigureCanvasTkAgg(fig, master=parent_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)

        graph_frame = tk.Frame(f, bg=THEME["bg"])
        graph_frame.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Button(
            f, text="Show Sales Graph",
            font=FONT_LG, bg=THEME["primary"], fg="white",
            cursor="hand2",
            command=lambda: show_graph(graph_frame)  # pass frame for embedding
        ).pack(pady=8)


        tk.Button(f, text="Alerts (Low Stock)", font=FONT_LG, bg=THEME["warning"], fg="black", cursor="hand2", command=self.show_alerts).pack(pady=8)

    def show_alerts(self):
        win = tk.Toplevel(self)
        win.title("Low Stock Alerts")
        win.geometry("500x300")
        win.configure(bg=THEME["bg"])

        cols = ("Product Name", "Quantity", "Reorder Level")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=12)
        for c, w in zip(cols, [200, 100, 150]):
            tv.heading(c, text=c)
            tv.column(c, width=w, anchor="center")
        tv.pack(fill="both", expand=True, padx=10, pady=10)
        setup_treeview_striped(tv)

        con = db(); cur = con.cursor()
        cur.execute("SELECT name, quantity, reorder_level FROM products WHERE quantity < reorder_level")
        rows = cur.fetchall(); con.close()
        for r in rows:
            tv.insert("", "end", values=(r["name"], r["quantity"], r["reorder_level"]))

    def show_employees(self):
        if self.app.current_user[1] != "Admin":
            messagebox.showwarning("Access", "Employees section is Admin only.")
            return
        self.clear_main()
        SectionEmployees(self.current_section_frame)

    def show_suppliers(self):
        if self.app.current_user[1] != "Admin":
            messagebox.showwarning("Access", "Suppliers section is Admin only.")
            return
        self.clear_main()
        SectionSuppliers(self.current_section_frame)

    def show_products(self):
        self.clear_main()
        SectionProducts(self.current_section_frame, self.app.current_user)

    def show_sales(self):
        self.clear_main()
        SectionSales(self.current_section_frame, self.app.current_user)

    def show_customers(self):
        self.clear_main()
        SectionCustomers(self.current_section_frame, self.app.current_user)

    def show_reports(self):
        username, role = self.app.current_user
        if role != "Admin":
            messagebox.showwarning("Access", "Reports section is Admin only.")
            return
        self.clear_main()
        SectionReports(self.current_section_frame, self.app.current_user)

    def show_stock_logs(self):
        self.clear_main()
        SectionStockLogs(self.current_section_frame)



# ---------- Section base utilities ----------
def setup_treeview_striped(tv: ttk.Treeview):
    style = ttk.Style()
    style.configure("Treeview", rowheight=29, font=FONT_MD)
    style.map("Treeview", background=[("selected", THEME["primary"])], foreground=[("selected", "white")])
    tv.tag_configure("odd", background="#FAFAFA")
    tv.tag_configure("even", background="#ECEFF1")

def insert_rows_striped(tv: ttk.Treeview, rows: List[Tuple[Any, ...]]):
    tv.delete(*tv.get_children())
    for i, row in enumerate(rows):
        tv.insert("", "end", values=row, tags=("even" if i % 2 == 0 else "odd",))

# ---------- Employees ----------
class SectionEmployees(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=THEME["bg"])
        self.pack(fill="both", expand=True)

        sframe = tk.Frame(self, bg=THEME["bg"])
        sframe.pack(fill="x", padx=12, pady=8)
        tk.Label(sframe, text="Search (Name/ID/Phone/Email):", bg=THEME["bg"], font=FONT_MD).pack(side="left")
        self.q = tk.StringVar()
        tk.Entry(sframe, textvariable=self.q, font=FONT_MD).pack(side="left", padx=8)
        tk.Button(sframe, text="Search", font=FONT_MD, bg=THEME["primary"], fg="white", command=self.refresh).pack(side="left", padx=4)
        tk.Button(sframe, text="Reset", font=FONT_MD, command=lambda: [self.q.set(""), self.refresh()]).pack(side="left", padx=4)

        cols = ("emp_id", "name", "phone", "email", "role", "join_date")
        self.tv = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, [80, 180, 120, 220, 120, 120]):
            self.tv.heading(c, text=c.replace("_", " ").title())
            self.tv.column(c, width=w, anchor="center")
        self.tv.pack(fill="both", expand=True, padx=12, pady=8)
        setup_treeview_striped(self.tv)

        form = tk.LabelFrame(self, text="Add / Edit Employee", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
        form.pack(fill="x", padx=12, pady=8)

        self.emp_id = tk.StringVar()
        self.name = tk.StringVar()
        self.phone = tk.StringVar()
        self.email = tk.StringVar()
        self.role = tk.StringVar(value="Employee")
        self.join_date = tk.StringVar(value=today_str())

        def add_row(lbl, var, row, col, width=25):
            tk.Label(form, text=lbl, font=FONT_MD, bg=THEME["bg"]).grid(row=row, column=col * 2, padx=8, pady=6, sticky="e")
            tk.Entry(form, textvariable=var, font=FONT_MD, width=width).grid(row=row, column=col * 2 + 1, padx=8, pady=6, sticky="w")

        add_row("Emp ID", self.emp_id, 0, 0)
        add_row("Name", self.name, 0, 1)
        add_row("Phone", self.phone, 1, 0)
        add_row("Email", self.email, 1, 1)
        add_row("Role (Admin/Employee)", self.role, 2, 0)
        add_row("Join Date (YYYY-MM-DD)", self.join_date, 2, 1)

        tk.Button(form, text="Auto ID", font=FONT_MD, command=self.auto_id).grid(row=0, column=4, padx=8)
        tk.Button(form, text="Add / Save", font=FONT_MD, bg=THEME["success"], fg="white", command=self.save).grid(row=3, column=1, pady=8)
        tk.Button(form, text="Delete", font=FONT_MD, bg=THEME["danger"], fg="white", command=self.delete).grid(row=3, column=2, pady=8)
        tk.Button(form, text="Load Selected", font=FONT_MD, command=self.load_selected).grid(row=3, column=3, pady=8)
        tk.Button(form, text="Create/Sync User Login", font=FONT_MD, bg=THEME["accent"], command=self.create_user_for_employee).grid(row=3, column=4, pady=8)
        tk.Button(form, text="Set Security Question", font=FONT_MD, bg="orange", command=self.set_security_question).grid(row=3, column=5, pady=8)

        self.refresh()

    def auto_id(self):
        self.emp_id.set(padded_id("employees", "emp_id"))

    def refresh(self):
        q = f"%{self.q.get().strip()}%"
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT emp_id, name, phone, email, role, join_date
            FROM employees
            WHERE emp_id LIKE ?
               OR name LIKE ?
               OR phone LIKE ?
               OR email LIKE ?
            ORDER BY CAST(emp_id AS INTEGER)
        """, (q, q, q, q))
        rows = [(r["emp_id"], r["name"], r["phone"], r["email"], r["role"], r["join_date"]) for r in cur.fetchall()]
        con.close()
        insert_rows_striped(self.tv, rows)

    def save(self):
        emp_id = self.emp_id.get().strip()
        name = self.name.get().strip()
        phone = self.phone.get().strip()
        email = self.email.get().strip()
        role = self.role.get().strip()
        jdate = self.join_date.get().strip()

        if not emp_id:
            messagebox.showerror("Validation", "Emp ID required (use Auto ID).")
            return
        if not name:
            messagebox.showerror("Validation", "Name required.")
            return
        if not re.match(r'^[A-Za-z ]+$', name):
            messagebox.showerror("Validation", "Name must contain only alphabets and spaces.")
            return
        if not validate_phone(phone):
            messagebox.showerror("Validation", "Phone must be 10 digits starting 6-9 and unique.")
            return
        if not validate_email(email):
            messagebox.showerror("Validation", "Email must be @gmail.com or @yahoo.com and unique.")
            return
        try:
            d = dt.date.fromisoformat(jdate)
            if d > dt.date.today():
                messagebox.showerror("Validation", "Join date cannot exceed system date.")
                return
        except:
            messagebox.showerror("Validation", "Join date must be YYYY-MM-DD.")
            return
        if role not in ("Admin", "Employee"):
            messagebox.showerror("Validation", "Role must be Admin or Employee.")
            return

        con = db(); cur = con.cursor()
        try:
            cur.execute("INSERT INTO employees(emp_id,name,phone,email,role,join_date) VALUES(?,?,?,?,?,?)",
                        (emp_id, name, phone, email, role, jdate))
            con.commit()
        except sqlite3.IntegrityError:
            cur.execute("""UPDATE employees
                           SET name=?, phone=?, email=?, role=?, join_date=?
                           WHERE emp_id = ?""",
                        (name, phone, email, role, jdate, emp_id))
            con.commit()
        con.close()
        messagebox.showinfo("Saved", "Employee saved.")
        self.refresh()

    def delete(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showwarning("Delete", "Select a row to delete.")
            return
        emp_id = self.tv.item(sel[0], "values")[0]
        if not messagebox.askyesno("Confirm", f"Delete employee {emp_id}?"):
            return
        con = db(); cur = con.cursor()
        # fetch employee name to determine linked username (we use employee name -> username convention)
        cur.execute("SELECT name FROM employees WHERE emp_id=?", (emp_id,))
        row = cur.fetchone()
        name_for_user = row["name"] if row else ""
        # Delete from employees
        cur.execute("DELETE FROM employees WHERE emp_id=?", (emp_id,))
        # Also delete user login created via create_user_for_employee (username derived from employee name)
        uname = re.sub(r"\s+", "", name_for_user).lower() if name_for_user else None
        if uname:
            cur.execute("DELETE FROM users WHERE username=?", (uname,))
        con.commit()
        con.close()
        self.refresh()
        messagebox.showinfo("Deleted", f"Employee {emp_id} and linked login deleted (if existed).")

    def load_selected(self):
        sel = self.tv.selection()
        if not sel:
            return
        vals = self.tv.item(sel[0], "values")
        self.emp_id.set(vals[0])
        self.name.set(vals[1])
        self.phone.set(vals[2])
        self.email.set(vals[3])
        self.role.set(vals[4])
        self.join_date.set(vals[5])

    def create_user_for_employee(self):
        name = self.name.get().strip()
        role = self.role.get().strip()
        if not name:
            messagebox.showerror("User", "Load or enter an employee first.")
            return
        username = re.sub(r"\s+", "", name).lower()
        password = employee_default_password(name)
        con = db(); cur = con.cursor()
        try:
            cur.execute("INSERT INTO users(username,password,role,is_online,last_login) VALUES(?,?,?,?,?)",
                        (username, password, role, 0, None))
        except sqlite3.IntegrityError:
            cur.execute("UPDATE users SET password=?, role=? WHERE username=?", (password, role, username))
        con.commit(); con.close()
        messagebox.showinfo("User", f"User created/updated.\nUsername: {username}\nPassword: {password}")

    def set_security_question(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showerror("Security", "Select an employee first.")
            return
        emp_id = self.tv.item(sel[0], "values")[0]
        con = db(); cur = con.cursor()
        cur.execute("SELECT name FROM employees WHERE emp_id=?", (emp_id,))
        row = cur.fetchone(); con.close()
        if not row:
            messagebox.showerror("Security", "Employee not found.")
            return
        username = re.sub(r"\s+", "", row["name"]).lower()

        win = tk.Toplevel(self)
        win.title("Set Security Question")
        tk.Label(win, text="Security Question:", font=FONT_MD).pack(pady=5)
        q_var = tk.StringVar()
        tk.Entry(win, textvariable=q_var, font=FONT_MD, width=40).pack(pady=5)

        tk.Label(win, text="Answer:", font=FONT_MD).pack(pady=5)
        a_var = tk.StringVar()
        tk.Entry(win, textvariable=a_var, font=FONT_MD, width=40).pack(pady=5)

        def save_q():
            q = q_var.get().strip()
            a = a_var.get().strip()
            if not q or not a:
                messagebox.showerror("Error", "Both fields required.")
                return
            con = db(); cur = con.cursor()
            cur.execute("UPDATE users SET security_question=?, security_answer=? WHERE username=?", (q, a, username))
            con.commit(); con.close()
            messagebox.showinfo("Saved", "Security question updated.")
            win.destroy()

        tk.Button(win, text="Save", command=save_q).pack(pady=10)

# ---------- Suppliers ----------
class SectionSuppliers(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=THEME["bg"])
        self.pack(fill="both", expand=True)

        sframe = tk.Frame(self, bg=THEME["bg"])
        sframe.pack(fill="x", padx=12, pady=8)
        tk.Label(sframe, text="Search (Name/Contact/Company):", bg=THEME["bg"], font=FONT_MD).pack(side="left")
        self.q = tk.StringVar()
        tk.Entry(sframe, textvariable=self.q, font=FONT_MD).pack(side="left", padx=8)
        tk.Button(sframe, text="Search", font=FONT_MD, bg=THEME["primary"], fg="white", command=self.refresh).pack(side="left", padx=4)
        tk.Button(sframe, text="Reset", font=FONT_MD, command=lambda: [self.q.set(""), self.refresh()]).pack(side="left", padx=4)

        cols = ("supplier_id", "name", "company", "phone", "email", "address")
        self.tv = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, [80, 150, 150, 120, 220, 220]):
            self.tv.heading(c, text=c.replace("_", " ").title())
            self.tv.column(c, width=w, anchor="center")
        self.tv.pack(fill="both", expand=True, padx=12, pady=8)
        setup_treeview_striped(self.tv)

        form = tk.LabelFrame(self, text="Add / Edit Supplier", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
        form.pack(fill="x", padx=12, pady=8)

        self.supplier_id = tk.StringVar()
        self.name = tk.StringVar()
        self.company = tk.StringVar()
        self.phone = tk.StringVar()
        self.email = tk.StringVar()
        self.address = tk.StringVar()

        def add(lbl, var, r, c, w=25):
            tk.Label(form, text=lbl, font=FONT_MD, bg=THEME["bg"]).grid(row=r, column=c * 2, padx=8, pady=6, sticky="e")
            tk.Entry(form, textvariable=var, font=FONT_MD, width=w).grid(row=r, column=c * 2 + 1, padx=8, pady=6, sticky="w")

        add("Supplier ID", self.supplier_id, 0, 0)
        add("Name", self.name, 0, 1)
        add("Company", self.company, 1, 0)
        add("Phone", self.phone, 1, 1)
        add("Email", self.email, 2, 0)
        add("Address", self.address, 2, 1, 40)

        tk.Button(form, text="Auto ID", font=FONT_MD, command=self.auto_id).grid(row=0, column=4, padx=8)
        tk.Button(form, text="Add / Save", font=FONT_MD, bg=THEME["success"], fg="white", command=self.save).grid(row=3, column=1, pady=8)
        tk.Button(form, text="Delete", font=FONT_MD, bg=THEME["danger"], fg="white", command=self.delete).grid(row=3, column=2, pady=8)
        tk.Button(form, text="Load Selected", font=FONT_MD, command=self.load_selected).grid(row=3, column=3, pady=8)

        self.refresh()

    def auto_id(self):
        self.supplier_id.set(padded_id("suppliers", "supplier_id"))

    def refresh(self):
        q = f"%{self.q.get().strip()}%"
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT supplier_id, name, company, phone, email, address
            FROM suppliers
            WHERE name LIKE ?
               OR phone LIKE ?
               OR company LIKE ?
            ORDER BY CAST(supplier_id AS INTEGER)
        """, (q, q, q))
        rows = [(r["supplier_id"], r["name"], r["company"], r["phone"], r["email"], r["address"]) for r in cur.fetchall()]
        con.close()
        insert_rows_striped(self.tv, rows)

    def save(self):
        sid = self.supplier_id.get().strip()
        name = self.name.get().strip()
        company = self.company.get().strip()
        phone = self.phone.get().strip()
        email = self.email.get().strip()
        address = self.address.get().strip()

        if not sid:
            messagebox.showerror("Validation", "Supplier ID required (Auto ID).")
            return
        if not name:
            messagebox.showerror("Validation", "Supplier Name required.")
            return
        if not re.match(r'^[A-Za-z ]+$', name):
            messagebox.showerror("Validation", "Supplier Name must contain only alphabets and spaces.")
            return
        if not company:
            messagebox.showerror("Validation", "Company is required.")
            return
        if not validate_phone(phone):
            messagebox.showerror("Validation", "Phone invalid/duplicate.")
            return
        if not validate_email(email):
            messagebox.showerror("Validation", "Email must be @gmail.com or @yahoo.com.")
            return

        con = db(); cur = con.cursor()
        try:
            cur.execute("INSERT INTO suppliers(supplier_id,name,company,phone,email,address) VALUES(?,?,?,?,?,?)",
                        (sid, name, company, phone, email, address))
            con.commit()
        except sqlite3.IntegrityError:
            cur.execute("""UPDATE suppliers
                           SET name=?, company=?, phone=?, email=?, address=?
                           WHERE supplier_id=?""",
                        (name, company, phone, email, address, sid))
            con.commit()
        con.close()
        messagebox.showinfo("Saved", "Supplier saved.")
        self.refresh()

    def delete(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showwarning("Delete", "Select a row.")
            return
        sid = self.tv.item(sel[0], "values")[0]
        if not messagebox.askyesno("Confirm", f"Delete supplier {sid}?"):
            return
        con = db(); cur = con.cursor()
        cur.execute("DELETE FROM suppliers WHERE supplier_id=?", (sid,))
        con.commit(); con.close()
        self.refresh()

    def load_selected(self):
        sel = self.tv.selection()
        if not sel:
            return
        v = self.tv.item(sel[0], "values")
        self.supplier_id.set(v[0])
        self.name.set(v[1])
        self.company.set(v[2])
        self.phone.set(v[3])
        self.email.set(v[4])
        self.address.set(v[5])

# ---------- Products ----------
class SectionProducts(tk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent, bg=THEME["bg"])
        self.pack(fill="both", expand=True)
        self.ensure_product_columns()

        top = tk.Frame(self, bg=THEME["bg"])
        top.pack(fill="x", padx=12, pady=8)
        tk.Label(top, text="Search (Name/Category/Company):", bg=THEME["bg"], font=FONT_MD).pack(side="left")
        self.q = tk.StringVar()
        tk.Entry(top, textvariable=self.q, font=FONT_MD).pack(side="left", padx=8)
        tk.Button(top, text="Search", font=FONT_MD, bg=THEME["primary"], fg="white", command=self.refresh).pack(side="left", padx=4)
        tk.Button(top, text="Reset", font=FONT_MD, command=lambda: [self.q.set(""), self.refresh()]).pack(side="left", padx=4)
        tk.Button(top, text="Export Excel", font=FONT_MD, command=lambda: self.export_excel()).pack(side="right", padx=4)
        tk.Button(top, text="Export PDF", font=FONT_MD, command=lambda: self.export_pdf()).pack(side="right", padx=4)

        self.total_lbl = tk.Label(top, text="Total Inventory Price: ₹0.00", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
        self.total_lbl.pack(side="right", padx=12)

        cols = ("product_id", "name", "category", "supplier_id", "supplier_company",
                "quantity", "cost_price", "unit_price", "gst", "mrp", "reorder_level")
        self.tv = ttk.Treeview(self, columns=cols, show="headings")
        widths = [80, 200, 150, 100, 180, 80, 100, 100, 60, 100, 120]
        for c, w in zip(cols, widths):
            self.tv.heading(c, text=c.replace("_", " "))
            self.tv.column(c, width=w, anchor="center")
        self.tv.pack(fill="both", expand=True, padx=12, pady=8)
        setup_treeview_striped(self.tv)

        form = tk.LabelFrame(self, text="Add / Edit Product", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
        form.pack(fill="x", padx=12, pady=8)

        self.product_id = tk.StringVar()
        self.name = tk.StringVar()
        self.category = tk.StringVar()
        self.supplier_id = tk.StringVar()
        self.quantity = tk.StringVar(value="0")
        self.cost_price = tk.StringVar(value="0.00")
        self.unit_price = tk.StringVar(value="0.00")
        self.gst = tk.StringVar(value="18")
        self.mrp = tk.StringVar(value="0.00")
        self.reorder_level = tk.StringVar(value="0")

        def update_mrp(*args):
            try:
                u = float(self.unit_price.get())
                g = float(self.gst.get())
                g = min(max(g, 0), 40)
                self.gst.set(str(int(g)))
                self.mrp.set(f"{u * (1 + g / 100):.2f}")
            except:
                self.mrp.set("0.00")

        self.unit_price.trace("w", update_mrp)
        self.gst.trace("w", update_mrp)

        def add(lbl, var, r, c, w=25, ro=False):
            tk.Label(form, text=lbl, font=FONT_MD, bg=THEME["bg"]).grid(row=r, column=c * 2, padx=8, pady=6, sticky="e")
            state = "readonly" if ro else "normal"
            tk.Entry(form, textvariable=var, font=FONT_MD, width=w, state=state).grid(row=r, column=c * 2 + 1, padx=8, pady=6, sticky="w")

        add("SKU", self.product_id, 0, 0)
        add("Name", self.name, 0, 1)
        add("Category", self.category, 1, 0)

        tk.Label(form, text="Supplier", font=FONT_MD, bg=THEME["bg"]).grid(row=1, column=2, padx=8, pady=6, sticky="e")
        self.supplier_cmb = ttk.Combobox(form, textvariable=self.supplier_id, width=27, state="readonly")
        self.supplier_cmb.grid(row=1, column=3, padx=8, pady=6, sticky="w")

        add("Quantity", self.quantity, 2, 0)
        add("Cost Price", self.cost_price, 2, 1)
        add("Unit Price", self.unit_price, 2, 2)

        tk.Label(form, text="GST (%)", font=FONT_MD, bg=THEME["bg"]).grid(row=1, column=4, padx=8, pady=6, sticky="e")
        self.gst_spin = tk.Spinbox(form, from_=0, to=40, increment=1, textvariable=self.gst, font=FONT_MD, width=5, state="readonly")
        self.gst_spin.grid(row=1, column=5, padx=8, pady=6, sticky="w")

        add("MRP (Auto)", self.mrp, 3, 0, ro=True)
        add("Reorder Level", self.reorder_level, 3, 1)

        btn_frame = tk.Frame(form, bg=THEME["bg"])
        btn_frame.grid(row=4, column=0, columnspan=6, pady=10)

        tk.Button(btn_frame, text="Auto SKU", font=FONT_MD, command=self.auto_id, bg=THEME["primary"], fg="white").pack(side="left", padx=6)
        tk.Button(btn_frame, text="Add / Save", font=FONT_MD, bg=THEME["success"], fg="white", command=self.save).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Delete", font=FONT_MD, bg=THEME["danger"], fg="white", command=self.delete).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Load Selected", font=FONT_MD, command=self.load_selected).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Generate QR", font=FONT_MD, bg=THEME["accent"], fg="white", command=self.generate_qr).pack(side="left", padx=6)

        self.load_suppliers()
        self.refresh()

    def ensure_product_columns(self):
        con = db(); cur = con.cursor()
        cur.execute("PRAGMA table_info(products)")
        cols = [row[1] for row in cur.fetchall()]
        if "gst" not in cols:
            try:
                cur.execute("ALTER TABLE products ADD COLUMN gst REAL DEFAULT 18")
            except Exception:
                pass
        if "cost_price" not in cols:
            try:
                cur.execute("ALTER TABLE products ADD COLUMN cost_price REAL DEFAULT 0.0")
            except Exception:
                pass
        con.commit(); con.close()

    def load_suppliers(self):
        con = db(); cur = con.cursor()
        cur.execute("SELECT supplier_id, company FROM suppliers ORDER BY company")
        self.suppliers = cur.fetchall(); con.close()
        self.supplier_cmb["values"] = [f"{r['supplier_id']} - {r['company']}" for r in self.suppliers]

    def auto_id(self):
        self.product_id.set(padded_id("products", "product_id"))

    def refresh(self):
        q = f"%{self.q.get().strip()}%"
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT p.product_id, p.name, p.category, p.supplier_id, s.company, p.quantity, p.cost_price, p.unit_price, p.gst, p.mrp, p.reorder_level
            FROM products p
            JOIN suppliers s ON s.supplier_id = p.supplier_id
            WHERE p.name LIKE ?
               OR p.category LIKE ?
               OR s.company LIKE ?
            ORDER BY CAST(p.product_id AS INTEGER)
        """, (q, q, q))
        rows = [(r["product_id"], r["name"], r["category"], r["supplier_id"], r["company"],
                 r["quantity"], f"{r['cost_price']:.2f}", f"{r['unit_price']:.2f}",
                 f"{r['gst']:.0f}%", f"{r['mrp']:.2f}", r["reorder_level"]) for r in cur.fetchall()]
        cur.execute("SELECT IFNULL(SUM(quantity*cost_price),0) FROM products")
        total_val = cur.fetchone()[0] or 0.0
        con.close()
        insert_rows_striped(self.tv, rows)
        self.total_lbl.config(text=f"Total Inventory Price: ₹{total_val:.2f}")

    def save(self):
        pid = self.product_id.get().strip()
        name = self.name.get().strip()
        cat = self.category.get().strip()
        supplier_text = self.supplier_id.get().strip()
        qty = self.quantity.get().strip()
        cost_price = self.cost_price.get().strip()
        unit_price = self.unit_price.get().strip()
        gst = self.gst.get().strip()
        rl = self.reorder_level.get().strip()

        if not pid:
            messagebox.showerror("Validation", "SKU required (Auto SKU).")
            return
        if not name or not cat:
            messagebox.showerror("Validation", "Name and Category required.")
            return
        if "-" not in supplier_text:
            messagebox.showerror("Validation", "Select supplier from dropdown.")
            return
        supplier_id = supplier_text.split(" - ")[0].strip()

        try:
            qty = int(qty)
            rl = int(rl)
            cost_price = float(cost_price)
            unit_price = float(unit_price)
            gst = float(gst)
            gst = min(max(gst, 0), 40)
            mrp = round(unit_price * (1 + gst / 100), 2)
        except:
            messagebox.showerror("Validation", "Invalid numbers in Quantity/Price/GST/Reorder.")
            return

        if qty < 0 or rl < 0 or cost_price < 0 or unit_price < 0:
            messagebox.showerror("Validation", "Negative values not allowed.")
            return

        con = db(); cur = con.cursor()
        try:
            cur.execute("""INSERT INTO products(product_id, name, category, supplier_id, quantity, cost_price, unit_price, gst, mrp, reorder_level)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (pid, name, cat, supplier_id, qty, cost_price, unit_price, gst, mrp, rl))
            con.commit()
        except sqlite3.IntegrityError:
            cur.execute("""UPDATE products
                           SET name=?, category=?, supplier_id=?, quantity=?, cost_price=?, unit_price=?, gst=?, mrp=?, reorder_level=?
                           WHERE product_id = ?""",
                        (name, cat, supplier_id, qty, cost_price, unit_price, gst, mrp, rl, pid))
            # 🔹 Log stock movement
            cur.execute("""
                INSERT INTO stock_logs(product_id, product_name, change_type, quantity, reason, changed_by, date)
                VALUES (?,?,?,?,?,?,?)
            """, (pid, name, "IN", qty, "Product Add/Update", self.user[0] if hasattr(self, "user") else "system",
                  now_str()))
            con.commit()

            con.commit()
        con.close()
        messagebox.showinfo("Saved", "Product saved.")
        self.refresh()
        # regenerate QR after save
        self.generate_qr(pid, name, cat, gst, f"{mrp:.2f}")

    def delete(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showwarning("Delete", "Select a row.")
            return
        pid = self.tv.item(sel[0], "values")[0]
        if not messagebox.askyesno("Confirm", f"Delete product {pid}?"):
            return
        con = db(); cur = con.cursor()
        cur.execute("DELETE FROM products WHERE product_id=?", (pid,))
        con.commit(); con.close()
        self.refresh()

    def load_selected(self):
        sel = self.tv.selection()
        if not sel:
            return
        v = self.tv.item(sel[0], "values")
        self.product_id.set(v[0])
        self.name.set(v[1])
        self.category.set(v[2])
        sid = v[3]
        for i, r in enumerate(self.suppliers):
            if r["supplier_id"] == sid:
                self.supplier_cmb.current(i)
                break
        self.quantity.set(v[5])
        self.cost_price.set(v[6])
        self.unit_price.set(v[7])
        self.gst.set(v[8].replace("%", ""))
        self.mrp.set(v[9])
        self.reorder_level.set(v[10])

    def generate_qr(self, pid=None, name=None, cat=None, gst=None, mrp=None):
        try:
            import qrcode
        except Exception:
            messagebox.showerror("QR", "qrcode package not installed. pip install qrcode[pil]")
            return

        if not pid:
            pid = self.product_id.get().strip()
            name = self.name.get().strip()
            cat = self.category.get().strip()
            gst = self.gst.get().strip()
            mrp = self.mrp.get().strip()

        qr_text = f"SKU:{pid} | Name:{name} | Category:{cat} | GST:{gst}% | MRP:₹{mrp}"
        img = qrcode.make(qr_text)
        filename = f"qr_{pid}.png"
        img.save(filename)
        messagebox.showinfo("QR Generated", f"QR Code saved as {filename}")

    def export_excel(self):
        try:
            import openpyxl
        except Exception:
            messagebox.showerror("Export", "openpyxl package not installed. pip install openpyxl")
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([self.tv.heading(c)["text"] for c in self.tv["columns"]])
        for row_id in self.tv.get_children():
            row = list(self.tv.item(row_id)["values"])
            gst_index = list(self.tv["columns"]).index("gst")
            row[gst_index] = row[gst_index].replace("%", "")
            ws.append(row)
        save_path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="products.xlsx", filetypes=[("Excel Workbook", "*.xlsx")])
        if save_path:
            wb.save(save_path)
            messagebox.showinfo("Export", f"Products exported to {save_path}")

    def export_pdf(self):
        doc = SimpleDocTemplate("products.pdf", pagesize=A4)
        elements = []
        style = getSampleStyleSheet()

        data = [[self.tv.heading(c)["text"] for c in self.tv["columns"]]]
        for row_id in self.tv.get_children():
            row = list(self.tv.item(row_id)["values"])
            gst_index = list(self.tv["columns"]).index("gst")
            row[gst_index] = row[gst_index].replace("%", "")
            data.append(row)

        table = Table(data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(Paragraph("Products", style["Title"]))
        elements.append(table)
        fpath = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="products.pdf", filetypes=[("PDF", "*.pdf")])
        if fpath:
            doc = SimpleDocTemplate(fpath, pagesize=A4)
            doc.build([Paragraph("Products", style["Title"]), table])
            messagebox.showinfo("Export", f"Products exported to {fpath}")

# ---------- Customers ----------
class SectionCustomers(tk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent, bg=THEME["bg"])
        self.pack(fill="both", expand=True)

        sframe = tk.Frame(self, bg=THEME["bg"])
        sframe.pack(fill="x", padx=12, pady=8)
        tk.Label(sframe, text="Search (Name/Contact):", bg=THEME["bg"], font=FONT_MD).pack(side="left")
        self.q = tk.StringVar()
        tk.Entry(sframe, textvariable=self.q, font=FONT_MD).pack(side="left", padx=8)
        tk.Button(sframe, text="Search", font=FONT_MD, bg=THEME["primary"], fg="white", command=self.refresh).pack(side="left", padx=4)
        tk.Button(sframe, text="Reset", font=FONT_MD, command=lambda: [self.q.set(""), self.refresh()]).pack(side="left", padx=4)

        tk.Button(sframe, text="Bulk Mail / SMS", font=FONT_MD, bg=THEME["accent"], fg="white", command=self.bulk_comm_window).pack(side="right", padx=6)

        cols = ("customer_id", "name", "phone", "email")
        self.tv = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, [80, 180, 120, 220]):
            self.tv.heading(c, text=c.replace("_", " ").title())
            self.tv.column(c, width=w, anchor="center")
        self.tv.pack(fill="both", expand=True, padx=12, pady=8)
        setup_treeview_striped(self.tv)

        form = tk.LabelFrame(self, text="Add / Edit Customer", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
        form.pack(fill="x", padx=12, pady=8)

        self.customer_id = tk.StringVar()
        self.name = tk.StringVar()
        self.phone = tk.StringVar()
        self.email = tk.StringVar()

        def add(lbl, var, r, c, w=25):
            tk.Label(form, text=lbl, font=FONT_MD, bg=THEME["bg"]).grid(row=r, column=c * 2, padx=8, pady=6, sticky="e")
            tk.Entry(form, textvariable=var, font=FONT_MD, width=w).grid(row=r, column=c * 2 + 1, padx=8, pady=6, sticky="w")

        add("Customer ID", self.customer_id, 0, 0)
        add("Name", self.name, 0, 1)
        add("Phone", self.phone, 1, 0)
        add("Email", self.email, 1, 1)

        tk.Button(form, text="Auto ID", font=FONT_MD, command=self.auto_id).grid(row=0, column=4, padx=8)
        tk.Button(form, text="Add / Save", font=FONT_MD, bg=THEME["success"], fg="white", command=self.save).grid(row=3, column=1, pady=8)
        tk.Button(form, text="Delete", font=FONT_MD, bg=THEME["danger"], fg="white", command=self.delete).grid(row=3, column=2, pady=8)
        tk.Button(form, text="Load Selected", font=FONT_MD, command=self.load_selected).grid(row=3, column=3, pady=8)

        self.refresh()

    def auto_id(self):
        self.customer_id.set(padded_id("customers", "customer_id"))

    def refresh(self):
        q = f"%{self.q.get().strip()}%"
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT customer_id, name, phone, email
            FROM customers
            WHERE name LIKE ?
               OR phone LIKE ?
            ORDER BY CAST(customer_id AS INTEGER)
        """, (q, q))
        rows = [(r["customer_id"], r["name"], r["phone"], r["email"]) for r in cur.fetchall()]
        con.close()
        insert_rows_striped(self.tv, rows)

    def save(self):
        cid = self.customer_id.get().strip()
        name = self.name.get().strip()
        phone = self.phone.get().strip()
        email = self.email.get().strip()

        if not cid:
            messagebox.showerror("Validation", "Customer ID required (Auto ID).")
            return
        if not name:
            messagebox.showerror("Validation", "Name required.")
            return
        if not re.match(r'^[A-Za-z ]+$', name):
            messagebox.showerror("Validation", "Name must contain only alphabets and spaces.")
            return
        if phone and not validate_phone(phone):
            messagebox.showerror("Validation", "Phone invalid (should be 10 digits starting 6-9).")
            return
        if email and not validate_email(email):
            messagebox.showerror("Validation", "Email must be @gmail.com or @yahoo.com.")
            return

        con = db(); cur = con.cursor()
        try:
            cur.execute("INSERT INTO customers(customer_id,name,phone,email) VALUES(?,?,?,?)", (cid, name, phone, email))
            con.commit()
        except sqlite3.IntegrityError:
            cur.execute("""UPDATE customers SET name=?, phone=?, email=? WHERE customer_id = ?""", (name, phone, email, cid))
            con.commit()
        con.close()
        messagebox.showinfo("Saved", "Customer saved.")
        self.refresh()

    def delete(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showwarning("Delete", "Select a row.")
            return
        cid = self.tv.item(sel[0], "values")[0]
        if not messagebox.askyesno("Confirm", f"Delete customer {cid}?"):
            return
        con = db(); cur = con.cursor()
        cur.execute("DELETE FROM customers WHERE customer_id=?", (cid,))
        con.commit(); con.close()
        self.refresh()

    def load_selected(self):
        sel = self.tv.selection()
        if not sel:
            return
        v = self.tv.item(sel[0], "values")
        self.customer_id.set(v[0])
        self.name.set(v[1])
        self.phone.set(v[2])
        self.email.set(v[3])

    # ---------------- BULK COMMUNICATION ----------------
    def bulk_comm_window(self):
        win = tk.Toplevel(self)
        win.title("Bulk Mail / SMS")
        win.geometry("450x400")

        # Subject (email only)
        tk.Label(win, text="Subject (Email Only):", font=FONT_MD).pack(pady=5)
        subject_var = tk.StringVar()
        tk.Entry(win, textvariable=subject_var, width=50).pack()

        # Message (both mail + sms)
        tk.Label(win, text="Message:", font=FONT_MD).pack(pady=5)
        body_text = tk.Text(win, height=10, width=50)
        body_text.pack()

        # Mode selection
        mode_var = tk.StringVar(value="both")
        tk.Label(win, text="Send via:", font=FONT_MD).pack(pady=5)
        tk.Radiobutton(win, text="Email Only", variable=mode_var, value="email").pack()
        tk.Radiobutton(win, text="SMS Only", variable=mode_var, value="sms").pack()
        tk.Radiobutton(win, text="Both", variable=mode_var, value="both").pack()

        def send_action():
            subject = subject_var.get().strip()
            message = body_text.get("1.0", "end-1c").strip()
            mode = mode_var.get()

            if not message:
                messagebox.showwarning("Bulk Mail/SMS", "Message cannot be empty.")
                return

            con = db();
            cur = con.cursor()
            cur.execute("SELECT email, phone FROM customers")
            customers = cur.fetchall()
            con.close()

            recipients_mail = [c["email"] for c in customers if c["email"]]
            recipients_sms = [c["phone"] for c in customers if c["phone"]]

            if mode in ("email", "both") and recipients_mail:
                self.send_bulk_mail(subject or "Notification", message,
                                    "lalbaghenterprises", "lojn yuaa tcfn rqxa", recipients_mail)

            if mode in ("sms", "both") and recipients_sms:
                self.send_bulk_sms(message, recipients_sms)

        tk.Button(win, text="Send", bg="green", fg="white",
                  font=FONT_MD, command=send_action).pack(pady=15)

    def send_bulk_mail(self, subject, body, sender_email, sender_password, recipients):
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender_email, sender_password)

            for email in recipients:
                msg = MIMEMultipart()
                msg["From"] = sender_email
                msg["To"] = email
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))
                server.sendmail(sender_email, email, msg.as_string())

            server.quit()
            messagebox.showinfo("Bulk Mail", "✅ Bulk mail sent successfully!")

        except Exception as e:
            messagebox.showerror("Error", f"❌ Failed to send mail:\n{e}")

# ---------- Sales ----------
import smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def send_invoice_email(to_email, pdf_path, customer_name, total_amount):
    """
    Send invoice PDF via Gmail SMTP.
    ⚠️ Requires Gmail App Password (not your normal password).
    """
    sender_email = "lalbaghenterprises@gmail.com"        # CHANGE THIS
    sender_password = "lojn yuaa tcfn rqxa"       # CHANGE THIS (from Google → App Passwords)
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    subject = f"Invoice from LALBAGH ENTERPRISE - ₹{total_amount:.2f}"
    body = f"""Dear {customer_name},

Thank you for shopping with us!
Please find your invoice attached.

Best regards,
LALBAGH ENTERPRISE
"""

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Attach PDF
    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(pdf_path)}")
    msg.attach(part)

    # Send email
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(sender_email, sender_password)
    server.sendmail(sender_email, to_email, msg.as_string())
    server.quit()

class SectionSales(tk.Frame):
    def __init__(self, parent, user):
            super().__init__(parent, bg=THEME["bg"])
            self.pack(fill="both", expand=True)
            self.username, self.role = user
            self.cart = []
            self.products = {}

            # ------------------ Form ------------------
            form = tk.LabelFrame(self, text="New Sale / Cart", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
            form.pack(fill="x", padx=12, pady=8)

            self.product_pid = tk.StringVar()
            self.product_name = tk.StringVar()
            self.product_cat = tk.StringVar()
            self.product_mrp = tk.StringVar()
            self.qty = tk.StringVar(value="1")
            self.prod_discount_type = tk.StringVar(value="Flat")
            self.prod_discount_value = tk.StringVar(value="0")

            tk.Label(form, text="Product (ID - Name)", font=FONT_MD, bg=THEME["bg"]).grid(row=0, column=0, padx=8,
                                                                                          pady=6, sticky="e")
            self.product_cmb = ttk.Combobox(form, textvariable=self.product_pid, width=40, state="readonly")
            self.product_cmb.grid(row=0, column=1, padx=8, pady=6, sticky="w")
            self.product_cmb.bind("<<ComboboxSelected>>", self.on_product_selected)

            def add_ro(label, var, r, c):
                tk.Label(form, text=label, font=FONT_MD, bg=THEME["bg"]).grid(row=r, column=c * 2, padx=8, pady=6,
                                                                              sticky="e")
                tk.Entry(form, textvariable=var, font=FONT_MD, width=20, state="readonly").grid(row=r, column=c * 2 + 1,
                                                                                                padx=8, pady=6,
                                                                                                sticky="w")

            add_ro("Name", self.product_name, 1, 0)
            add_ro("Category", self.product_cat, 1, 1)
            add_ro("MRP", self.product_mrp, 1, 2)

            tk.Label(form, text="Quantity", font=FONT_MD, bg=THEME["bg"]).grid(row=2, column=0, padx=8, pady=6,
                                                                               sticky="e")
            tk.Entry(form, textvariable=self.qty, font=FONT_MD, width=8).grid(row=2, column=1, padx=8, pady=6,
                                                                              sticky="w")

            tk.Label(form, text="Discount type", font=FONT_MD, bg=THEME["bg"]).grid(row=2, column=2, padx=8, pady=6,
                                                                                    sticky="e")
            ttk.Combobox(form, textvariable=self.prod_discount_type, values=("Flat", "Percent"), width=8,
                         state="readonly").grid(row=2, column=3, padx=8, pady=6, sticky="w")
            tk.Label(form, text="Value", font=FONT_MD, bg=THEME["bg"]).grid(row=2, column=4, padx=8, pady=6, sticky="e")
            tk.Entry(form, textvariable=self.prod_discount_value, font=FONT_MD, width=8).grid(row=2, column=5, padx=8,
                                                                                              pady=6, sticky="w")

            # Hidden scanner input
            self.scan_var = tk.StringVar()
            self.scan_entry = tk.Entry(self, textvariable=self.scan_var, font=("Segoe UI", 1), width=1)
            self.scan_entry.place(x=-100, y=-100)
            self.scan_entry.bind("<Return>", lambda e: self.process_scanned_code(self.scan_var.get()))
            self.scan_entry.focus_set()

            # ------------------ Customer ------------------
            cust_frame = tk.Frame(form, bg=THEME["bg"])
            cust_frame.grid(row=3, column=0, columnspan=6, sticky="w", padx=8, pady=6)

            tk.Label(cust_frame, text="Customer:", font=FONT_MD, bg=THEME["bg"]).grid(row=0, column=0, padx=6)
            self.customer_sel = tk.StringVar()
            self.customer_cmb = ttk.Combobox(cust_frame, textvariable=self.customer_sel, width=35, state="readonly")
            self.customer_cmb.grid(row=0, column=1, padx=6)
            self.customer_cmb.bind("<<ComboboxSelected>>", lambda e: self._on_customer_choice())

            self.new_customer_name = tk.StringVar()
            self.new_customer_phone = tk.StringVar()
            self.new_customer_email = tk.StringVar()
            self.new_name_entry = tk.Entry(cust_frame, textvariable=self.new_customer_name, width=20)
            self.new_phone_entry = tk.Entry(cust_frame, textvariable=self.new_customer_phone, width=15)
            self.new_email_entry = tk.Entry(cust_frame, textvariable=self.new_customer_email, width=25)
            self.save_new_customer_btn = tk.Button(cust_frame, text="Save Customer", font=FONT_MD, bg=THEME["accent"],
                                                   fg="white", command=self.save_new_customer_inline)

            # ------------------ Buttons ------------------
            btn_row = 5
            tk.Button(form, text="Add to Cart", bg=THEME["accent"], fg="white", font=FONT_MD,
                      command=self.add_to_cart).grid(row=btn_row, column=0, padx=8, pady=8, sticky="ew")
            tk.Button(form, text="Remove Selected", bg="#D84315", fg="white", font=FONT_MD,
                      command=self.remove_selected_from_cart).grid(row=btn_row, column=1, padx=8, pady=8, sticky="ew")
            tk.Button(form, text="Clear Cart", bg="#9E9E9E", fg="white", font=FONT_MD, command=self.clear_cart).grid(
                row=btn_row, column=2, padx=8, pady=8, sticky="ew")
            tk.Button(form, text="Checkout + Invoice", bg=THEME["success"], fg="white", font=FONT_LG,
                      command=self.checkout).grid(row=btn_row + 1, column=0, columnspan=3, sticky="ew", padx=8, pady=10)
            tk.Button(form, text="Return / Refund", bg=THEME["warning"], fg="black", font=FONT_LG,
                      command=self.show_returns).grid(row=btn_row + 2, column=0, columnspan=3, sticky="ew", padx=8,
                                                      pady=6)

            # ------------------ Cart ------------------
            cart_frame = tk.LabelFrame(self, text="Cart", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
            cart_frame.pack(fill="both", padx=12, pady=8)

            cols = ("product_id", "product_name", "category", "qty", "mrp", "discount_type", "discount_value",
                    "final_total")
            self.cart_tv = ttk.Treeview(cart_frame, columns=cols, show="headings", height=7)
            for c, w in zip(cols, [80, 220, 120, 60, 80, 100, 100, 100]):
                self.cart_tv.heading(c, text=c.replace("_", " ").title())
                self.cart_tv.column(c, width=w, anchor="center")
            self.cart_tv.pack(fill="both", expand=True, padx=8, pady=8)
            setup_treeview_striped(self.cart_tv)

            totals_frame = tk.Frame(cart_frame, bg=THEME["bg"])
            totals_frame.pack(fill="x", padx=8, pady=6)
            self.subtotal_var = tk.StringVar(value="₹0.00")
            self.grand_total_var = tk.StringVar(value="₹0.00")
            tk.Label(totals_frame, text="Subtotal:", bg=THEME["bg"], font=FONT_LG).pack(side="left", padx=6)
            tk.Label(totals_frame, textvariable=self.subtotal_var, bg=THEME["bg"], font=FONT_LG).pack(side="left",
                                                                                                      padx=6)
            tk.Label(totals_frame, text="   Grand Total:", bg=THEME["bg"], font=FONT_LG).pack(side="left", padx=6)
            tk.Label(totals_frame, textvariable=self.grand_total_var, bg=THEME["bg"], font=FONT_LG).pack(side="left",
                                                                                                         padx=6)

            # ------------------ Sales History ------------------
            bot = tk.Frame(self, bg=THEME["bg"])
            bot.pack(fill="both", expand=True, padx=12, pady=8)

            tk.Label(bot, text="Sales History (recent)", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"]).pack(
                anchor="w", padx=8, pady=4)
            cols = ("sale_id", "date", "sold_by", "customer_name", "grand_total")
            self.sales_tv = ttk.Treeview(bot, columns=cols, show="headings", height=8)
            for c, w in zip(cols, [100, 140, 120, 200, 120]):
                self.sales_tv.heading(c, text=c.replace("_", " ").title())
                self.sales_tv.column(c, width=w, anchor="center")
            self.sales_tv.pack(fill="both", expand=True, padx=8, pady=6)
            setup_treeview_striped(self.sales_tv)

            # ------------------ Returns ------------------
            ret_frame = tk.LabelFrame(self, text="Return History (recent)", bg=THEME["bg"], font=FONT_LG,
                                      fg=THEME["dark"])
            ret_frame.pack(fill="both", padx=12, pady=8)

            cols = ("sale_id", "product_id", "qty", "refund_amt", "date", "reason")
            self.returns_tv = ttk.Treeview(ret_frame, columns=cols, show="headings", height=6)
            for c, w in zip(cols, [80, 100, 60, 100, 140, 200]):
                self.returns_tv.heading(c, text=c.replace("_", " ").title())
                self.returns_tv.column(c, width=w, anchor="center")
            self.returns_tv.pack(fill="both", expand=True, padx=8, pady=6)
            setup_treeview_striped(self.returns_tv)

            # Init
            self.load_products()
            self.load_customers()
            self.refresh_sales_history()
            self.refresh_returns_history()

        # ---------------- Product / Customer Loaders ----------------
    def load_products(self):
            con = db();
            cur = con.cursor()
            cur.execute("SELECT product_id, name, category, mrp, quantity FROM products ORDER BY name")
            rows = cur.fetchall();
            con.close()
            formatted = []
            self.products = {}
            for r in rows:
                key = f"{r['product_id']} - {r['name']}"
                self.products[key] = r
                formatted.append(key)
            self.product_cmb["values"] = formatted

    def load_customers(self):
            con = db();
            cur = con.cursor()
            cur.execute("SELECT customer_id, name FROM customers ORDER BY name")
            rows = cur.fetchall();
            con.close()
            formatted = [""]  # Walk-in
            formatted.extend([f"{r['customer_id']} - {r['name']}" for r in rows])
            formatted.append("Add New Customer")
            self.customer_cmb["values"] = formatted
            self.customer_cmb.set("")

    def _on_customer_choice(self):
            sel = self.customer_sel.get()
            self._hide_new_customer_fields()
            if sel == "Add New Customer":
                parent = self.customer_cmb.master
                self.new_name_entry.grid(row=1, column=1, padx=6, pady=4, sticky="w")
                self.new_phone_entry.grid(row=1, column=2, padx=6, pady=4, sticky="w")
                self.new_email_entry.grid(row=1, column=3, padx=6, pady=4, sticky="w")
                self.save_new_customer_btn.grid(row=1, column=4, padx=8)
            else:
                self.new_customer_name.set("");
                self.new_customer_phone.set("");
                self.new_customer_email.set("")

    def _hide_new_customer_fields(self):
            for w in (self.new_name_entry, self.new_phone_entry, self.new_email_entry, self.save_new_customer_btn):
                w.grid_forget()

    def save_new_customer_inline(self):
            name = self.new_customer_name.get().strip()
            phone = self.new_customer_phone.get().strip()
            email = self.new_customer_email.get().strip()
            if not name:
                messagebox.showerror("Customer", "Name required for new customer.")
                return
            if phone and not validate_phone(phone):
                messagebox.showerror("Customer", "Phone invalid (should be 10 digits starting 6-9).")
                return
            if email and not validate_email(email):
                messagebox.showerror("Customer", "Email must be valid.")
                return
            cid = padded_id("customers", "customer_id")
            con = db();
            cur = con.cursor()
            try:
                cur.execute("INSERT INTO customers(customer_id,name,phone,email) VALUES(?,?,?,?)",
                            (cid, name, phone, email))
                con.commit()
            except sqlite3.IntegrityError as e:
                con.rollback();
                con.close()
                messagebox.showerror("Customer", f"Error saving: {e}")
                return
            con.close()
            messagebox.showinfo("Customer", f"Customer saved ({cid}) and selected.")
            self.load_customers()
            self.customer_cmb.set(f"{cid} - {name}")
            self._hide_new_customer_fields()

        # ---------------- Cart Handling ----------------
    def on_product_selected(self, e=None):
            key = self.product_pid.get()
            if not key: return
            p = self.products.get(key)
            if not p: return
            self.product_name.set(p["name"])
            self.product_cat.set(p["category"])
            self.product_mrp.set(f"{p['mrp']:.2f}")

    def add_to_cart(self):
            key = self.product_pid.get()
            if not key:
                messagebox.showwarning("Add", "Select a product.")
                return
            p = self.products.get(key)
            if not p:
                messagebox.showerror("Add", "Product not found.")
                return
            try:
                qty = int(self.qty.get() or 0)
            except:
                messagebox.showerror("Qty", "Quantity must be integer.")
                return
            if qty <= 0:
                messagebox.showerror("Qty", "Quantity must be > 0.")
                return
            try:
                dval = float(self.prod_discount_value.get() or 0)
            except:
                dval = 0.0

            line_total = qty * float(p["mrp"])
            if self.prod_discount_type.get() == "Flat":
                if dval < 0 or dval > line_total:
                    messagebox.showerror("Discount", "Flat discount invalid.")
                    return
                discount_amt = dval
            else:
                if dval < 0 or dval > 90:
                    messagebox.showerror("Discount", "Percent must be 0–90.")
                    return
                discount_amt = line_total * (dval / 100.0)
            final_total = max(line_total - discount_amt, 0.0)

            # merge same product+discount
            for i, item in enumerate(self.cart):
                if (item["pid"] == p["product_id"] and item["discount_type"] == self.prod_discount_type.get() and item[
                    "discount_value"] == dval):
                    new_qty = item["qty"] + qty
                    if new_qty > p["quantity"]:
                        messagebox.showerror("Stock",
                                             f"Not enough stock (available {p['quantity']}, trying {new_qty}).")
                        return
                    item["qty"] = new_qty
                    line_total = new_qty * item["mrp"]
                    discount_amt = item["discount_value"] if item["discount_type"] == "Flat" else line_total * (
                                item["discount_value"] / 100.0)
                    item["final_total"] = round(line_total - discount_amt, 2)
                    vals = (item["pid"], item["name"], item["cat"], item["qty"],
                            f"{item['mrp']:.2f}", item["discount_type"], f"{item['discount_value']}",
                            f"{item['final_total']:.2f}")
                    self.cart_tv.item(self.cart_tv.get_children()[i], values=vals)
                    self.update_totals()
                    return

            if qty > p["quantity"]:
                messagebox.showerror("Stock", f"Not enough stock (available {p['quantity']}).")
                return

            item = {"pid": p["product_id"], "name": p["name"], "cat": p["category"],
                    "qty": qty, "mrp": float(p["mrp"]),
                    "discount_type": self.prod_discount_type.get(),
                    "discount_value": dval, "final_total": round(final_total, 2)}
            self.cart.append(item)
            self.cart_tv.insert("", "end", values=(item["pid"], item["name"], item["cat"], item["qty"],
                                                   f"{item['mrp']:.2f}", item["discount_type"],
                                                   f"{item['discount_value']}", f"{item['final_total']:.2f}"))
            self.update_totals()

    def remove_selected_from_cart(self):
            sel = self.cart_tv.selection()
            if not sel: return
            idx = self.cart_tv.index(sel[0])
            item = self.cart[idx]
            if item["qty"] > 1:
                item["qty"] -= 1
                disc = item["discount_value"] if item["discount_type"] == "Flat" else item["qty"] * item["mrp"] * (
                            item["discount_value"] / 100)
                item["final_total"] = round(item["qty"] * item["mrp"] - disc, 2)
                vals = (item["pid"], item["name"], item["cat"], item["qty"],
                        f"{item['mrp']:.2f}", item["discount_type"], f"{item['discount_value']}",
                        f"{item['final_total']:.2f}")
                self.cart_tv.item(sel[0], values=vals)
            else:
                self.cart_tv.delete(sel[0]);
                del self.cart[idx]
            self.update_totals()

    def clear_cart(self):
            self.cart = [];
            self.cart_tv.delete(*self.cart_tv.get_children());
            self.update_totals()

    def update_totals(self):
            subtotal = sum(item["final_total"] for item in self.cart)
            self.subtotal_var.set(f"₹{subtotal:.2f}")
            self.grand_total_var.set(f"₹{subtotal:.2f}")

        # ---------------- Checkout ----------------
    def checkout(self):
            if not self.cart:
                messagebox.showwarning("Checkout", "Cart is empty!");
                return

            cust_sel = self.customer_sel.get().strip()
            customer_name, customer_phone, customer_email = "Walk-in", "", ""
            if cust_sel and cust_sel != "Add New Customer":
                parts = cust_sel.split(" - ", 1)
                customer_name = parts[1] if len(parts) > 1 else cust_sel
                con = db();
                cur = con.cursor()
                cur.execute("SELECT phone, email FROM customers WHERE customer_id=?", (parts[0],))
                r = cur.fetchone();
                con.close()
                if r:
                    if r["phone"]: customer_phone = r["phone"]
                    if r["email"]: customer_email = r["email"]
            else:
                if self.new_customer_name.get().strip():
                    self.save_new_customer_inline()
                    cs = self.customer_sel.get();
                    parts = cs.split(" - ", 1) if cs else []
                    customer_name = parts[1] if len(parts) > 1 else self.new_customer_name.get().strip()
                    customer_phone = self.new_customer_phone.get().strip()
                    customer_email = self.new_customer_email.get().strip()

            subtotal = sum(item["final_total"] for item in self.cart)
            grand_total = round(subtotal, 2)

            con = db();
            cur = con.cursor()
            try:
                now = dt.datetime.now()
                cur.execute("""INSERT INTO sales_master(date, sold_by, customer_name, customer_phone, subtotal, grand_total)
                               VALUES (?,?,?,?,?,?)""",
                            (now.strftime("%Y-%m-%d %H:%M:%S"), self.username, customer_name, customer_phone, subtotal,
                             grand_total))
                sale_id = cur.lastrowid
                for item in self.cart:
                    cur.execute("""INSERT INTO sales_items(sale_id, product_id, product_name, category, quantity, mrp, total_price, discount_type, discount_value, effective_total)
                                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                (sale_id, item["pid"], item["name"], item["cat"], item["qty"], item["mrp"],
                                 item["qty"] * item["mrp"],
                                 item["discount_type"], item["discount_value"], item["final_total"]))
                    cur.execute("UPDATE products SET quantity = quantity - ? WHERE product_id=?",
                                (item["qty"], item["pid"]))
                con.commit()
            except Exception as e:
                con.rollback();
                messagebox.showerror("Checkout", f"Error: {e}");
                return
            finally:
                con.close()

            # --- Invoice PDF path ---
            invoice_file = f"invoice_{sale_id}_{dt.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
            try:
                self.generate_invoice_with_qr(sale_id, invoice_file)
                messagebox.showinfo("Invoice", f"Invoice generated:\n{invoice_file}\nSale ID: {sale_id}")
            except Exception as e:
                messagebox.showerror("Invoice", f"Failed to generate: {e}");
                return

            # --- Email invoice if email exists ---
            if customer_email:
                try:
                    send_invoice_email(customer_email, invoice_file, customer_name, grand_total)
                    messagebox.showinfo("Invoice Email", f"Invoice emailed to {customer_email}")
                except Exception as e:
                    messagebox.showwarning("Email Error", f"Could not send invoice email:\n{e}")

            # --- Reset ---
            self.cart.clear();
            self.cart_tv.delete(*self.cart_tv.get_children())
            self.update_totals();
            self.load_products();
            self.load_customers()
            self.refresh_sales_history();
            self.refresh_returns_history()

        # ---------------- Invoice PDF ----------------
    def generate_invoice_with_qr(self, sale_id, filename):
            con = db();
            cur = con.cursor()
            cur.execute("SELECT * FROM sales_master WHERE sale_id=?", (sale_id,));
            master = cur.fetchone()
            cur.execute("""SELECT product_name, category, quantity, mrp, total_price, discount_type, discount_value, effective_total
                           FROM sales_items WHERE sale_id=?""", (sale_id,));
            items = cur.fetchall();
            con.close()

            doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20)
            story = [];
            styles = getSampleStyleSheet()
            story.append(Paragraph("<b>LALBAGH ENTERPRISE</b>", styles["Title"]))
            story.append(Paragraph("77, OMRAHGANG, LALBAGH, MURSHIDABAD, WEST BENGAL", styles["Normal"]))
            story.append(Spacer(1, 12))
            invoice_no = f"{sale_id}-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
            story.append(Paragraph(f"<b>Invoice No:</b> {invoice_no}", styles["Normal"]))
            story.append(Paragraph(f"<b>Date:</b> {master['date']}", styles["Normal"]))
            story.append(Paragraph(f"<b>Customer:</b> {master['customer_name']}", styles["Normal"]))
            story.append(Paragraph(f"<b>Phone:</b> {master['customer_phone']}", styles["Normal"]))
            story.append(Spacer(1, 12))

            data = [["Product", "Category", "Qty", "MRP", "Line Total", "Discount", "Final"]]
            for it in items:
                data.append([it["product_name"], it["category"], it["quantity"], f"{it['mrp']:.2f}",
                             f"{it['total_price']:.2f}", f"{it['discount_type']} {it['discount_value']}",
                             f"{it['effective_total']:.2f}"])
            table = Table(data, colWidths=[150, 80, 50, 60, 80, 80, 80])
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
                                       ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                       ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                       ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
            story.append(table);
            story.append(Spacer(1, 12))

            totals_data = [["Subtotal", f"₹ {master['subtotal']:.2f}"],
                           ["Grand Total", f"₹ {master['grand_total']:.2f}"]]
            totals_table = Table(totals_data, colWidths=[300, 200])
            totals_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                                              ("FONTNAME", (-1, -1), (-1, -1), "Helvetica-Bold"),
                                              ("TEXTCOLOR", (-1, -1), (-1, -1), colors.green),
                                              ("FONTSIZE", (-1, -1), (-1, -1), 14)]))
            story.append(totals_table);
            story.append(Spacer(1, 20))

            payload = {"invoice_no": invoice_no, "sale_id": sale_id, "date": master["date"],
                       "customer": {"name": master["customer_name"], "phone": master["customer_phone"]},
                       "totals": {"subtotal": master["subtotal"], "grand_total": master["grand_total"]}, "items": []}
            for it in items:
                payload["items"].append({"product_name": it["product_name"], "category": it["category"],
                                         "qty": it["quantity"], "mrp": float(it["mrp"]),
                                         "final": float(it["effective_total"])})
            qr_text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            qr_code = qr_barcode.QrCodeWidget(qr_text);
            bounds = qr_code.getBounds();
            size = 200
            d = Drawing(size, size,
                        transform=[size / (bounds[2] - bounds[0]), 0, 0, size / (bounds[3] - bounds[1]), 0, 0])
            d.add(qr_code);
            story.append(d)
            doc.build(story)

    # ---------------- returns / refund UI & processing ----------------
    def show_returns(self):
        win = tk.Toplevel(self)
        win.title("Process Return / Refund")
        win.geometry("900x520")
        win.configure(bg=THEME["bg"])

        sale_id_var = tk.StringVar()
        reason_var = tk.StringVar()
        refund_data = []

        f_top = tk.Frame(win, bg=THEME["bg"])
        f_top.pack(fill="x", pady=6)
        tk.Label(f_top, text="Select Recent Sale (last 10 days):", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        sale_combo = ttk.Combobox(f_top, textvariable=sale_id_var, width=80, state="readonly")
        sale_combo.pack(side="left", padx=6)

        ten_days_ago = (dt.datetime.now() - dt.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        con = db(); cur = con.cursor()
        cur.execute("SELECT sale_id, date, customer_name, grand_total FROM sales_master WHERE date >= ? ORDER BY sale_id DESC LIMIT 50", (ten_days_ago,))
        rows = cur.fetchall(); con.close()
        ids = []
        if rows:
            formatted = [f"{r['sale_id']} - {r['date']} - {r['customer_name']} - ₹{r['grand_total']:.2f}" for r in rows]
            ids = [str(r['sale_id']) for r in rows]
            sale_combo['values'] = formatted

            def set_sale(ev=None):
                idx = sale_combo.current()
                if idx >= 0:
                    sale_id_var.set(ids[idx])
                    load_sale()

            sale_combo.bind("<<ComboboxSelected>>", set_sale)

        cols = ("Product", "Qty Sold", "Unit Price", "Refund Qty", "Refund Amount")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=10)
        for c, w in zip(cols, [300, 80, 100, 100, 120]):
            tv.heading(c, text=c)
            tv.column(c, width=w, anchor="center")
        tv.pack(fill="both", expand=True, padx=8, pady=6)
        setup_treeview_striped(tv)

        def load_sale():
            tv.delete(*tv.get_children())
            refund_data.clear()
            sid = sale_id_var.get().strip()
            if not sid:
                return
            con = db(); cur = con.cursor()
            cur.execute("""SELECT product_id, product_name, quantity, mrp, effective_total FROM sales_items WHERE sale_id=?""", (sid,))
            rows = cur.fetchall(); con.close()
            for r in rows:
                refund_data.append([sid, r["product_id"], r["product_name"], r["quantity"], r["mrp"], 0, 0.0])
                tv.insert("", "end", values=(r["product_name"], r["quantity"], f"₹{r['mrp']:.2f}", 0, "₹0.00"))

        def set_refund(event):
            sel = tv.selection()
            if not sel:
                return
            idx = tv.index(sel[0])
            max_q = refund_data[idx][3]
            entry = simpledialog.askinteger("Refund Qty", f"Enter refund qty for {refund_data[idx][2]} (max {max_q}):", minvalue=1, maxvalue=max_q, parent=win)
            if entry:
                sid, pid, name, sold_qty, mrp, _, _ = refund_data[idx]
                con = db(); cur = con.cursor()
                cur.execute("SELECT effective_total FROM sales_items WHERE sale_id=? AND product_id=?", (sid, pid))
                row = cur.fetchone(); con.close()
                eff_total = row["effective_total"] if row and row["effective_total"] else (sold_qty * mrp)
                unit_price = eff_total / sold_qty if sold_qty else mrp
                r_amt = round(unit_price * entry, 2)
                refund_data[idx][5] = entry
                refund_data[idx][6] = r_amt
                tv.item(sel[0], values=(name, sold_qty, f"₹{mrp:.2f}", entry, f"₹{r_amt:.2f}"))

        tv.bind("<Double-1>", set_refund)

        f_bottom = tk.Frame(win, bg=THEME["bg"])
        f_bottom.pack(fill="x", pady=6)
        tk.Label(f_bottom, text="Reason for Return:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=6)
        reason_entry = tk.Entry(f_bottom, textvariable=reason_var, width=60)
        reason_entry.pack(side="left", padx=6)

        def process_all_refunds():
            reason = reason_var.get().strip()
            if not reason:
                messagebox.showwarning("Refund", "Reason is required.")
                return
            any_refund = False
            con = db(); cur = con.cursor()
            try:
                for sid, pid, name, sold_qty, mrp, r_qty, r_amt in refund_data:
                    if r_qty and r_qty > 0:
                        cur.execute("SELECT IFNULL(SUM(quantity),0) as refunded FROM returns WHERE sale_id=? AND product_id=?", (sid, pid))
                        already = cur.fetchone()["refunded"]
                        if r_qty + already > sold_qty:
                            messagebox.showerror("Refund", f"Cannot refund {r_qty} for {name}. Already refunded {already} of {sold_qty}.")
                            con.rollback()
                            return
                        cur.execute("INSERT INTO returns (sale_id, product_id, quantity, refund_amount, date, reason) VALUES (?,?,?,?,?,?)",
                                    (sid, pid, r_qty, r_amt, today_str(), reason))
                        cur.execute("UPDATE products SET quantity = quantity + ? WHERE product_id=?", (r_qty, pid))
                        cur.execute("SELECT effective_total FROM sales_items WHERE sale_id=? AND product_id=?", (sid, pid))
                        e = cur.fetchone()
                        if e:
                            new_eff = max((e["effective_total"] or 0.0) - r_amt, 0.0)
                            cur.execute("UPDATE sales_items SET effective_total=? WHERE sale_id=? AND product_id=?", (new_eff, sid, pid))
                        cur.execute("SELECT grand_total FROM sales_master WHERE sale_id=?", (sid,))
                        g = cur.fetchone()
                        if g:
                            newg = max((g["grand_total"] or 0.0) - r_amt, 0.0)
                            cur.execute("UPDATE sales_master SET grand_total=? WHERE sale_id=?", (newg, sid))
                        any_refund = True
                if any_refund:
                    con.commit()
                    messagebox.showinfo("Refund", "Refund(s) processed successfully.")
                    win.destroy()
                    self.load_products()
                    self.refresh_sales_history()
                else:
                    messagebox.showwarning("Refund", "No refund quantities entered.")
            except Exception as e:
                con.rollback()
                messagebox.showerror("Refund", f"Error processing refunds: {e}")
            finally:
                con.close()

        tk.Button(f_bottom, text="Process Refund(s)", bg=THEME["danger"], fg="white", command=process_all_refunds).pack(pady=8)

    def refresh_sales_history(self):
        con = db(); cur = con.cursor()
        cur.execute("SELECT sale_id,date,sold_by,customer_name,grand_total FROM sales_master ORDER BY sale_id DESC LIMIT 50")
        rows = cur.fetchall(); con.close()
        self.sales_tv.delete(*self.sales_tv.get_children())
        for r in rows:
            self.sales_tv.insert("", "end", values=(r["sale_id"], r["date"], r["sold_by"], r["customer_name"], f"₹{r['grand_total']:.2f}"))

    def refresh_returns_history(self):
        con = db(); cur = con.cursor()
        cur.execute("SELECT sale_id,product_id,quantity,refund_amount,date,reason FROM returns ORDER BY date DESC LIMIT 50")
        rows = cur.fetchall(); con.close()
        self.returns_tv.delete(*self.returns_tv.get_children())
        for r in rows:
            self.returns_tv.insert("", "end", values=(r["sale_id"], r["product_id"], r["quantity"], f"₹{r['refund_amount']:.2f}", r["date"], r["reason"]))

    # ---------------- QR / scanner integration ----------------
    def process_scanned_code(self, code: str):
        code = (code or "").strip()
        if not code: return
        if "SKU:" in code:
            for part in code.split("|"):
                if part.strip().startswith("SKU:"):
                    code = part.replace("SKU:", "").strip()
                    break
        pid = None
        if code.upper().startswith("PID:"):
            pid = code.split(":",1)[1].strip()
        elif " - " in code:
            pid = code.split(" - ",1)[0].strip()
        else:
            pid = code
        matched_key = None
        for k in self.products.keys():
            if k.startswith(pid) or k.split(" - ",1)[0]==pid:
                matched_key = k; break
        if matched_key:
            self.product_cmb.set(matched_key); self.product_pid.set(matched_key); self.on_product_selected()
            self.qty.set("1"); self.prod_discount_value.set("0"); self.add_to_cart(); self.play_beep()
            self.scan_var.set(""); self.scan_entry.focus_set(); return
        con = db(); cur = con.cursor()
        cur.execute("SELECT product_id,name FROM products WHERE product_id=?", (pid,))
        row = cur.fetchone(); con.close()
        if row:
            pname = f"{row['product_id']} - {row['name']}"
            self.product_cmb.set(pname); self.product_pid.set(pname); self.on_product_selected()
            self.qty.set("1"); self.prod_discount_value.set("0"); self.add_to_cart(); self.play_beep()
        else:
            messagebox.showerror("Scan", f"❌ Product not found: {pid}"); self.play_beep(error=True)
        self.scan_var.set(""); self.scan_entry.focus_set()

    def play_beep(self, error=False):
        try:
            if platform.system()=="Windows":
                import winsound
                winsound.Beep(400 if error else 1000, 200 if error else 150)
            else:
                # Try common bell
                print("\a")
        except Exception:
            pass

# ---------- REPORTS ----------
# Full SectionReports class (complete)
import os
import tempfile
import datetime as dt
from typing import List, Tuple

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkcalendar import DateEntry

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# Assumes these exist in your codebase:
# db(), now_str(), setup_treeview_striped(tv), insert_rows_striped(tv, rows),
# export_treeview_to_excel(tree, suggested_name), export_treeview_to_pdf(tree, suggested_name, title),
# THEME, FONT_XL, FONT_LG, FONT_MD

class SectionReports(tk.Frame):
    def __init__(self, parent, user: Tuple[str, str]):
        """
        Full Reports dashboard:
          - Admin-only access
          - KPI cards (with buttons)
          - Chart & report buttons
          - Sales history with date filters + export
          - Profit Margin Report, Profit Analysis (with forecast)
          - Return History (tries `returns` table else negative sales_items)
          - Consolidated Export (PDF) with logo.png embedded (if present)
        """
        username, role = user
        if role != "Admin":
            messagebox.showerror("Access Denied", "Reports are available only for Admin users.")
            parent.destroy()
            return

        super().__init__(parent, bg=THEME["bg"])
        self.pack(fill="both", expand=True)
        self.user = username

        # Title
        tk.Label(self, text="Reports Dashboard (Admin Only)", font=FONT_XL, bg=THEME["bg"], fg=THEME["dark"]).pack(pady=8)

        # KPI frame
        kpi_frame = tk.Frame(self, bg=THEME["bg"])
        kpi_frame.pack(fill="x", padx=12, pady=8)

        self.kpi_sales_lbl = tk.Label(kpi_frame, text="Total Sales: ₹0.00", font=FONT_LG, bg=THEME["primary"], fg="white", width=34, relief="ridge")
        self.kpi_sales_lbl.grid(row=0, column=0, padx=6, pady=6)
        self.kpi_customers_lbl = tk.Label(kpi_frame, text="Total Customers: 0", font=FONT_LG, bg=THEME["success"], fg="white", width=34, relief="ridge")
        self.kpi_customers_lbl.grid(row=0, column=1, padx=6, pady=6)
        self.kpi_profit_lbl = tk.Label(kpi_frame, text="Profit: ₹0.00", font=FONT_LG, bg=THEME["danger"], fg="white", width=34, relief="ridge")
        self.kpi_profit_lbl.grid(row=0, column=2, padx=6, pady=6)

        tk.Button(kpi_frame, text="Refresh KPIs", command=self.refresh_kpis, font=FONT_MD).grid(row=1, column=0, pady=(0,8))
        tk.Button(kpi_frame, text="Customer Report", command=self.open_customer_report, font=FONT_MD).grid(row=1, column=1, pady=(0,8))
        tk.Button(kpi_frame, text="Profit Analysis", command=self.show_profit_analysis, font=FONT_MD).grid(row=1, column=2, pady=(0,8))

        # Chart/report buttons
        btns_frame = tk.Frame(self, bg=THEME["bg"])
        btns_frame.pack(fill="x", padx=12, pady=6)

        btn_specs = [
            ("Monthly Sales Trend", self.show_monthly_sales_trend, THEME["primary"]),
            ("Daily Sales Trend", self.show_daily_sales_trend, THEME["accent"]),
            ("Top 5 Products", self.show_top_products, THEME["success"]),
            ("Supplier vs Supplier", self.show_supplier_comparison, THEME["warning"]),
            ("Product Sales Share (Pie)", self.show_product_sales_share, THEME["accent"]),
            ("Profit Margin Report", self.show_profit_margin_report, THEME["danger"]),
            ("Return History", self.show_return_history, "#8E44AD"),
            ("Export All Reports (PDF)", self.export_all_reports, THEME["success"]),
        ]

        for i, (txt, cmd, bgc) in enumerate(btn_specs):
            tk.Button(btns_frame, text=txt, command=cmd, font=FONT_MD, bg=bgc, fg="white").grid(row=0, column=i, padx=6, pady=6, sticky="ew")

        # Sales History section
        history_frame = tk.LabelFrame(self, text="Sales History", bg=THEME["bg"], font=FONT_LG, fg=THEME["dark"])
        history_frame.pack(fill="both", expand=True, padx=12, pady=12)

        filter_frame = tk.Frame(history_frame, bg=THEME["bg"])
        filter_frame.pack(fill="x", padx=6, pady=6)
        tk.Label(filter_frame, text="From:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        self.hist_from = DateEntry(filter_frame, width=12, date_pattern="yyyy-mm-dd")
        self.hist_from.set_date(dt.date.today() - dt.timedelta(days=30))
        self.hist_from.pack(side="left")
        tk.Label(filter_frame, text="To:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        self.hist_to = DateEntry(filter_frame, width=12, date_pattern="yyyy-mm-dd")
        self.hist_to.set_date(dt.date.today())
        self.hist_to.pack(side="left")
        tk.Button(filter_frame, text="Apply", bg=THEME["primary"], fg="white", command=self.refresh_sales_history).pack(side="left", padx=6)

        tk.Button(filter_frame, text="Export Excel", bg=THEME["accent"], fg="white", command=self.export_sales_history_excel).pack(side="right", padx=6)
        tk.Button(filter_frame, text="Export PDF", bg=THEME["primary"], fg="white", command=self.export_sales_history_pdf).pack(side="right", padx=6)

        cols = ("sale_id", "date", "product_name", "category", "quantity", "mrp", "effective_total", "sold_by", "customer_name", "customer_phone")
        self.sales_tv = ttk.Treeview(history_frame, columns=cols, show="headings", height=12)
        widths = [70,100,220,120,80,80,110,100,160,120]
        for c, w in zip(cols, widths):
            self.sales_tv.heading(c, text=c.replace("_", " ").title())
            self.sales_tv.column(c, width=w, anchor="center")
        self.sales_tv.pack(fill="both", expand=True, padx=6, pady=6)
        setup_treeview_striped(self.sales_tv)

        # initial data
        self.refresh_kpis()
        self.refresh_sales_history()

    # ---------- KPI calculations (use effective_total - cost*qty) ----------
    def refresh_kpis(self):
        con = db(); cur = con.cursor()
        # total sales (grand_total from sales_master)
        cur.execute("SELECT IFNULL(SUM(grand_total),0) AS total_sales FROM sales_master")
        row = cur.fetchone(); total_sales = row["total_sales"] if row and "total_sales" in row.keys() else 0.0

        # total customers
        cur.execute("SELECT COUNT(*) AS cnt FROM customers")
        row = cur.fetchone(); total_customers = row["cnt"] if row and "cnt" in row.keys() else 0

        # profit estimate using effective_total minus cost
        cur.execute("""
            SELECT IFNULL(SUM(si.effective_total - (IFNULL(p.cost_price,0) * si.quantity)), 0) AS profit_est
            FROM sales_items si
            LEFT JOIN products p ON si.product_id = p.product_id
        """)
        row = cur.fetchone(); profit_est = row["profit_est"] if row and "profit_est" in row.keys() else 0.0
        con.close()

        self.kpi_sales_lbl.config(text=f"Total Sales: ₹{total_sales:,.2f}")
        self.kpi_customers_lbl.config(text=f"Total Customers: {total_customers}")
        self.kpi_profit_lbl.config(text=f"Profit: ₹{profit_est:,.2f}")

    # ---------- Sales History ----------
    def refresh_sales_history(self):
        start = self.hist_from.get_date().strftime("%Y-%m-%d")
        end = self.hist_to.get_date().strftime("%Y-%m-%d")
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT sm.sale_id, sm.date, si.product_name, si.category, si.quantity, si.mrp,
                   si.effective_total, sm.sold_by, sm.customer_name, sm.customer_phone
            FROM sales_master sm
            JOIN sales_items si ON si.sale_id = sm.sale_id
            WHERE date(sm.date) BETWEEN ? AND ?
            ORDER BY sm.date DESC
        """, (start, end))
        rows = cur.fetchall(); con.close()
        out = []
        for r in rows:
            out.append((
                r["sale_id"],
                r["date"],
                r["product_name"],
                r["category"],
                r["quantity"],
                f"{r['mrp']:.2f}" if r["mrp"] is not None else "0.00",
                f"{r['effective_total']:.2f}" if r["effective_total"] is not None else "0.00",
                r["sold_by"],
                r["customer_name"],
                r["customer_phone"]
            ))
        insert_rows_striped(self.sales_tv, out)

    def export_sales_history_excel(self):
        # prefer existing helper if present
        try:
            # try to use your helper
            export_treeview_to_excel(self.sales_tv, "sales_history.xlsx")
            return
        except Exception:
            pass

        # fallback: build excel via pandas
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="sales_history.xlsx", filetypes=[("Excel","*.xlsx")])
        if not path:
            return
        cols = [self.sales_tv.heading(c)["text"] for c in self.sales_tv["columns"]]
        rows = [self.sales_tv.item(r)["values"] for r in self.sales_tv.get_children()]
        df = pd.DataFrame(rows, columns=cols)
        try:
            df.to_excel(path, index=False)
            messagebox.showinfo("Export", f"Excel saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def export_sales_history_pdf(self):
        # prefer existing helper if present
        try:
            export_treeview_to_pdf(self.sales_tv, "sales_history.pdf", "Sales History")
            return
        except Exception:
            pass

        path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="sales_history.pdf", filetypes=[("PDF","*.pdf")])
        if not path:
            return

        doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
        styles = getSampleStyleSheet()
        story = []

        # add logo if present
        logo = "logo.png"
        if os.path.exists(logo):
            try:
                story.append(RLImage(logo, width=60, height=60))
                story.append(Spacer(1, 8))
            except Exception:
                pass

        story.append(Paragraph("Sales History", styles["Title"]))
        story.append(Spacer(1, 8))

        # build table data
        cols = [self.sales_tv.heading(c)["text"] for c in self.sales_tv["columns"]]
        data = [cols]
        for rid in self.sales_tv.get_children():
            data.append(self.sales_tv.item(rid)["values"])

        tbl = Table(data, repeatRows=1, colWidths=None)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("GRID", (0,0), (-1,-1), 0.25, colors.black),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ]))
        story.append(tbl)
        story.append(Spacer(1,8))
        story.append(Paragraph(f"Exported On: {now_str()}", styles["Normal"]))
        doc.build(story)
        messagebox.showinfo("Export", f"PDF saved to:\n{path}")

    # ---------- Chart windows and helpers ----------
    def _make_chart_window(self, title: str, fig: Figure):
        win = tk.Toplevel(self); win.title(title); win.geometry("900x600")
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        bar = tk.Frame(win, bg=THEME["bg"]); bar.pack(fill="x")
        tk.Button(bar, text="Save PNG", command=lambda: self._save_fig(fig, f"{title}.png")).pack(side="left", padx=6, pady=6)
        tk.Button(bar, text="Save JPEG", command=lambda: self._save_fig(fig, f"{title}.jpg")).pack(side="left", padx=6, pady=6)
        tk.Button(bar, text="Close", command=win.destroy).pack(side="right", padx=6, pady=6)

    def _save_fig(self, fig: Figure, suggested_name: str):
        path = filedialog.asksaveasfilename(defaultextension=os.path.splitext(suggested_name)[1], initialfile=suggested_name)
        if not path:
            return
        fig.savefig(path, bbox_inches="tight")
        messagebox.showinfo("Saved", f"Chart saved to:\n{path}")

    def show_monthly_sales_trend(self):
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT strftime('%Y-%m', date) as ym, IFNULL(SUM(grand_total),0) as total
            FROM sales_master
            GROUP BY ym
            ORDER BY ym DESC
            LIMIT 12
        """)
        rows = list(reversed(cur.fetchall())); con.close()
        months = [r["ym"] for r in rows]
        totals = [r["total"] for r in rows]

        fig = Figure(figsize=(9,4))
        ax = fig.add_subplot(111)
        ax.plot(months, totals, marker="o")
        ax.set_title("Monthly Sales Trend (Last 12 months)")
        ax.set_xlabel("Month"); ax.set_ylabel("Sales")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        self._make_chart_window("Monthly Sales Trend", fig)

    def show_daily_sales_trend(self):
        con = db(); cur = con.cursor()
        start = (dt.date.today() - dt.timedelta(days=29)).isoformat()
        cur.execute("""
            SELECT date, IFNULL(SUM(grand_total),0) as total
            FROM sales_master
            WHERE date >= ?
            GROUP BY date
            ORDER BY date
        """, (start,))
        rows = cur.fetchall(); con.close()
        dates = [r["date"] for r in rows]; totals = [r["total"] for r in rows]

        fig = Figure(figsize=(10,4.5)); ax = fig.add_subplot(111)
        ax.plot(dates, totals, marker="o")
        ax.set_title("Daily Sales Trend (Last 30 days)")
        ax.set_xlabel("Date"); ax.set_ylabel("Sales")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        self._make_chart_window("Daily Sales Trend", fig)

    def show_top_products(self):
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT si.product_name AS name, IFNULL(SUM(si.effective_total),0) AS total_sales
            FROM sales_items si
            GROUP BY si.product_id
            ORDER BY total_sales DESC
            LIMIT 10
        """)
        rows = cur.fetchall(); con.close()
        names = [r["name"] for r in rows]; totals = [r["total_sales"] for r in rows]

        fig = Figure(figsize=(9,5)); ax = fig.add_subplot(111)
        ax.barh(names[::-1], totals[::-1])
        ax.set_title("Top Products by Sales")
        ax.set_xlabel("Sales")
        fig.tight_layout()
        self._make_chart_window("Top Products", fig)

    def show_supplier_comparison(self):
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT s.company AS supplier, IFNULL(SUM(si.effective_total),0) AS supplier_sales
            FROM sales_items si
            JOIN products p ON si.product_id = p.product_id
            LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id
            GROUP BY p.supplier_id
            ORDER BY supplier_sales DESC
            LIMIT 12
        """)
        rows = cur.fetchall(); con.close()
        labels = [r["supplier"] or "Unknown" for r in rows]; vals = [r["supplier_sales"] for r in rows]

        fig = Figure(figsize=(9,5)); ax = fig.add_subplot(111)
        ax.bar(labels, vals)
        ax.set_title("Supplier vs Supplier (Top)")
        ax.set_xlabel("Supplier"); ax.set_ylabel("Sales")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        self._make_chart_window("Supplier Comparison", fig)

    def show_product_sales_share(self):
        # popup with date range and pie chart
        win = tk.Toplevel(self); win.title("Product Sales Share"); win.geometry("820x640")
        top = tk.Frame(win, bg=THEME["bg"]); top.pack(fill="x", pady=6)
        tk.Label(top, text="From:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        fr = DateEntry(top, width=12, date_pattern="yyyy-mm-dd"); fr.set_date(dt.date.today() - dt.timedelta(days=365)); fr.pack(side="left")
        tk.Label(top, text="To:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        to = DateEntry(top, width=12, date_pattern="yyyy-mm-dd"); to.set_date(dt.date.today()); to.pack(side="left")

        fig = Figure(figsize=(6.8,5)); ax = fig.add_subplot(111)
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.get_tk_widget().pack(fill="both", expand=True)

        def load():
            start = fr.get_date().strftime("%Y-%m-%d"); end = to.get_date().strftime("%Y-%m-%d")
            con = db(); cur = con.cursor()
            cur.execute("""
                SELECT si.product_name, IFNULL(SUM(si.effective_total),0) AS total_sales
                FROM sales_items si
                JOIN sales_master sm ON si.sale_id = sm.sale_id
                WHERE date(sm.date) BETWEEN ? AND ?
                GROUP BY si.product_id
                ORDER BY total_sales DESC
                LIMIT 12
            """, (start, end))
            rows = cur.fetchall(); con.close()
            labels = [r["product_name"] for r in rows]; vals = [r["total_sales"] for r in rows]
            ax.clear()
            if vals:
                ax.pie(vals, labels=labels, autopct="%1.1f%%", startangle=120)
                ax.set_title(f"Product Sales Share ({start} → {end})")
            else:
                ax.text(0.5, 0.5, "No data", ha="center", va="center")
            fig.tight_layout()
            canvas.draw()

        btns = tk.Frame(win, bg=THEME["bg"]); btns.pack(fill="x")
        tk.Button(btns, text="Load", bg=THEME["primary"], fg="white", command=load).pack(side="left", padx=6, pady=6)
        tk.Button(btns, text="Save PNG", command=lambda: self._save_fig(fig, "product_sales_share.png")).pack(side="left", padx=6)
        tk.Button(btns, text="Close", command=win.destroy).pack(side="right", padx=6)
        load()

    # ---------- Profit Margin Report ----------
    def show_profit_margin_report(self):
        win = tk.Toplevel(self); win.title("Profit Margin Report"); win.geometry("1000x650")
        ctrl = tk.Frame(win, bg=THEME["bg"]); ctrl.pack(fill="x", pady=6)
        tk.Label(ctrl, text="From:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        fr = DateEntry(ctrl, width=12, date_pattern="yyyy-mm-dd"); fr.set_date(dt.date.today() - dt.timedelta(days=30)); fr.pack(side="left")
        tk.Label(ctrl, text="To:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        to = DateEntry(ctrl, width=12, date_pattern="yyyy-mm-dd"); to.set_date(dt.date.today()); to.pack(side="left")
        tk.Button(ctrl, text="Apply", bg=THEME["primary"], fg="white", command=lambda: load_report()).pack(side="left", padx=6)
        tk.Button(ctrl, text="Export Excel", command=lambda: export_excel()).pack(side="right", padx=6)
        tk.Button(ctrl, text="Export PDF", command=lambda: export_pdf()).pack(side="right", padx=6)

        cols = ("Product", "Sales (₹)", "COGS (₹)", "Profit (₹)", "Profit %")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=16)
        widths = [360,100,100,100,100]
        for c,w in zip(cols,widths):
            tv.heading(c, text=c); tv.column(c, width=w, anchor="center")
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        setup_treeview_striped(tv)

        summary_lbl = tk.Label(win, text="", bg=THEME["bg"], font=FONT_MD, justify="left")
        summary_lbl.pack(fill="x", padx=6, pady=6)

        def load_report():
            start = fr.get_date().strftime("%Y-%m-%d"); end = to.get_date().strftime("%Y-%m-%d")
            con = db(); cur = con.cursor()
            cur.execute("""
                SELECT si.product_name,
                       IFNULL(SUM(si.effective_total),0) AS sales,
                       IFNULL(SUM(IFNULL(p.cost_price,0) * si.quantity),0) AS cogs
                FROM sales_items si
                LEFT JOIN products p ON si.product_id = p.product_id
                JOIN sales_master sm ON si.sale_id = sm.sale_id
                WHERE date(sm.date) BETWEEN ? AND ?
                GROUP BY si.product_id
                ORDER BY sales DESC
            """, (start, end))
            rows = cur.fetchall(); con.close()

            data = []
            total_sales = total_profit = 0.0
            for r in rows:
                sales = r["sales"] or 0.0
                cogs = r["cogs"] or 0.0
                profit = sales - cogs
                pct = (profit / cogs * 100) if sales else 0.0
                data.append((r["product_name"], f"₹{sales:.2f}", f"₹{cogs:.2f}", f"₹{profit:.2f}", f"{pct:.2f}%"))
                total_sales += sales
                total_profit += profit

            # populate treeview
            tv.delete(*tv.get_children())
            for i, row in enumerate(data):
                tv.insert("", "end", values=row, tags=("even" if i % 2 == 0 else "odd",))

            overall_pct = (total_profit / total_sales * 100) if total_sales else 0.0
            avg_profit_daily = total_profit / max(1, (to.get_date() - fr.get_date()).days + 1)
            summary_lbl.config(text=f"Total Sales: ₹{total_sales:,.2f}    Total Profit: ₹{total_profit:,.2f}    Overall Profit %: {overall_pct:.2f}%    Avg Profit/Day: ₹{avg_profit_daily:,.2f}")

        def export_excel():
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="profit_margin.xlsx", filetypes=[("Excel","*.xlsx")])
            if not path:
                return
            cols_hdr = [tv.heading(c)["text"] for c in tv["columns"]]
            rows = [tv.item(r)["values"] for r in tv.get_children()]
            df = pd.DataFrame(rows, columns=cols_hdr)
            df.to_excel(path, index=False)
            messagebox.showinfo("Export", f"Excel saved to:\n{path}")

        def export_pdf():
            path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="profit_margin.pdf", filetypes=[("PDF","*.pdf")])
            if not path:
                return
            doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
            styles = getSampleStyleSheet()
            story = []

            # logo
            logo = "logo.png"
            if os.path.exists(logo):
                try:
                    story.append(RLImage(logo, width=60, height=60))
                    story.append(Spacer(1,8))
                except Exception:
                    pass

            story.append(Paragraph("Profit Margin Report", styles["Title"])); story.append(Spacer(1,8))
            cols_hdr = [tv.heading(c)["text"] for c in tv["columns"]]
            data = [cols_hdr] + [tv.item(r)["values"] for r in tv.get_children()]
            tbl = Table(data, repeatRows=1)
            tbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.black),("ALIGN",(0,0),(-1,-1),"CENTER")]))
            story.append(tbl)
            story.append(Spacer(1,8))
            story.append(Paragraph(f"Exported On: {now_str()}", styles["Normal"]))
            doc.build(story)
            messagebox.showinfo("Export", f"PDF saved to:\n{path}")

        load_report()

    # ---------- Return History (tries returns table else negative sales_items) ----------
    def show_return_history(self):
        win = tk.Toplevel(self); win.title("Return History"); win.geometry("1000x600")
        ctrl = tk.Frame(win, bg=THEME["bg"]); ctrl.pack(fill="x", pady=6)
        tk.Label(ctrl, text="From:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        fr = DateEntry(ctrl, width=12, date_pattern="yyyy-mm-dd"); fr.set_date(dt.date.today() - dt.timedelta(days=90)); fr.pack(side="left")
        tk.Label(ctrl, text="To:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        to = DateEntry(ctrl, width=12, date_pattern="yyyy-mm-dd"); to.set_date(dt.date.today()); to.pack(side="left")
        tk.Button(ctrl, text="Apply", bg=THEME["primary"], fg="white", command=lambda: load()).pack(side="left", padx=6)
        tk.Button(ctrl, text="Export Excel", command=lambda: export_excel()).pack(side="right", padx=6)
        tk.Button(ctrl, text="Export PDF", command=lambda: export_pdf()).pack(side="right", padx=6)

        cols = ("Return ID","Sale ID","Date","Product","Qty","Refund ₹","Reason")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=18)
        widths = [80,80,120,320,60,100,220]
        for c,w in zip(cols,widths):
            tv.heading(c, text=c); tv.column(c, width=w, anchor="center")
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        setup_treeview_striped(tv)

        def load():
            start = fr.get_date().strftime("%Y-%m-%d"); end = to.get_date().strftime("%Y-%m-%d")
            con = db(); cur = con.cursor()
            rows_out = []
            try:
                # check existence of returns table
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='returns'")
                has_returns = cur.fetchone() is not None
                if has_returns:
                    # expected returns schema: return_id, sale_id, date, product_id, quantity, refund_amount, reason
                    cur.execute("""
                        SELECT r.return_id, r.sale_id, r.date, p.name as product_name, r.quantity, r.refund_amount, r.reason
                        FROM returns r
                        LEFT JOIN products p ON r.product_id = p.product_id
                        WHERE date(r.date) BETWEEN ? AND ?
                        ORDER BY r.return_id DESC
                    """, (start, end))
                    for r in cur.fetchall():
                        rows_out.append((r["return_id"], r["sale_id"], r["date"], r["product_name"], r["quantity"], f"₹{r['refund_amount']:.2f}", r["reason"]))
                else:
                    # fallback: negative quantity in sales_items indicates a return
                    cur.execute("""
                        SELECT sm.sale_id, sm.date, si.product_name, si.quantity, ABS(si.effective_total) AS refund_amount
                        FROM sales_items si
                        JOIN sales_master sm ON si.sale_id = sm.sale_id
                        WHERE si.quantity < 0 AND date(sm.date) BETWEEN ? AND ?
                        ORDER BY sm.date DESC
                    """, (start, end))
                    idx = 1
                    for r in cur.fetchall():
                        # craft a Return ID placeholder
                        rows_out.append((f"R-{r['sale_id']}-{idx}", r["sale_id"], r["date"], r["product_name"], r["quantity"], f"₹{r['refund_amount']:.2f}", "Return"))
                        idx += 1
            finally:
                con.close()
            # populate
            tv.delete(*tv.get_children())
            for i, row in enumerate(rows_out):
                tv.insert("", "end", values=row, tags=("even" if i%2==0 else "odd",))

        def export_excel():
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="returns.xlsx", filetypes=[("Excel","*.xlsx")])
            if not path:
                return
            cols_hdr = [tv.heading(c)["text"] for c in tv["columns"]]
            rows = [tv.item(r)["values"] for r in tv.get_children()]
            df = pd.DataFrame(rows, columns=cols_hdr)
            df.to_excel(path, index=False)
            messagebox.showinfo("Export", f"Excel saved to:\n{path}")

        def export_pdf():
            path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="returns.pdf", filetypes=[("PDF","*.pdf")])
            if not path:
                return
            doc = SimpleDocTemplate(path, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            logo = "logo.png"
            if os.path.exists(logo):
                try:
                    story.append(RLImage(logo, width=60, height=60))
                    story.append(Spacer(1,8))
                except Exception:
                    pass

            story.append(Paragraph("Return History", styles["Title"])); story.append(Spacer(1,8))
            cols_hdr = [tv.heading(c)["text"] for c in tv["columns"]]
            data = [cols_hdr] + [tv.item(r)["values"] for r in tv.get_children()]
            tbl = Table(data, repeatRows=1)
            tbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.black),("ALIGN",(0,0),(-1,-1),"CENTER")]))
            story.append(tbl)
            story.append(Spacer(1,8))
            story.append(Paragraph(f"Exported On: {now_str()}", styles["Normal"]))
            doc.build(story)
            messagebox.showinfo("Export", f"PDF saved to:\n{path}")

        load()

    # ---------- Profit Analysis + Forecast ----------
    def show_profit_analysis(self):
        win = tk.Toplevel(self); win.title("Profit Analysis & Forecast"); win.geometry("1000x700")
        ctrl = tk.Frame(win, bg=THEME["bg"]); ctrl.pack(fill="x", pady=6)
        tk.Label(ctrl, text="From:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        fr = DateEntry(ctrl, width=12, date_pattern="yyyy-mm-dd"); fr.set_date(dt.date.today() - dt.timedelta(days=90)); fr.pack(side="left")
        tk.Label(ctrl, text="To:", bg=THEME["bg"], font=FONT_MD).pack(side="left", padx=4)
        to = DateEntry(ctrl, width=12, date_pattern="yyyy-mm-dd"); to.set_date(dt.date.today()); to.pack(side="left")
        tk.Button(ctrl, text="Analyze", bg=THEME["primary"], fg="white", command=lambda: analyze()).pack(side="left", padx=6)
        tk.Button(ctrl, text="Export PDF", command=lambda: export_pdf()).pack(side="right", padx=6)

        summary_txt = tk.Text(win, height=6, wrap="word", font=("Segoe UI", 10))
        summary_txt.pack(fill="x", padx=6, pady=6)

        fig = Figure(figsize=(9,4)); ax = fig.add_subplot(111)
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)

        def analyze():
            start = fr.get_date().strftime("%Y-%m-%d"); end = to.get_date().strftime("%Y-%m-%d")
            con = db(); cur = con.cursor()
            cur.execute("""
                SELECT date(sm.date) as day,
                       IFNULL(SUM(si.effective_total),0) AS sales,
                       IFNULL(SUM(IFNULL(p.cost_price,0) * si.quantity),0) AS cogs
                FROM sales_master sm
                JOIN sales_items si ON si.sale_id = sm.sale_id
                LEFT JOIN products p ON si.product_id = p.product_id
                WHERE date(sm.date) BETWEEN ? AND ?
                GROUP BY day
                ORDER BY day
            """, (start, end))
            rows = cur.fetchall(); con.close()
            if not rows:
                messagebox.showinfo("No data", "No sales in selected range.")
                return
            days = [r["day"] for r in rows]
            sales = [r["sales"] for r in rows]
            cogs = [r["cogs"] for r in rows]
            profit = [s - c for s, c in zip(sales, cogs)]

            total_sales = sum(sales); total_profit = sum(profit)
            overall_profit_pct = (total_profit / total_sales * 100) if total_sales else 0.0
            avg_daily_profit = total_profit / max(1, len(profit))
            highest_val = max(profit); lowest_val = min(profit)
            highest_day = days[profit.index(highest_val)]; lowest_day = days[profit.index(lowest_val)]

            # simple moving average forecast (7-day) projected next 30 days
            window = 7
            if len(profit) >= window:
                last_ma = sum(profit[-window:]) / window
            else:
                last_ma = avg_daily_profit
            forecast_days = 30
            forecast_vals = [last_ma for _ in range(forecast_days)]
            forecast_dates = [(dt.date.fromisoformat(days[-1]) + dt.timedelta(days=i+1)).isoformat() for i in range(forecast_days)]

            # plot
            ax.clear()
            ax.plot(days, profit, label="Daily Profit", marker="o")
            ax.plot(forecast_dates, forecast_vals, label="Forecast (MA-7)", linestyle="--")
            ax.set_title("Profit and Forecast")
            ax.set_xlabel("Date"); ax.set_ylabel("Profit")
            ax.tick_params(axis="x", rotation=45)
            ax.legend()
            fig.tight_layout()
            canvas.draw()

            text = (
                f"Profit Analysis ({start} → {end})\n"
                f"• Total Sales: ₹{total_sales:,.2f}\n"
                f"• Total Profit: ₹{total_profit:,.2f}\n"
                f"• Overall Profit %: {overall_profit_pct:.2f}%\n"
                f"• Average Daily Profit: ₹{avg_daily_profit:,.2f}\n"
                f"• Highest Profit: ₹{highest_val:,.2f} on {highest_day}\n"
                f"• Lowest Profit: ₹{lowest_val:,.2f} on {lowest_day}\n"
                f"• Forecast next {forecast_days} days: approx ₹{last_ma:,.2f}/day (simple MA-{window})\n"
            )
            summary_txt.delete("1.0", "end"); summary_txt.insert("1.0", text)

        def export_pdf():
            path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="profit_analysis.pdf", filetypes=[("PDF","*.pdf")])
            if not path:
                return
            doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
            styles = getSampleStyleSheet()
            story = []
            logo = "logo.png"
            if os.path.exists(logo):
                try:
                    story.append(RLImage(logo, width=60, height=60)); story.append(Spacer(1,8))
                except Exception:
                    pass
            story.append(Paragraph("Profit Analysis & Forecast", styles["Title"])); story.append(Spacer(1,8))
            story.append(Paragraph(summary_txt.get("1.0", "end"), styles["Normal"]))
            # snapshot of figure
            tmpf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            try:
                fig.savefig(tmpf.name, bbox_inches="tight")
                story.append(Spacer(1,12))
                story.append(RLImage(tmpf.name, width=450, height=250))
            finally:
                tmpf.close()
            doc.build(story)
            try: os.remove(tmpf.name)
            except: pass
            messagebox.showinfo("Export", f"PDF saved to:\n{path}")

    # ---------- Consolidated export (All reports) ----------
    def export_all_reports(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="all_reports.pdf", filetypes=[("PDF","*.pdf")])
        if not path:
            return
        tmp_imgs: List[str] = []
        try:
            con = db(); cur = con.cursor()
            # Monthly sales chart
            cur.execute("""
                SELECT strftime('%Y-%m', date) as ym, IFNULL(SUM(grand_total),0) as total
                FROM sales_master
                GROUP BY ym
                ORDER BY ym DESC
                LIMIT 12
            """)
            rows = list(reversed(cur.fetchall()))
            months = [r["ym"] for r in rows]; totals = [r["total"] for r in rows]
            fig1 = plt.figure(figsize=(8,3.5)); ax1 = fig1.add_subplot(111)
            ax1.plot(months, totals, marker="o"); ax1.set_title("Monthly Sales (Last 12 months)"); ax1.tick_params(axis="x", rotation=45)
            f1 = tempfile.NamedTemporaryFile(suffix=".png", delete=False); fig1.savefig(f1.name, bbox_inches="tight"); tmp_imgs.append(f1.name); plt.close(fig1)

            # Top 5 products by profit %
            cur.execute("""
                SELECT si.product_name,
                       IFNULL(SUM(si.effective_total),0) AS sales,
                       IFNULL(SUM(IFNULL(p.cost_price,0) * si.quantity),0) AS cogs
                FROM sales_items si
                LEFT JOIN products p ON si.product_id = p.product_id
                GROUP BY si.product_id
                HAVING sales > 0
                ORDER BY (sales - cogs)/sales DESC
                LIMIT 5
            """)
            rows = cur.fetchall()
            prods = [r["product_name"] for r in rows]; percents = []
            for r in rows:
                sales = r["sales"] or 0.0; cogs = r["cogs"] or 0.0
                pct = ((sales - cogs) / sales * 100) if sales else 0.0
                percents.append(pct)
            fig2 = plt.figure(figsize=(6,3)); ax2 = fig2.add_subplot(111)
            if prods:
                ax2.bar(prods, percents); ax2.set_title("Top 5 Products by Profit %"); ax2.set_ylabel("Profit %")
            else:
                ax2.text(0.5,0.5,"No data", ha="center")
            f2 = tempfile.NamedTemporaryFile(suffix=".png", delete=False); fig2.savefig(f2.name, bbox_inches="tight"); tmp_imgs.append(f2.name); plt.close(fig2)

            # Product sales share (top 6)
            cur.execute("""
                SELECT si.product_name, IFNULL(SUM(si.effective_total),0) AS total_sales
                FROM sales_items si
                GROUP BY si.product_id
                ORDER BY total_sales DESC
                LIMIT 6
            """)
            rows = cur.fetchall()
            labels = [r["product_name"] for r in rows]; vals = [r["total_sales"] for r in rows]
            fig3 = plt.figure(figsize=(6,4)); ax3 = fig3.add_subplot(111)
            if vals:
                ax3.pie(vals, labels=labels, autopct="%1.1f%%", startangle=120); ax3.set_title("Product Sales Share (Top 6)")
            else:
                ax3.text(0.5,0.5,"No data", ha="center")
            f3 = tempfile.NamedTemporaryFile(suffix=".png", delete=False); fig3.savefig(f3.name, bbox_inches="tight"); tmp_imgs.append(f3.name); plt.close(fig3)
            con.close()

            # Build consolidated PDF
            doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
            styles = getSampleStyleSheet()
            story = []

            logo = "logo.png"
            if os.path.exists(logo):
                try:
                    story.append(RLImage(logo, width=60, height=60)); story.append(Spacer(1,8))
                except Exception:
                    pass

            story.append(Paragraph("Consolidated Reports", styles["Title"]))
            story.append(Paragraph(f"Exported On: {now_str()}", styles["Normal"])); story.append(Spacer(1,8))

            # KPI snapshot
            con = db(); cur = con.cursor()
            cur.execute("SELECT IFNULL(SUM(grand_total),0) AS total_sales FROM sales_master"); ts = cur.fetchone()["total_sales"] or 0.0
            cur.execute("SELECT COUNT(*) AS cnt FROM customers"); tc = cur.fetchone()["cnt"] or 0
            cur.execute("""
                SELECT IFNULL(SUM(si.effective_total - (IFNULL(p.cost_price,0) * si.quantity)), 0) as profit_est
                FROM sales_items si
                LEFT JOIN products p ON si.product_id = p.product_id
            """)
            tp = cur.fetchone()["profit_est"] or 0.0
            con.close()
            kpi_table = Table([["Total Sales", f"₹{ts:,.2f}"], ["Total Customers", str(tc)], ["Profit Estimate", f"₹{tp:,.2f}"]], colWidths=[200, 200])
            kpi_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.whitesmoke), ("GRID", (0,0), (-1,-1), 0.25, colors.black)]))
            story.append(kpi_table); story.append(Spacer(1,12))

            # attach charts
            for img in tmp_imgs:
                try:
                    story.append(RLImage(img, width=450, height=220))
                    story.append(Spacer(1,8))
                except Exception:
                    pass

            # Net vs Gross explanation
            story.append(Paragraph("<b>Profit Definitions</b>", styles["Heading3"]))
            story.append(Paragraph("Gross = Sales – Cost of Goods Sold (COGS).", styles["Normal"]))
            story.append(Paragraph("Net = Gross – (Discounts + Returns).", styles["Normal"]))
            story.append(Spacer(1,8))

            doc.build(story)
            messagebox.showinfo("Export", f"Consolidated PDF saved to:\n{path}")

        finally:
            for f in tmp_imgs:
                try:
                    os.remove(f)
                except:
                    pass

    # ---------- small utilities ----------
    def open_customer_report(self):
        win = tk.Toplevel(self); win.title("Customers"); win.geometry("700x500")
        tv = ttk.Treeview(win, columns=("id","name","phone","email"), show="headings")
        for c,w in zip(("id","name","phone","email"), (80,220,120,220)):
            tv.heading(c, text=c.title()); tv.column(c, width=w, anchor="center")
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        con = db(); cur = con.cursor()
        cur.execute("SELECT customer_id, name, phone, email FROM customers ORDER BY customer_id")
        rows = cur.fetchall(); con.close()
        data = [(r["customer_id"], r["name"], r["phone"], r["email"]) for r in rows]
        insert_rows_striped(tv, data)
        bar = tk.Frame(win); bar.pack(fill="x")
        tk.Button(bar, text="Export Excel", command=lambda: export_treeview_to_excel(tv, "customers.xlsx")).pack(side="left", padx=6)
        tk.Button(bar, text="Export PDF", command=lambda: export_treeview_to_pdf(tv, "customers.pdf", "Customers")).pack(side="left", padx=6)

# ---------- Stock Logs ----------
class SectionStockLogs(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=THEME["bg"])
        self.pack(fill="both", expand=True)

        # Search bar
        sframe = tk.Frame(self, bg=THEME["bg"])
        sframe.pack(fill="x", padx=12, pady=8)
        tk.Label(sframe, text="Search (Product / User / Reason):", bg=THEME["bg"], font=FONT_MD).pack(side="left")
        self.q = tk.StringVar()
        tk.Entry(sframe, textvariable=self.q, font=FONT_MD).pack(side="left", padx=8)
        tk.Button(sframe, text="Search", font=FONT_MD, bg=THEME["primary"], fg="white", command=self.refresh).pack(side="left", padx=4)
        tk.Button(sframe, text="Reset", font=FONT_MD, command=lambda: [self.q.set(""), self.refresh()]).pack(side="left", padx=4)

        # Table
        cols = ("log_id", "product_id", "product_name", "change_type", "quantity", "reason", "changed_by", "date")
        self.tv = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, [60, 80, 160, 80, 80, 180, 120, 160]):
            self.tv.heading(c, text=c.replace("_", " ").title())
            self.tv.column(c, anchor="center", width=w)
        self.tv.pack(fill="both", expand=True, padx=12, pady=12)
        setup_treeview_striped(self.tv)

        tk.Button(self, text="Export Excel", font=FONT_MD, bg=THEME["success"], fg="white",
                  command=lambda: export_treeview_to_excel(self.tv, "stock_logs.xlsx")).pack(side="left", padx=8, pady=6)
        tk.Button(self, text="Export PDF", font=FONT_MD, bg=THEME["accent"], fg="white",
                  command=lambda: export_treeview_to_pdf(self.tv, "stock_logs.pdf", "Stock Logs")).pack(side="left", padx=8, pady=6)

        self.refresh()

    def refresh(self):
        q = f"%{self.q.get().strip()}%"
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT * FROM stock_logs
            WHERE product_name LIKE ?
               OR changed_by LIKE ?
               OR reason LIKE ?
            ORDER BY log_id DESC
        """, (q, q, q))
        rows = [(r["log_id"], r["product_id"], r["product_name"], r["change_type"],
                 r["quantity"], r["reason"], r["changed_by"], r["date"]) for r in cur.fetchall()]
        con.close()
        insert_rows_striped(self.tv, rows)

# ---------- Run ----------
if __name__ == "__main__":
    init_db()
    app = InventoryApp()
    app.mainloop()