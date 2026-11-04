"""
PEPA – Swine Farm Registration and Monitoring System
Single-file Tkinter + MySQL desktop application.
"""
import os
import csv
import json
import hashlib
import secrets
from pathlib import Path
from datetime import date, datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import mysql.connector
from mysql.connector import Error
from PIL import Image, ImageTk, ImageDraw
from dotenv import load_dotenv

# =====================================================================
# CONFIG
# =====================================================================
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", "3306")),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "pepa_db"),
}

LOGO_PATH = BASE_DIR / "assets" / "pepa_logo.png"

COLORS = {
    "sidebar":       "#28102F",
    "sidebar_var":   "#381848",
    "primary":       "#401848",
    "lavender":      "#F0E8F8",
    "bg":            "#F8F8F8",
    "white":         "#FFFFFF",
    "border":        "#E8E0EC",
    "text":          "#28102F",
    "text_muted":    "#88818F",
    "pink":          "#F4B6CC",
    "green":         "#35C985",
    "red":           "#E74C3C",
    "orange":        "#F39C12",
    "purple_accent": "#9149A8",
    "hover_light":   "#F5EEF8", # Very light purple for table row hover
}
FONT = "Arial"
_PEPPER = "pepa_swine_system_2024_secure"

# =====================================================================
# DATABASE
# =====================================================================
def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def execute_query(sql, params=None, fetch=False, commit=True):
    conn = cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall() if fetch else None
        last_id = cur.lastrowid
        if commit:
            conn.commit()
        return rows, last_id
    except Error as e:
        if conn:
            conn.rollback()
        raise RuntimeError(f"Database error: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def test_connection():
    try:
        get_connection().close()
        return True, "OK"
    except Error as e:
        return False, str(e)


def seed_data():
    """Populates database with sample data if empty."""
    rows, _ = execute_query("SELECT COUNT(*) c FROM animals", fetch=True)
    if rows[0]["c"] > 0:
        return

    # 1. Add Sample Pigs
    samples = [
        ("PIG-1001", "Piggy 1", "Female", "Breeder", "Berkshire", 61.12, "Healthy"),
        ("PIG-1002", "Piggy 2", "Female", "Breeder", "Landrace", 38.15, "Healthy"),
        ("PIG-1003", "Piggy 3", "Female", "Breeder", "Duroc", 43.47, "Healthy"),
        ("PIG-1004", "Piggy 4", "Male", "Breeder", "Berkshire", 50.40, "Healthy"),
        ("PIG-1005", "Piggy 5", "Female", "Breeder", "Large White", 75.20, "Sick"),
        ("PIG-1006", "Piggy 6", "Female", "Grower", "Landrace", 46.28, "Healthy"),
        ("PIG-1007", "Piggy 7", "Male", "Grower", "Berkshire", 116.76, "Healthy"),
        ("PIG-1008", "Piggy 8", "Male", "Grower", "Large White", 85.00, "Healthy"),
    ]
    for tag, name, sex, cat, breed, weight, health in samples:
        add_animal({
            "tag_no": tag, "name": name, "species": "Pig", "breed": breed,
            "sex": sex, "birth_date": "2025-10-01", "age_months": 3,
            "weight_kg": weight, "health_status": health, "location": "Pen A",
            "registration_date": date.today().isoformat(), "category": cat
        })

    # 2. Add Sample Health Records
    add_health({"animal_id": 5, "exam_date": date.today().isoformat(), "symptoms": "Fever and loss of appetite",
                "diagnosis": "Illness", "treatment": "Antibiotic", "veterinarian": "Dr. Jane", "health_status": "Sick"})
    
    # 3. Add Sample Events
    add_event({"animal_id": 1, "event_type": "Birth", "event_date": "2025-10-01", "description": "Healthy litter", "responsible_staff": "Admin"})
    add_event({"animal_id": 8, "event_type": "Sale", "event_date": date.today().isoformat(), "description": "Sold to local market", "responsible_staff": "Admin", "amount": 15000, "buyer": "Juan"})
    add_event({"animal_id": 4, "event_type": "Death", "event_date": date.today().isoformat(), "description": "Natural causes", "responsible_staff": "Admin"})


# =====================================================================
# AUTH
# =====================================================================
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", (password + _PEPPER).encode(), salt.encode(), 200_000)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def login(username, password):
    rows, _ = execute_query(
        "SELECT * FROM users WHERE username=%s AND is_active=1",
        (username,), fetch=True)
    if not rows:
        return None
    u = rows[0]
    if verify_password(password, u["password_hash"]):
        execute_query("UPDATE users SET last_login=NOW() WHERE user_id=%s",
                      (u["user_id"],))
        return u
    return None


def admin_exists():
    rows, _ = execute_query("SELECT COUNT(*) c FROM users WHERE role='Admin'",
                            fetch=True)
    return rows[0]["c"] > 0


def create_admin(username, password, full_name):
    if admin_exists():
        raise ValueError("An administrator already exists.")
    execute_query(
        "INSERT INTO users (username,password_hash,full_name,role,is_active) "
        "VALUES (%s,%s,%s,'Admin',1)",
        (username, hash_password(password), full_name))


# =====================================================================
# DATA OPERATIONS
# =====================================================================
def list_animals(search="", species="", breed="", sex="", health=""):
    sql = "SELECT * FROM animals WHERE 1=1"
    p = []
    if search:
        sql += " AND (tag_no LIKE %s OR name LIKE %s)"
        like = f"%{search}%"; p += [like, like]
    if species and species != "All Species": 
        sql += " AND species=%s"; p.append(species)
    if breed and breed != "Breed":   
        sql += " AND breed LIKE %s"; p.append(f"%{breed}%")
    if sex and sex != "All Sexes":     
        sql += " AND sex=%s"; p.append(sex)
    if health and health != "All Health":  
        sql += " AND health_status=%s"; p.append(health)
    sql += " ORDER BY animal_id DESC"
    return execute_query(sql, tuple(p), fetch=True)[0]


def get_animal(aid):
    rows, _ = execute_query("SELECT * FROM animals WHERE animal_id=%s",
                            (aid,), fetch=True)
    return rows[0] if rows else None


def add_animal(d):
    _, new_id = execute_query("""INSERT INTO animals
        (tag_no,name,species,breed,sex,birth_date,age_months,weight_kg,
         health_status,location,registration_date,notes,category)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d["tag_no"], d.get("name") or None, d["species"],
         d.get("breed") or None, d["sex"], d.get("birth_date") or None,
         d.get("age_months") or None, d.get("weight_kg") or None,
         d["health_status"], d.get("location") or None,
         d["registration_date"], d.get("notes") or None,
         d.get("category") or "Grower"))
    return new_id


def update_animal(aid, d):
    execute_query("""UPDATE animals SET tag_no=%s,name=%s,species=%s,breed=%s,
        sex=%s,birth_date=%s,age_months=%s,weight_kg=%s,health_status=%s,
        location=%s,registration_date=%s,notes=%s,category=%s
        WHERE animal_id=%s""",
        (d["tag_no"], d.get("name") or None, d["species"],
         d.get("breed") or None, d["sex"], d.get("birth_date") or None,
         d.get("age_months") or None, d.get("weight_kg") or None,
         d["health_status"], d.get("location") or None,
         d["registration_date"], d.get("notes") or None,
         d.get("category") or "Grower", aid))


def delete_animal(aid):
    execute_query("DELETE FROM animals WHERE animal_id=%s", (aid,))


def distinct_values(field):
    allowed = {"species", "breed", "sex", "health_status", "location"}
    if field not in allowed:
        return []
    return [r["v"] for r in execute_query(
        f"SELECT DISTINCT {field} AS v FROM animals "
        f"WHERE {field} IS NOT NULL ORDER BY v", fetch=True)[0]]


def animal_choices():
    return execute_query(
        "SELECT animal_id, tag_no, name FROM animals "
        "WHERE status='Active' ORDER BY tag_no", fetch=True)[0]


def list_health(search=""):
    sql = """SELECT h.*, a.tag_no, a.name AS animal_name
             FROM health_records h JOIN animals a ON a.animal_id=h.animal_id
             WHERE 1=1"""
    p = []
    if search:
        sql += " AND (a.tag_no LIKE %s OR a.name LIKE %s OR h.diagnosis LIKE %s)"
        like = f"%{search}%"; p += [like, like, like]
    sql += " ORDER BY h.exam_date DESC, h.record_id DESC"
    return execute_query(sql, tuple(p), fetch=True)[0]


def add_health(d):
    execute_query("""INSERT INTO health_records
        (animal_id,exam_date,symptoms,diagnosis,treatment,veterinarian,
         follow_up_date,health_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d["animal_id"], d["exam_date"], d.get("symptoms"), d.get("diagnosis"),
         d.get("treatment"), d.get("veterinarian"), d.get("follow_up_date"),
         d["health_status"]))
    execute_query("UPDATE animals SET health_status=%s WHERE animal_id=%s",
                  (d["health_status"], d["animal_id"]))


def delete_health(rid):
    execute_query("DELETE FROM health_records WHERE record_id=%s", (rid,))


STATUS_MAP = {"Death": "Deceased", "Sale": "Sold",
              "Missing": "Missing", "Transfer": "Transferred"}


def list_events(event_type="", search=""):
    sql = """SELECT e.*, a.tag_no, a.name AS animal_name
             FROM animal_events e JOIN animals a ON a.animal_id=e.animal_id
             WHERE 1=1"""
    p = []
    if event_type: sql += " AND e.event_type=%s"; p.append(event_type)
    if search:
        sql += " AND (a.tag_no LIKE %s OR a.name LIKE %s)"
        like = f"%{search}%"; p += [like, like]
    sql += " ORDER BY e.event_date DESC, e.event_id DESC"
    return execute_query(sql, tuple(p), fetch=True)[0]


def add_event(d):
    execute_query("""INSERT INTO animal_events
        (animal_id,event_type,event_date,description,responsible_staff,amount,buyer)
        VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (d["animal_id"], d["event_type"], d["event_date"], d.get("description"),
         d.get("responsible_staff"), d.get("amount"), d.get("buyer")))
    new_status = STATUS_MAP.get(d["event_type"])
    if new_status:
        execute_query("UPDATE animals SET status=%s WHERE animal_id=%s",
                      (new_status, d["animal_id"]))


def delete_event(eid):
    execute_query("DELETE FROM animal_events WHERE event_id=%s", (eid,))


def _feed_columns():
    rows, _ = execute_query("SHOW COLUMNS FROM feed_inventory", fetch=True)
    return {r["Field"] for r in rows}


def _feed_meta(notes):
    """Read optional feed fields stored in notes on older database schemas."""
    if not notes:
        return {}, ""
    marker = "__PEPA_META__="
    for line in str(notes).splitlines():
        if line.startswith(marker):
            try:
                return json.loads(line[len(marker):]), "\n".join(
                    x for x in str(notes).splitlines() if not x.startswith(marker))
            except (ValueError, TypeError):
                break
    return {}, str(notes)


def _normalize_feed(row):
    meta, plain_notes = _feed_meta(row.get("notes"))
    return {
        **row,
        "feed_type": row.get("feed_type") or row.get("feed_name") or "",
        "brand": row.get("brand") or meta.get("brand", ""),
        "min_stock": row.get("min_stock", meta.get("min_stock", 10)),
        "purchase_date": row.get("purchase_date") or row.get("date_added"),
        "cost": row.get("cost", meta.get("cost", "")),
        "notes": plain_notes,
    }


def list_feed(search=""):
    sql = "SELECT * FROM feed_inventory WHERE 1=1"
    p = []
    if search:
        sql += " AND (feed_name LIKE %s OR feed_type LIKE %s OR supplier LIKE %s)"
        like = f"%{search}%"; p += [like, like, like]
    sql += " ORDER BY feed_id DESC"
    rows = execute_query(sql, tuple(p), fetch=True)[0]
    return [_normalize_feed(r) for r in rows]


def _feed_payload(d):
    cols = _feed_columns()
    meta = {"brand": d.get("brand") or "", "min_stock": d.get("min_stock", 10),
            "cost": d.get("cost") or ""}
    notes = d.get("notes") or ""
    if not all(k in cols for k in ("brand", "min_stock", "cost")):
        notes = (notes + "\n" if notes else "") + "__PEPA_META__=" + json.dumps(meta)
    values = {
        "feed_name": d.get("feed_type") or "Feed",
        "feed_type": d.get("feed_type") or None,
        "brand": d.get("brand") or None,
        "quantity": d["quantity"], "unit": d["unit"],
        "min_stock": d.get("min_stock", 10),
        "date_added": d["purchase_date"],
        "purchase_date": d["purchase_date"],
        "supplier": d.get("supplier") or None,
        "cost": d.get("cost") or None,
        "notes": notes or None,
    }
    return {k: v for k, v in values.items() if k in cols}


def add_feed(d):
    values = _feed_payload(d)
    cols = list(values)
    sql = "INSERT INTO feed_inventory (" + ",".join(cols) + ") VALUES (" + ",".join(["%s"] * len(cols)) + ")"
    execute_query(sql, tuple(values[c] for c in cols))


def update_feed(fid, d):
    values = _feed_payload(d)
    cols = list(values)
    sql = "UPDATE feed_inventory SET " + ",".join(f"{c}=%s" for c in cols) + " WHERE feed_id=%s"
    execute_query(sql, tuple(values[c] for c in cols) + (fid,))


def delete_feed(fid):
    execute_query("DELETE FROM feed_inventory WHERE feed_id=%s", (fid,))


def list_expenses(search=""):
    sql = "SELECT * FROM expenses WHERE 1=1"
    p = []
    if search:
        sql += " AND (category LIKE %s OR description LIKE %s OR recorded_by LIKE %s)"
        like = f"%{search}%"; p += [like, like, like]
    sql += " ORDER BY expense_date DESC, expense_id DESC"
    return execute_query(sql, tuple(p), fetch=True)[0]


def add_expense(d):
    execute_query("""INSERT INTO expenses
        (category,description,amount,expense_date,recorded_by,notes)
        VALUES (%s,%s,%s,%s,%s,%s)""",
        (d["category"], d.get("description"), d["amount"],
         d["expense_date"], d.get("recorded_by"), d.get("notes")))


def update_expense(eid, d):
    execute_query("""UPDATE expenses SET category=%s,description=%s,amount=%s,
        expense_date=%s,recorded_by=%s,notes=%s WHERE expense_id=%s""",
        (d["category"], d.get("description"), d["amount"],
         d["expense_date"], d.get("recorded_by"), d.get("notes"), eid))


def delete_expense(eid):
    execute_query("DELETE FROM expenses WHERE expense_id=%s", (eid,))


def dashboard_stats():
    q = {
        "active":    "SELECT COUNT(*) c FROM animals WHERE status='Active'",
        "piglets":   "SELECT COUNT(*) c FROM animals WHERE category='Piglet' AND status='Active'",
        "breeders":  "SELECT COUNT(*) c FROM animals WHERE category='Breeder' AND status='Active'",
        "growers":   "SELECT COUNT(*) c FROM animals WHERE category='Grower' AND status='Active'",
        "attention": "SELECT COUNT(*) c FROM animals WHERE health_status IN ('Sick','Under Treatment')",
        "feed":      "SELECT COALESCE(SUM(quantity),0) c FROM feed_inventory",
        "total":     "SELECT COUNT(*) c FROM animals",
        "births":    "SELECT COUNT(*) c FROM animal_events WHERE event_type='Birth'",
        "deaths":    "SELECT COUNT(*) c FROM animal_events WHERE event_type='Death'",
        "sales":     "SELECT COUNT(*) c FROM animal_events WHERE event_type='Sale'",
    }
    return {k: execute_query(v, fetch=True)[0][0]["c"] for k, v in q.items()}


def recent_animals(limit=8):
    return execute_query("SELECT * FROM animals ORDER BY animal_id DESC LIMIT %s",
                         (limit,), fetch=True)[0]


def list_users():
    return execute_query("SELECT * FROM users ORDER BY user_id", fetch=True)[0]


def add_user(username, password, full_name, role):
    execute_query("INSERT INTO users (username,password_hash,full_name,role,is_active) "
                  "VALUES (%s,%s,%s,%s,1)",
                  (username, hash_password(password), full_name, role))


def toggle_user(user_id, active):
    execute_query("UPDATE users SET is_active=%s WHERE user_id=%s",
                  (1 if active else 0, user_id))


def delete_user(user_id):
    execute_query("DELETE FROM users WHERE user_id=%s", (user_id,))


# =====================================================================
# WIDGET HELPERS
# =====================================================================
def make_button(parent, text, command, bg=None, fg="white", **kw):
    return tk.Button(
        parent, text=text, command=command, bg=bg or COLORS["primary"],
        fg=fg, font=(FONT, 10, "bold"), bd=0, relief="flat",
        activebackground=COLORS["purple_accent"], activeforeground="white",
        cursor="hand2", padx=12, pady=6, **kw)


def stat_card(parent, title, value, subtitle, color):
    card = tk.Frame(parent, bg=COLORS["white"],
                    highlightbackground=COLORS["border"], highlightthickness=1)
    tk.Frame(card, bg=color, height=5).pack(fill="x")
    inner = tk.Frame(card, bg=COLORS["white"], padx=16, pady=14)
    inner.pack(fill="both", expand=True)
    tk.Label(inner, text=title, font=(FONT, 10, "bold"),
             fg=COLORS["text_muted"], bg=COLORS["white"]).pack(anchor="w")
    tk.Label(inner, text=str(value), font=(FONT, 32, "bold"),
             fg=COLORS["text"], bg=COLORS["white"]).pack(anchor="w", pady=(4, 0))
    tk.Label(inner, text=subtitle, font=(FONT, 10),
             fg=COLORS["text_muted"], bg=COLORS["white"]).pack(anchor="w")
    return card


def styled_tree(parent, columns, widths=None, height=18):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Pepa.Treeview",
                    background=COLORS["white"], fieldbackground=COLORS["white"],
                    foreground=COLORS["text"], rowheight=40,
                    font=(FONT, 10), borderwidth=0)
    style.configure("Pepa.Treeview.Heading",
                    background=COLORS["lavender"], foreground=COLORS["text"],
                    font=(FONT, 9, "bold"), relief="flat")
    style.map("Pepa.Treeview",
              background=[("selected", COLORS["hover_light"])],
              foreground=[("selected", COLORS["text"])])
    tree = ttk.Treeview(parent, columns=columns, show="headings",
                        style="Pepa.Treeview", height=height)
    for i, col in enumerate(columns):
        tree.heading(col, text=col.upper(), anchor="center")
        tree.column(col, width=(widths[i] if widths else 130), anchor="center")
        
    tree.tag_configure("hover", background=COLORS["hover_light"])
    return tree


def page_header(parent, title, subtitle):
    f = tk.Frame(parent, bg=COLORS["bg"])
    f.pack(fill="x", padx=24, pady=(18, 6))
    tk.Label(f, text=title, font=(FONT, 24, "bold"),
             bg=COLORS["bg"], fg=COLORS["text"]).pack(anchor="w")
    tk.Label(f, text=subtitle, font=(FONT, 11),
             bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(anchor="w")


def form_row(parent, row, label, width=28, show=None):
    tk.Label(parent, text=label, font=(FONT, 11, "bold"),
             bg=COLORS["white"], fg=COLORS["text"]).grid(
        row=row, column=0, sticky="w", padx=(0, 8), pady=6)
    e = tk.Entry(parent, font=(FONT, 11), width=width, relief="solid",
                 bd=1, highlightthickness=0, show=show)
    e.grid(row=row, column=1, sticky="w", pady=6)
    return e


def form_combo(parent, row, label, values=None, width=26):
    tk.Label(parent, text=label, font=(FONT, 11, "bold"),
             bg=COLORS["white"], fg=COLORS["text"]).grid(
        row=row, column=0, sticky="w", padx=(0, 8), pady=6)
    c = ttk.Combobox(parent, values=values or [], state="readonly",
                     font=(FONT, 11), width=width)
    c.grid(row=row, column=1, sticky="w", pady=6)
    return c


# =====================================================================
# LOGIN
# =====================================================================
class LoginWindow:
    def __init__(self, root, on_success):
        self.root = root
        self.on_success = on_success
        root.title("PEPA – Login")
        root.state("zoomed")
        root.configure(bg=COLORS["bg"])
        root.resizable(True, True)
        self.build()

    def build(self):
        for w in self.root.winfo_children():
            w.destroy()

        center_frame = tk.Frame(self.root, bg=COLORS["bg"])
        center_frame.place(relx=0.5, rely=0.5, anchor="center")

        body = tk.Frame(center_frame, bg=COLORS["white"], padx=50, pady=40,
                        highlightbackground=COLORS["border"], highlightthickness=1)
        body.pack()

        tk.Label(body, text="pepa", font=(FONT, 36, "bold"), 
                 bg=COLORS["white"], fg=COLORS["text"]).pack(pady=(10, 0))
        tk.Label(body, text="SWINE FARM SYSTEM", font=(FONT, 9, "bold"),
                 bg=COLORS["white"], fg=COLORS["text"]).pack(pady=(0, 30))

        tk.Label(body, text="Username", font=(FONT, 11, "bold"),
                 bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w")
        self.user = tk.Entry(body, font=(FONT, 12), relief="solid", bd=1, bg=COLORS["bg"], width=35)
        self.user.pack(fill="x", pady=(4, 14), ipady=6)

        tk.Label(body, text="Password", font=(FONT, 11, "bold"),
                 bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w")
        self.pwd = tk.Entry(body, font=(FONT, 12), relief="solid", bd=1, show="•", bg=COLORS["bg"], width=35)
        self.pwd.pack(fill="x", pady=(4, 24), ipady=6)
        self.pwd.bind("<Return>", lambda e: self.do_login())

        tk.Button(body, text="➔ Log In", command=self.do_login,
                  bg=COLORS["primary"], fg="white", font=(FONT, 12, "bold"),
                  bd=0, pady=12, cursor="hand2",
                  activebackground=COLORS["purple_accent"],
                  activeforeground="white").pack(fill="x")

        tk.Label(body, text="Default: admin / admin123", font=(FONT, 9),
                 bg=COLORS["white"], fg=COLORS["text_muted"]).pack(pady=(20, 0))

        if not admin_exists():
            tk.Button(body, text="Create First Admin Account", command=self.open_setup,
                      bg=COLORS["lavender"], fg=COLORS["primary"],
                      font=(FONT, 10, "bold"), bd=0, pady=8,
                      cursor="hand2").pack(fill="x", pady=(10, 0))

    def do_login(self):
        u, p = self.user.get().strip(), self.pwd.get()
        if not u or not p:
            messagebox.showwarning("Missing", "Enter username and password.")
            return
        user = login(u, p)
        if not user:
            messagebox.showerror("Login failed", "Invalid credentials or inactive account.")
            return
        seed_data()
        self.on_success(user)

    def open_setup(self):
        SetupAdminDialog(self.root, self.build)


class SetupAdminDialog:
    def __init__(self, parent, on_done):
        self.on_done = on_done
        self.win = tk.Toplevel(parent)
        self.win.title("Create Administrator")
        self.win.geometry("420x360")
        self.win.configure(bg=COLORS["white"])
        self.win.transient(parent); self.win.grab_set()

        tk.Label(self.win, text="Create Administrator Account",
                 font=(FONT, 14, "bold"), bg=COLORS["white"]).pack(pady=(20, 14))
        frame = tk.Frame(self.win, bg=COLORS["white"], padx=24)
        frame.pack(fill="both", expand=True)

        self.fields = {}
        for label, key, show in [
            ("Full Name", "fullname", None),
            ("Username", "username", None),
            ("Password (min 6)", "password", "•"),
        ]:
            tk.Label(frame, text=label, font=(FONT, 10, "bold"),
                     bg=COLORS["white"]).pack(anchor="w")
            e = tk.Entry(frame, font=(FONT, 11), relief="solid", bd=1, show=show)
            e.pack(fill="x", pady=(2, 10), ipady=5)
            self.fields[key] = e

        tk.Button(frame, text="Create Account", command=self.create,
                  bg=COLORS["primary"], fg="white", font=(FONT, 11, "bold"),
                  bd=0, pady=9, cursor="hand2").pack(fill="x", pady=12)

    def create(self):
        fn = self.fields["fullname"].get().strip()
        un = self.fields["username"].get().strip()
        pw = self.fields["password"].get()
        if not fn or not un or len(pw) < 6:
            messagebox.showwarning("Validation",
                "All fields required. Password ≥ 6 characters.", parent=self.win)
            return
        try:
            create_admin(un, pw, fn)
            messagebox.showinfo("Success", "Admin created. You may now log in.",
                                parent=self.win)
            self.win.destroy(); self.on_done()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.win)


# =====================================================================
# SIDEBAR
# =====================================================================
NAV_ITEMS = [
    ("📊   Dashboard",       "dashboard"),
    ("🐖   Pig Records",     "animals"),
    ("🩺   Health Records",  "health"),
    ("👶   Births",          "births"),
    ("💔   Deaths / Losses", "deaths"),
    ("💰   Sales",           "sales"),
    ("🌾   Feed Inventory",  "feed"),
    ("🧾   Expenses",        "expenses"),
    ("📄   Reports",         "reports"),
    ("👥   Users",           "users"),
]

class Sidebar(tk.Frame):
    def __init__(self, parent, on_navigate, on_logout):
        super().__init__(parent, bg=COLORS["sidebar"], width=230)
        self.pack_propagate(False)
        self.on_navigate = on_navigate
        self.buttons = {}
        self._active = None
        self._build(on_logout)

    def _build(self, on_logout):
        brand = tk.Frame(self, bg=COLORS["sidebar"], pady=4)
        brand.pack(fill="x", pady=(10, 0))
        
        try:
            img = Image.open(LOGO_PATH)
            img.thumbnail((110, 80)) 
            self._logo = ImageTk.PhotoImage(img)
            tk.Label(brand, image=self._logo, bg=COLORS["sidebar"]).pack(anchor="center")
        except Exception:
            pass
        
        tk.Label(brand, text="SWINE FARM SYSTEM", font=(FONT, 9, "bold"),
                 bg=COLORS["sidebar"], fg=COLORS["pink"]).pack(anchor="center", pady=(4, 0))
                 
        tk.Frame(self, bg=COLORS["sidebar_var"], height=1).pack(fill="x", padx=16, pady=(10, 10))

        bottom_frame = tk.Frame(self, bg=COLORS["sidebar"])
        bottom_frame.pack(side="bottom", fill="x")

        tk.Frame(bottom_frame, bg=COLORS["sidebar_var"], height=1).pack(fill="x", padx=16, pady=(10, 0))
        
        tk.Button(bottom_frame, text="🚪   Log out", anchor="w",
                  font=(FONT, 12, "bold"), bg=COLORS["sidebar"],
                  fg=COLORS["pink"], bd=0, padx=32, pady=16, cursor="hand2",
                  activebackground=COLORS["sidebar_var"],
                  activeforeground="white",
                  command=on_logout).pack(fill="x")

        nav = tk.Frame(self, bg=COLORS["sidebar"], padx=10, pady=4)
        nav.pack(fill="both", expand=True)
        
        for label, key in NAV_ITEMS:
            btn = tk.Button(
                nav, text=label, anchor="w",
                font=(FONT, 11), bg=COLORS["sidebar"], fg="#EADDF0",
                bd=0, relief="flat", padx=32, pady=10, cursor="hand2",
                activebackground=COLORS["sidebar_var"],
                activeforeground="white",
                command=lambda k=key: self.on_navigate(k))
            
            btn.pack(fill="x", pady=4) 
            
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=COLORS["sidebar_var"]))
            btn.bind("<Leave>", lambda e, b=btn, k=key:
                     b.configure(bg=COLORS["primary"]
                                 if self._active == k else COLORS["sidebar"]))
            self.buttons[key] = btn

    def set_active(self, key):
        # Keep Pig Records highlighted when in the form view
        highlight_key = "animals" if key == "animal_form" else key
        for k, b in self.buttons.items():
            b.configure(bg=COLORS["primary"] if k == highlight_key else COLORS["sidebar"],
                        fg="white" if k == highlight_key else "#EADDF0")
        self._active = highlight_key


# =====================================================================
# PAGE: DASHBOARD (WITH SCROLLABLE FRAME)
# =====================================================================
class DashboardPage(tk.Frame):
    def __init__(self, parent, user, navigate):
        super().__init__(parent, bg=COLORS["bg"])
        self.user = user
        self.navigate = navigate
        self.build()

    def build(self):
        s = dashboard_stats()
        
        canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS["bg"])

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas.find_all()[0], width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        tk.Label(scrollable_frame, text="Dashboard", font=(FONT, 28, "bold"),
                 bg=COLORS["bg"], fg=COLORS["text"]).pack(anchor="w", padx=30, pady=(32, 2))
        
        tk.Label(scrollable_frame, text="Here's an overview of your swine farm today.", 
                 font=(FONT, 12), bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(anchor="w", padx=30, pady=(0, 24))

        # 1. WELCOME BANNER
        banner_path = BASE_DIR / "assets" / "banner.png"
        banner_canvas = tk.Canvas(
            scrollable_frame, bg=COLORS["bg"],
            highlightthickness=0, height=260
        )
        banner_canvas.pack(fill="x", padx=30, pady=(0, 20))

        try:
            banner_source = Image.open(banner_path).convert("RGBA")
        except Exception as exc:
            banner_source = None
            print(f"Could not load SMART-PIG banner image: {exc}")

        self._banner_photo = None
        banner_image_id = banner_canvas.create_image(0, 0, anchor="nw")

        welcome_name = self.user.get("full_name") or "System Administrator"
        welcome_title = f"Welcome back,\n{welcome_name}!"
        welcome_description = (
            "Welcome to PEPA Swine Farm System! We're glad to have you back.\n"
            "Manage your farm activities and keep track of your livestock with ease."
        )

        title_id = banner_canvas.create_text(
            44, 78, anchor="nw", text=welcome_title,
            font=(FONT, 28, "bold"), fill="white", justify="left"
        )
        description_id = banner_canvas.create_text(
            44, 178, anchor="nw", text=welcome_description,
            font=(FONT, 10), fill="#E7D9ED", justify="left", width=560
        )

        feed_button = tk.Button(
            banner_canvas, text="🌾  Daily Feed Records",
            command=lambda: self.navigate("feed"), bg="#492653",
            fg="#F9EAF7", font=(FONT, 10, "bold"), bd=0, relief="flat",
            activebackground=COLORS["purple_accent"], activeforeground="white",
            cursor="hand2", padx=12, pady=6
        )
        health_button = tk.Button(
            banner_canvas, text="▣  Livestock Health Log",
            command=lambda: self.navigate("health"), bg="#492653",
            fg="#F9EAF7", font=(FONT, 10, "bold"), bd=0, relief="flat",
            activebackground=COLORS["purple_accent"], activeforeground="white",
            cursor="hand2", padx=12, pady=6
        )
        
        feed_window = banner_canvas.create_window(44, 260, anchor="nw", window=feed_button)
        health_window = banner_canvas.create_window(230, 260, anchor="nw", window=health_button)

        def resize_banner(event):
            width = max(event.width, 1)
            height = max(220, min(280, int(width / 3.8)))
            
            if abs(banner_canvas.winfo_height() - height) > 2:
                banner_canvas.configure(height=height)

            if banner_source is not None:
                resized = banner_source.resize(
                    (width, height), Image.Resampling.LANCZOS
                )
                
                mask = Image.new('L', (width, height), 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle((0, 0, width, height), radius=16, fill=255)
                resized.putalpha(mask)

                self._banner_photo = ImageTk.PhotoImage(resized)
                banner_canvas.itemconfigure(banner_image_id, image=self._banner_photo)

            banner_canvas.coords(title_id, 44, int(height * 0.15))
            banner_canvas.coords(description_id, 44, int(height * 0.55))
            banner_canvas.coords(feed_window, 44, int(height * 0.78))
            banner_canvas.coords(health_window, 224, int(height * 0.78))

        banner_canvas.bind("<Configure>", resize_banner)

        # 2. STAT CARDS
        cards_row = tk.Frame(scrollable_frame, bg=COLORS["bg"])
        cards_row.pack(fill="x", padx=30, pady=(0, 24))
        
        cards_data = [
            ("ACTIVE PIGS",   s["active"],    "Currently on the farm", COLORS["text"]),
            ("PIGLETS",       s["piglets"],   "Under 3 months",        COLORS["pink"]),
            ("BREEDERS",      s["breeders"],  "Over 6 months",         COLORS["green"]),
            ("NEEDS ATTENTION", s["attention"], "Health follow-up",    COLORS["red"]),
            ("TOTAL FEED STOCK", int(s["feed"]), "Kg available",       COLORS["orange"]),
        ]
        
        for i, (title, val, sub, col) in enumerate(cards_data):
            c = stat_card(cards_row, title, val, sub, col)
            c.grid(row=0, column=i, sticky="nsew", padx=8)
            cards_row.grid_columnconfigure(i, weight=1)

        # 3. BOTTOM SECTION: Chart + Quick Actions
        bottom_row = tk.Frame(scrollable_frame, bg=COLORS["bg"])
        bottom_row.pack(fill="both", expand=True, padx=30, pady=(0, 24))

        # Chart
        chart_frame = tk.Frame(bottom_row, bg=COLORS["white"], 
                               highlightbackground=COLORS["border"], highlightthickness=1)
        chart_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        tk.Label(chart_frame, text="📊 Animal Population Overview", 
                 font=(FONT, 14, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=16, pady=(16, 8))
        
        self.canvas = tk.Canvas(chart_frame, bg=COLORS["white"], highlightthickness=0, height=200)
        self.canvas.pack(fill="both", expand=True, padx=16, pady=10)
        self.canvas.bind("<Configure>", lambda e: self.draw_chart(s))

        # Quick Actions
        qa_frame = tk.Frame(bottom_row, bg=COLORS["lavender"], padx=20, pady=20)
        qa_frame.pack(side="right", fill="y")
        
        tk.Label(qa_frame, text="⚡ Quick Actions", 
                 font=(FONT, 14, "bold"), bg=COLORS["lavender"], fg=COLORS["text"]).pack(anchor="w", pady=(0, 16))
                 
        actions = [
            ("+ Register a Pig", "animal_form"),
            ("🩺 Add Health Record", "health"),
            ("📋 View All Pigs", "animals"),
            ("📄 View Reports", "reports")
        ]
        
        for text, nav_key in actions:
            btn = tk.Button(qa_frame, text=text, font=(FONT, 11), bg=COLORS["white"], fg=COLORS["text"],
                            relief="flat", anchor="w", padx=16, pady=12, cursor="hand2",
                            activebackground=COLORS["border"],
                            command=lambda k=nav_key: self.navigate(k))
            btn.pack(fill="x", pady=4)
            btn.configure(highlightbackground=COLORS["border"], highlightthickness=1, bd=0)
            
        tk.Label(qa_frame, text=f"Deceased records: {s['deaths']}", font=(FONT, 10),
                 bg=COLORS["lavender"], fg=COLORS["text_muted"]).pack(anchor="w", pady=(20, 0))

        # 4. RECENT PIGS
        recent_frame = tk.Frame(scrollable_frame, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        recent_frame.pack(fill="both", expand=True, padx=30, pady=(0, 24))
        
        tk.Label(recent_frame, text="⏱️ Recently Registered Pigs", font=(FONT, 14, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=16, pady=(16, 8))
        
        cols = ("PIG ID", "BREED", "SEX", "CATEGORY", "HEALTH STATUS")
        tree = styled_tree(recent_frame, cols, widths=(120, 200, 100, 150, 150), height=8)
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        
        for a in recent_animals(8):
            tree.insert("", "end", values=(
                a["tag_no"], a["breed"] or "—", a["sex"], 
                a["category"] or "—", a["health_status"]))

    def draw_chart(self, stats):
        """Draws the HORIZONTAL bar chart exactly like the screenshot."""
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 50 or h < 50: return
            
        pad_l, pad_b, pad_t, pad_r = 70, 30, 20, 40
        chart_w = w - pad_l - pad_r
        chart_h = h - pad_b - pad_t

        # Piglets, Growers, Breeders
        data = [
            ("Piglets", stats["piglets"], COLORS["pink"]),
            ("Growers", stats["growers"], COLORS["green"]),
            ("Breeders", stats["breeders"], COLORS["text"])
        ]
        
        max_val = max([d[1] for d in data] + [1])
        
        # Draw vertical grid lines
        for i in range(5):
            val = int(max_val * (i/4))
            x = pad_l + (i/4 * chart_w)
            self.canvas.create_line(x, pad_t, x, pad_t + chart_h, fill=COLORS["border"], dash=(2, 4))
            self.canvas.create_text(x, pad_t + chart_h + 15, text=str(val), font=(FONT, 9), fill=COLORS["text_muted"])

        bar_h = min(40, (chart_h / len(data)) - 15)
        spacing = chart_h / len(data)
        
        for i, (label, val, color) in enumerate(data):
            y_center = pad_t + (i * spacing) + (spacing / 2)
            y0 = y_center - (bar_h / 2)
            y1 = y_center + (bar_h / 2)
            
            bar_w = (val / max_val) * chart_w
            x0 = pad_l
            x1 = pad_l + bar_w
            
            if val > 0:
                self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
            else:
                self.canvas.create_rectangle(x0, y0, x0+2, y1, fill=color, outline="")
            
            # Value
            self.canvas.create_text(x1 + 10, y_center, text=str(val), anchor="w", font=(FONT, 10, "bold"), fill=COLORS["text"])
            # Label
            self.canvas.create_text(pad_l - 10, y_center, text=label, anchor="e", font=(FONT, 9, "bold"), fill=COLORS["text_muted"])


# =====================================================================
# PAGE: PIG RECORDS (Updated for Card Layout + Actions + Hover)
# =====================================================================
class AnimalsPage(tk.Frame):
    def __init__(self, parent, user, navigate):
        super().__init__(parent, bg=COLORS["bg"])
        self.user = user
        self.navigate = navigate
        self.build()

    def build(self):
        page_header(self, "Pig Records", "View and manage all registered pigs.")

        # Main Card container
        self.card = tk.Frame(self, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        self.card.pack(fill="both", expand=True, padx=24, pady=(12, 20))

        # Top Toolbar (Filters)
        tb1 = tk.Frame(self.card, bg=COLORS["white"])
        tb1.pack(fill="x", padx=20, pady=(20, 10))

        self.search_var = tk.StringVar()
        se = tk.Entry(tb1, textvariable=self.search_var, font=(FONT, 10), relief="solid", bd=1, width=20)
        se.pack(side="left", padx=(0, 12), ipady=5)
        se.bind("<Return>", lambda e: self.refresh())

        def make_combo(values, default):
            c = ttk.Combobox(tb1, values=values, state="readonly", font=(FONT, 10), width=16)
            c.set(default)
            c.pack(side="left", padx=(0, 12))
            return c

        self.f_species = make_combo(["All Species"] + distinct_values("species"), "All Species")
        
        # Breed is often varied, a text entry or combo can work. Following ref, using an Entry with placeholder or combo.
        self.f_breed_var = tk.StringVar()
        be = tk.Entry(tb1, textvariable=self.f_breed_var, font=(FONT, 10), relief="solid", bd=1, width=18)
        be.pack(side="left", padx=(0, 12), ipady=5)
        be.insert(0, "Breed")
        be.bind("<FocusIn>", lambda e: be.delete(0, 'end') if be.get() == 'Breed' else None)
        be.bind("<FocusOut>", lambda e: be.insert(0, 'Breed') if not be.get() else None)
        
        self.f_sex = make_combo(["All Sexes", "Male", "Female"], "All Sexes")
        self.f_health = make_combo(["All Health", "Healthy", "Sick", "Under Treatment", "Recovered", "Deceased"], "All Health")

        make_button(tb1, "▼ Filter", self.refresh, bg=COLORS["sidebar"]).pack(side="left", padx=(0, 10))
        make_button(tb1, "C Reset", self.reset, bg=COLORS["white"], fg=COLORS["text"]).pack(side="left")
        # Add border to reset button manually
        tb1.winfo_children()[-1].configure(highlightbackground=COLORS["border"], highlightthickness=1, bd=0)

        # Toolbar 2 (+ Add Pig)
        tb2 = tk.Frame(self.card, bg=COLORS["white"])
        tb2.pack(fill="x", padx=20, pady=(0, 15))
        
        make_button(tb2, "+ Add Pig", lambda: self.navigate("animal_form"), bg=COLORS["sidebar"]).pack(side="left")

        # Table
        table_wrap = tk.Frame(self.card, bg=COLORS["white"])
        table_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        cols = ("TAG", "NAME", "SPECIES", "BREED", "SEX", "WEIGHT", "HEALTH", "LOCATION", "ACTIONS")
        widths = (90, 120, 80, 110, 70, 70, 120, 110, 110)
        self.tree = styled_tree(table_wrap, cols, widths)
        self.tree.pack(fill="both", expand=True)
        
        # Hover logic
        self.tree.bind("<Motion>", self.on_motion)
        self.tree.bind("<Leave>", lambda e: self.tree.tk.call(self.tree, "tag", "remove", "hover"))
        
        # Actions Click logic
        self.tree.bind("<ButtonRelease-1>", self.on_click)

        self.refresh()

    def on_motion(self, event):
        item = self.tree.identify_row(event.y)
        self.tree.tk.call(self.tree, "tag", "remove", "hover")
        if item:
            self.tree.item(item, tags=("hover",))

    def on_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            col = self.tree.identify_column(event.x)
            if col == "#9":  # Actions column
                item = self.tree.identify_row(event.y)
                if not item: return
                bbox = self.tree.bbox(item, col)
                if bbox:
                    x_rel = event.x - bbox[0]
                    w = bbox[2]
                    aid = int(item)
                    if x_rel < w/3:
                        self.view_selected(aid)
                    elif x_rel < 2*w/3:
                        self.edit_selected(aid)
                    else:
                        self.delete_selected(aid)

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
            
        breed_val = self.f_breed_var.get().strip()
        if breed_val == "Breed": breed_val = ""

        rows = list_animals(
            search=self.search_var.get().strip(),
            species=self.f_species.get(), breed=breed_val,
            sex=self.f_sex.get(), health=self.f_health.get())
            
        for a in rows:
            # Emulate Health Badges using Emojis 
            health = a["health_status"]
            if health == "Healthy": health_disp = "🟢 Healthy"
            elif health in ("Sick", "Under Treatment"): health_disp = "🔴 " + health
            elif health == "Deceased": health_disp = "⚫ Deceased"
            else: health_disp = health
            
            self.tree.insert("", "end", iid=a["animal_id"], values=(
                a["tag_no"], a["name"] or "—", a["species"],
                a["breed"] or "—", a["sex"],
                f"{a['weight_kg']}" if a["weight_kg"] else "—",
                health_disp, a["location"] or "—", 
                " 👁     ✎     🗑 "))

    def reset(self):
        self.search_var.set("")
        self.f_species.set("All Species")
        self.f_breed_var.set("Breed")
        self.f_sex.set("All Sexes")
        self.f_health.set("All Health")
        self.refresh()

    def view_selected(self, aid):
        # Open in read-only mode using payload
        self.navigate("animal_form", {"animal": get_animal(aid), "mode": "view"})

    def edit_selected(self, aid):
        self.navigate("animal_form", {"animal": get_animal(aid), "mode": "edit"})

    def delete_selected(self, aid):
        if messagebox.askyesno("Delete", "Are you sure you want to delete this pig record?"):
            try:
                delete_animal(aid); self.refresh()
            except Exception as e:
                messagebox.showerror("Error", str(e))


# =====================================================================
# PAGE: REGISTER NEW PIG (Updated with Scrollbar & Action Buttons)
# =====================================================================
class AnimalFormPage(tk.Frame):
    def __init__(self, parent, user, navigate, payload=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.user = user
        self.navigate = navigate
        self.payload = payload or {}
        self.mode = self.payload.get("mode", "add")
        self.animal = self.payload.get("animal", None)
        self._animal_id = self.animal.get("animal_id") if self.animal else None

        # Add scrollable canvas layout to prevent clipping (fixes hidden save button)
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.main_container = tk.Frame(self.canvas, bg=COLORS["bg"])

        self.main_container.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas_window = self.canvas.create_window((0, 0), window=self.main_container, anchor="nw")

        self.build()

    def build(self):
        titles = {
            "add": ("Register New Pig", "Add a new animal to the farm records."),
            "edit": ("Edit Pig Record", "Update details for this animal."),
            "view": ("Pig Details", "View details for this animal.")
        }
        title, subtitle = titles.get(self.mode, titles["add"])
        page_header(self.main_container, title, subtitle)

        card = tk.Frame(self.main_container, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill="both", expand=True, padx=24, pady=(12, 20))

        form = tk.Frame(card, bg=COLORS["white"])
        form.pack(fill="both", expand=True, padx=30, pady=24)
        
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        self.widgets = {}

        def v_field(row, col, label_text, widget_class=tk.Entry, **kwargs):
            tk.Label(form, text=label_text, font=(FONT, 10, "bold"), bg=COLORS["white"], fg=COLORS["text"]).grid(
                row=row*2, column=col, sticky="w", pady=(10, 4), padx=(0, 20) if col==0 else 0)
            
            if widget_class == tk.Text:
                w = tk.Text(form, font=(FONT, 10), relief="solid", bd=1, height=4)
                w.grid(row=row*2+1, column=col, columnspan=2, sticky="ew", pady=(0, 10))
            else:
                w = widget_class(form, font=(FONT, 10), **kwargs)
                if widget_class == tk.Entry:
                    w.configure(relief="solid", bd=1)
                    w.grid(row=row*2+1, column=col, sticky="ew", padx=(0, 30) if col==0 else 0, ipady=6, pady=(0, 10))
                elif widget_class == ttk.Combobox:
                    w.grid(row=row*2+1, column=col, sticky="ew", padx=(0, 30) if col==0 else 0, ipady=3, pady=(0, 10))
            
            self.widgets[label_text] = w
            return w

        # Row 0
        v_field(0, 0, "Pig Tag / ID *")
        v_field(0, 1, "Name")

        # Row 1
        v_field(1, 0, "Species *", ttk.Combobox, values=["Pig"], state="readonly")
        v_field(1, 1, "Breed")

        # Row 2
        v_field(2, 0, "Sex *", ttk.Combobox, values=["Male", "Female"], state="readonly")
        v_field(2, 1, "Date of Birth (YYYY-MM-DD)")

        # Row 3
        v_field(3, 0, "Age (months)")
        v_field(3, 1, "Weight (kg)")

        # Row 4
        v_field(4, 0, "Health Status *", ttk.Combobox, values=["Healthy", "Sick", "Under Treatment", "Recovered", "Deceased"], state="readonly")
        v_field(4, 1, "Location / Pen")

        # Row 5
        v_field(5, 0, "Registration Date *")
        v_field(5, 1, "Category", ttk.Combobox, values=["Piglet", "Breeder", "Grower", "Finisher"], state="readonly")

        # Row 6
        v_field(6, 0, "Notes", tk.Text)

        # Pre-fill data
        data = self.animal or {}
        keymap = {
            "Pig Tag / ID *": "tag_no", "Name": "name", "Species *": "species",
            "Breed": "breed", "Sex *": "sex",
            "Date of Birth (YYYY-MM-DD)": "birth_date",
            "Age (months)": "age_months", "Weight (kg)": "weight_kg",
            "Health Status *": "health_status", "Location / Pen": "location",
            "Registration Date *": "registration_date",
            "Category": "category", "Notes": "notes",
        }
        
        defaults = {
            "Species *": "Pig", "Health Status *": "Healthy",
            "Category": "Grower", "Registration Date *": date.today().isoformat(),
        }

        for label, widget in self.widgets.items():
            val = data.get(keymap[label]) or defaults.get(label, "")
            if isinstance(widget, ttk.Combobox):
                widget.set(str(val) if val else "")
            elif isinstance(widget, tk.Text):
                widget.insert("1.0", "" if val is None else str(val))
            else:
                widget.insert(0, "" if val is None else str(val))

        # View Mode Constraints
        if self.mode == "view":
            for w in self.widgets.values():
                if isinstance(w, ttk.Combobox):
                    w.configure(state="disabled")
                elif isinstance(w, tk.Entry) or isinstance(w, tk.Text):
                    w.configure(state="disabled" if isinstance(w, tk.Text) else "readonly")

        # Bottom Buttons
        btn_frame = tk.Frame(card, bg=COLORS["white"])
        btn_frame.pack(fill="x", padx=30, pady=(0, 24))

        # Add the separator line like in Health Records
        tk.Frame(btn_frame, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 14))

        # Inner frame for button layout
        buttons_inner = tk.Frame(btn_frame, bg=COLORS["white"])
        buttons_inner.pack(fill="x")
        
        if self.mode != "view":
            make_button(buttons_inner, "💾 Save Record", self.save, bg=COLORS["sidebar"]).pack(side="right", padx=(10, 0))
        
        make_button(buttons_inner, "Cancel", lambda: self.navigate("animals"), bg=COLORS["white"], fg=COLORS["text"]).pack(side="right")
        buttons_inner.winfo_children()[-1].configure(highlightbackground=COLORS["border"], highlightthickness=1, bd=0)


    def save(self):
        try:
            def g(label):
                w = self.widgets[label]
                if isinstance(w, tk.Text):
                    v = w.get("1.0", "end").strip()
                elif isinstance(w, ttk.Combobox):
                    v = w.get().strip()
                else:
                    v = w.get().strip()
                return v or None

            data = {
                "tag_no": g("Pig Tag / ID *"),
                "name": g("Name"),
                "species": g("Species *") or "Pig",
                "breed": g("Breed"),
                "sex": g("Sex *"),
                "birth_date": g("Date of Birth (YYYY-MM-DD)"),
                "age_months": int(g("Age (months)")) if g("Age (months)") else None,
                "weight_kg": float(g("Weight (kg)")) if g("Weight (kg)") else None,
                "health_status": g("Health Status *") or "Healthy",
                "location": g("Location / Pen"),
                "registration_date": g("Registration Date *") or date.today().isoformat(),
                "notes": g("Notes"),
                "category": g("Category") or "Grower",
            }

            if not data["tag_no"] or not data["sex"]:
                messagebox.showwarning("Validation", "Tag and Sex are required.")
                return

            if self.mode == "add":
                add_animal(data)
                messagebox.showinfo("Saved", "Pig registered successfully!")
            else:
                update_animal(self._animal_id, data)
                messagebox.showinfo("Saved", "Pig record updated successfully!")
            
            self.navigate("animals")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))


# =====================================================================
# PAGE: HEALTH RECORDS (Updated Layout)
# =====================================================================
class HealthPage(tk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent, bg=COLORS["bg"])
        self.user = user
        self._animals = []
        
        # Add scrollable canvas layout to prevent clipping
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.main_container = tk.Frame(self.canvas, bg=COLORS["bg"])

        self.main_container.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", 
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.main_container, anchor="nw")

        self.build()

    def build(self):
        page_header(self.main_container, "Health Records", "Monitor and record medical history.")
        
        # Needs attention alert banner
        attention_rows, _ = execute_query("SELECT tag_no FROM animals WHERE health_status IN ('Sick', 'Under Treatment')", fetch=True)
        if attention_rows:
            alert = tk.Frame(self.main_container, bg="#FFF3E0", highlightbackground="#FFE0B2", highlightthickness=1)
            alert.pack(fill="x", padx=24, pady=(0, 10))
            tk.Label(alert, text="⚠️ Needs attention:", font=(FONT, 10, "bold"), bg="#FFF3E0", fg="#E65100").pack(side="left", padx=(16, 8), pady=12)
            for r in attention_rows[:8]:
                tk.Label(alert, text=r["tag_no"], font=(FONT, 10, "bold"), bg="#FFF3E0", fg=COLORS["red"]).pack(side="left", padx=4)

        # Inline Form Card
        form_card = tk.Frame(self.main_container, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        form_card.pack(fill="x", padx=24, pady=(12, 10))
        tk.Label(form_card, text="➕ New Health Record", font=(FONT, 13, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=20, pady=(18, 12))

        form = tk.Frame(form_card, bg=COLORS["white"])
        form.pack(fill="x", padx=20, pady=(0, 12))
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        def add_field(row, col, label, widget):
            tk.Label(form, text=label, font=(FONT, 10, "bold"), bg=COLORS["white"], fg=COLORS["text"]).grid(
                row=row*2, column=col, sticky="w", padx=(0, 10), pady=(5, 4))
            widget.grid(row=row*2+1, column=col, sticky="ew", padx=(0, 16) if col==0 else 0, pady=(0, 10), ipady=5 if isinstance(widget, tk.Entry) else 2)
            return widget

        self._animals = animal_choices()
        self.animal_combo = ttk.Combobox(form, values=[f"{a['tag_no']} – {a['name'] or 'Unnamed'}" for a in self._animals], state="readonly", font=(FONT, 10))
        # Remove standard combobox background to make it solid as in the screenshot
        self.animal_combo.configure(background="#EAE8E6")
        add_field(0, 0, "Animal *", self.animal_combo)
        
        self.type_combo = ttk.Combobox(form, values=["Vaccination", "Illness", "Routine Checkup", "Injury"], state="readonly", font=(FONT, 10))
        self.type_combo.set("Vaccination")
        self.type_combo.configure(background="#EAE8E6")
        add_field(0, 1, "Record Type *", self.type_combo)

        self.date_e = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1, bg=COLORS["white"], fg=COLORS["text"])
        self.date_e.insert(0, date.today().strftime("%m/%d/%Y"))
        add_field(1, 0, "Record Date *", self.date_e)
        
        self.vet_e = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1, bg=COLORS["white"], fg=COLORS["text"])
        add_field(1, 1, "Veterinarian", self.vet_e)
        
        self.follow_e = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1, bg=COLORS["white"], fg=COLORS["text"])
        self.follow_e.insert(0, "dd/mm/yyyy")
        self.follow_e.bind("<FocusIn>", lambda e: self.follow_e.delete(0, 'end') if self.follow_e.get() == 'dd/mm/yyyy' else None)
        self.follow_e.bind("<FocusOut>", lambda e: self.follow_e.insert(0, 'dd/mm/yyyy') if not self.follow_e.get() else None)
        add_field(2, 0, "Follow-Up Date", self.follow_e)
        
        self.status_combo = ttk.Combobox(form, values=["Healthy", "Sick", "Under Treatment", "Recovered"], state="readonly", font=(FONT, 10))
        self.status_combo.set("Healthy")
        self.status_combo.configure(background="#EAE8E6")
        add_field(2, 1, "Health Status *", self.status_combo)

        # Description / Symptoms (Full width)
        tk.Label(form, text="Description", font=(FONT, 10, "bold"), bg=COLORS["white"], fg=COLORS["text"]).grid(row=6, column=0, columnspan=2, sticky="w", pady=(5, 4))
        self.desc_e = tk.Text(form, height=3, font=(FONT, 10), relief="solid", bd=1, wrap="word", bg=COLORS["white"], fg=COLORS["text"])
        self.desc_e.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        
        # Medication / Treatment (Full width)
        tk.Label(form, text="Medication", font=(FONT, 10, "bold"), bg=COLORS["white"], fg=COLORS["text"]).grid(row=8, column=0, columnspan=2, sticky="w", pady=(5, 4))
        self.med_e = tk.Text(form, height=3, font=(FONT, 10), relief="solid", bd=1, wrap="word", bg=COLORS["white"], fg=COLORS["text"])
        self.med_e.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        # Save Button area
        button_area = tk.Frame(form_card, bg=COLORS["white"])
        button_area.pack(fill="x", padx=20, pady=(0, 16))
        
        tk.Frame(button_area, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 14))
        make_button(button_area, "💾 Save Record", self.save_record, bg=COLORS["sidebar"]).pack(side="right")

        # All Health Records Table
        records_card = tk.Frame(self.main_container, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        records_card.pack(fill="both", expand=True, padx=24, pady=(10, 16))
        
        records_header = tk.Frame(records_card, bg=COLORS["white"])
        records_header.pack(fill="x", padx=20, pady=(16, 10))

        # Left aligned search area
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(records_header, textvariable=self.search_var, font=(FONT, 10), relief="solid", bd=1, width=22)
        search_entry.insert(0, "Search animal...")
        search_entry.bind("<FocusIn>", lambda e: search_entry.delete(0, 'end') if search_entry.get() == 'Search animal...' else None)
        search_entry.bind("<FocusOut>", lambda e: search_entry.insert(0, 'Search animal...') if not search_entry.get() else None)
        search_entry.pack(side="left", padx=(0, 8), ipady=5)
        search_entry.bind("<Return>", lambda event: self.refresh())
        
        make_button(records_header, "Search", self.refresh, bg=COLORS["sidebar"]).pack(side="left", padx=(0, 8))
        make_button(records_header, "C Reset", self.reset, bg=COLORS["white"], fg=COLORS["text"]).pack(side="left")
        records_header.winfo_children()[-1].configure(highlightbackground=COLORS["border"], highlightthickness=1, bd=0)

        # Table Wrapper
        table_wrap = tk.Frame(records_card, bg=COLORS["white"])
        table_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        
        columns = ("DATE", "ANIMAL", "TYPE", "DESCRIPTION", "MEDICATION", "VET", "STATUS")
        widths = (110, 100, 120, 220, 150, 120, 110)
        self.tree = styled_tree(table_wrap, columns, widths, height=8)
        self.tree.pack(fill="both", expand=True)

        actions = tk.Frame(records_card, bg=COLORS["white"])
        actions.pack(fill="x", padx=20, pady=(0, 14))
        make_button(actions, "Delete Selected", self.delete_selected, bg=COLORS["red"]).pack(side="right")

        self.refresh()

    def save_record(self):
        try:
            animal_val = self.animal_combo.get()
            if not animal_val or animal_val == "Select...":
                messagebox.showwarning("Missing Information", "Please select an animal.")
                return

            animal_index = -1
            for i, a in enumerate(self._animals):
                if animal_val.startswith(a['tag_no']):
                    animal_index = i
                    break
            
            if animal_index < 0:
                messagebox.showwarning("Missing Information", "Please select a valid animal.")
                return
                
            raw_date = self.date_e.get().strip()
            try: 
                exam_date = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
            except ValueError: 
                exam_date = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
            
            raw_follow = self.follow_e.get().strip()
            follow_up = None
            if raw_follow and raw_follow != "dd/mm/yyyy":
                try: 
                    follow_up = datetime.strptime(raw_follow, "%m/%d/%Y").date().isoformat()
                except ValueError: 
                    follow_up = datetime.strptime(raw_follow, "%Y-%m-%d").date().isoformat()

            status = self.status_combo.get().strip()
            if not status:
                messagebox.showwarning("Missing Information", "Please select a health status.")
                return

            add_health({
                "animal_id": self._animals[animal_index]["animal_id"],
                "exam_date": exam_date,
                "diagnosis": self.type_combo.get().strip() or None,
                "symptoms": self.desc_e.get("1.0", "end").strip() or None,
                "treatment": self.med_e.get("1.0", "end").strip() or None,
                "veterinarian": self.vet_e.get().strip() or None,
                "follow_up_date": follow_up,
                "health_status": status
            })
            messagebox.showinfo("Saved", "Health record added successfully.")
            self.clear_form()
            self.refresh()
        except ValueError:
            messagebox.showwarning("Invalid Date", "Please use the mm/dd/yyyy or yyyy-mm-dd format.")
        except Exception as error:
            messagebox.showerror("Error", str(error))

    def clear_form(self):
        self.animal_combo.set("Select...")
        self.date_e.delete(0, "end")
        self.date_e.insert(0, date.today().strftime("%m/%d/%Y"))
        self.follow_e.delete(0, "end")
        self.follow_e.insert(0, "dd/mm/yyyy")
        self.vet_e.delete(0, "end")
        self.desc_e.delete("1.0", "end")
        self.med_e.delete("1.0", "end")
        self.type_combo.set("Vaccination")
        self.status_combo.set("Healthy")

    def reset(self):
        self.search_var.set("Search animal...")
        self.refresh()

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        search_val = self.search_var.get().strip()
        if search_val == "Search animal...":
            search_val = ""

        for record in list_health(search_val):
            status = record["health_status"]
            if status == "Healthy": health_disp = "🟢 Healthy"
            elif status in ("Sick", "Under Treatment"): health_disp = "🔴 " + status
            else: health_disp = status
            
            self.tree.insert("", "end", iid=record["record_id"], values=(
                record["exam_date"], 
                record["tag_no"], 
                record["diagnosis"] or "—",
                record["symptoms"] or "—", 
                record["treatment"] or "—",
                record["veterinarian"] or "—", 
                health_disp
            ))

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select Record", "Please select a health record first.")
            return

        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this health record?"):
            try:
                delete_health(int(selected[0]))
                self.refresh()
            except Exception as error:
                messagebox.showerror("Error", str(error))


# =====================================================================
# PAGE: EVENTS (Births / Deaths / Sales)
# =====================================================================
class EventsPage(tk.Frame):
    EVENT_MAP = {
        "births":  {"type": "Birth", "title": "Birth Records",
                    "subtitle": "Log and track newborn pigs."},
        "deaths":  {"type": "Death", "title": "Death & Loss Records",
                    "subtitle": "Track deceased and missing pigs."},
        "sales":   {"type": "Sale",  "title": "Sales Records",
                    "subtitle": "Manage pig sales and revenue."},
    }

    def __init__(self, parent, user, key):
        super().__init__(parent, bg=COLORS["bg"])
        self.user = user
        self.key = key
        self.meta = self.EVENT_MAP[key]
        self._animals = []
        
        # Add scrollable canvas layout to prevent clipping on smaller screens
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.main_container = tk.Frame(self.canvas, bg=COLORS["bg"])

        self.main_container.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", 
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.main_container, anchor="nw")

        self.build()

    def build(self):
        if self.key == "births":
            self.build_births()
        elif self.key == "deaths":
            self.build_deaths()
        elif self.key == "sales":
            self.build_sales()
        else:
            self.build_standard_events()

    def build_births(self):
        page_header(self.main_container, self.meta["title"], self.meta["subtitle"])

        # Record New Birth form card
        form_card = tk.Frame(
            self.main_container, bg=COLORS["white"],
            highlightbackground=COLORS["border"], highlightthickness=1
        )
        form_card.pack(fill="x", padx=24, pady=(12, 10))

        tk.Label(
            form_card, text="✚  Record New Birth",
            font=(FONT, 13, "bold"), bg=COLORS["white"],
            fg=COLORS["text"]
        ).pack(anchor="w", padx=20, pady=(18, 12))

        form = tk.Frame(form_card, bg=COLORS["white"])
        form.pack(fill="x", padx=20, pady=(0, 12))
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(3, weight=1)

        self._animals = animal_choices()
        animal_values = [
            f"{a['tag_no']} – {a['name'] or 'Unnamed'}"
            for a in self._animals
        ]

        def field_label(row, col, label):
            tk.Label(
                form, text=label, font=(FONT, 10, "bold"),
                bg=COLORS["white"], fg=COLORS["text"]
            ).grid(row=row, column=col, sticky="w", padx=(0, 12),
                   pady=(5, 4))

        def entry(row, col, width=30):
            widget = tk.Entry(
                form, font=(FONT, 10), relief="solid", bd=1,
                bg=COLORS["white"], fg=COLORS["text"], width=width
            )
            widget.grid(row=row + 1, column=col, sticky="ew",
                        padx=(0, 16), pady=(0, 10))
            return widget

        # Newborn animal
        field_label(0, 0, "Newborn Animal *")
        self.birth_animal = ttk.Combobox(
            form, values=animal_values, state="readonly", font=(FONT, 10)
        )
        self.birth_animal.grid(
            row=1, column=0, columnspan=2, sticky="ew",
            padx=(0, 16), pady=(0, 10)
        )

        # Mother (optional)
        field_label(0, 2, "Mother (optional)")
        self.birth_mother = ttk.Combobox(
            form, values=animal_values, state="readonly", font=(FONT, 10)
        )
        self.birth_mother.grid(
            row=1, column=2, columnspan=2, sticky="ew",
            padx=(0, 0), pady=(0, 10)
        )
        self.birth_mother.set("— None —")

        # Birth date
        field_label(2, 0, "Birth Date *")
        self.birth_date = entry(2, 0)
        self.birth_date.insert(0, date.today().isoformat())

        # Notes
        field_label(4, 0, "Notes")
        self.birth_notes = tk.Text(
            form, height=3, font=(FONT, 10), relief="solid",
            bd=1, wrap="word"
        )
        self.birth_notes.grid(
            row=5, column=0, columnspan=4, sticky="ew",
            padx=(0, 0), pady=(0, 12)
        )

        # Save button footer
        footer = tk.Frame(form_card, bg=COLORS["white"])
        footer.pack(fill="x", padx=20, pady=(0, 16))
        tk.Frame(footer, bg=COLORS["border"], height=1).pack(
            fill="x", pady=(0, 14)
        )
        make_button(
            footer, "▣  Save Birth Record", self.save_birth,
            bg=COLORS["primary"]
        ).pack(side="right")

        # All Birth Records table card
        records_card = tk.Frame(
            self.main_container, bg=COLORS["white"],
            highlightbackground=COLORS["border"], highlightthickness=1
        )
        records_card.pack(
            fill="both", expand=True, padx=24, pady=(10, 16)
        )

        header = tk.Frame(records_card, bg=COLORS["white"])
        header.pack(fill="x", padx=20, pady=(16, 10))
        tk.Label(
            header, text="☷  All Birth Records",
            font=(FONT, 13, "bold"), bg=COLORS["white"],
            fg=COLORS["text"]
        ).pack(side="left")

        self.search_var = tk.StringVar()
        search_entry = tk.Entry(
            header, textvariable=self.search_var,
            font=(FONT, 10), relief="solid", bd=1, width=22
        )
        search_entry.pack(side="right", ipady=5)
        search_entry.bind("<Return>", lambda event: self.refresh())
        make_button(header, "Search", self.refresh).pack(
            side="right", padx=6
        )

        table_wrap = tk.Frame(records_card, bg=COLORS["white"])
        table_wrap.pack(
            fill="both", expand=True, padx=20, pady=(0, 12)
        )
        columns = ("Date", "Newborn", "Mother", "Notes")
        widths = (130, 180, 180, 420)
        self.tree = styled_tree(table_wrap, columns, widths, height=8)
        self.tree.pack(fill="both", expand=True)

        actions = tk.Frame(records_card, bg=COLORS["white"])
        actions.pack(fill="x", padx=20, pady=(0, 14))
        make_button(
            actions, "Delete Selected Record", self.delete_selected,
            bg=COLORS["red"]
        ).pack(side="right")

        self.refresh()

    def save_birth(self):
        try:
            idx = self.birth_animal.current()
            if idx < 0:
                messagebox.showwarning(
                    "Missing Information",
                    "Please select the newborn animal."
                )
                return

            birth_date = self.birth_date.get().strip()
            if not birth_date:
                messagebox.showwarning(
                    "Missing Information", "Please enter the birth date."
                )
                return

            mother_idx = self.birth_mother.current()
            mother_text = ""
            if mother_idx >= 0:
                mother = self._animals[mother_idx]
                mother_text = (
                    f"Mother: {mother['tag_no']} – "
                    f"{mother['name'] or 'Unnamed'}"
                )

            notes = self.birth_notes.get("1.0", "end").strip()
            description_parts = []
            if mother_text:
                description_parts.append(mother_text)
            if notes:
                description_parts.append(f"Notes: {notes}")
            description = "\n".join(description_parts) or None

            add_event({
                "animal_id": self._animals[idx]["animal_id"],
                "event_type": "Birth",
                "event_date": birth_date,
                "description": description,
                "responsible_staff": getattr(self.user, "username", None)
                    if not isinstance(self.user, dict)
                    else self.user.get("username"),
            })

            messagebox.showinfo(
                "Success", "Birth record saved successfully!"
            )
            self.birth_animal.set("")
            self.birth_mother.set("— None —")
            self.birth_date.delete(0, "end")
            self.birth_date.insert(0, date.today().isoformat())
            self.birth_notes.delete("1.0", "end")
            self.refresh()

        except Exception as error:
            messagebox.showerror("Error", str(error))

    def _make_inline_card(self, title):
        card = tk.Frame(
            self.main_container, bg=COLORS["white"],
            highlightbackground=COLORS["border"], highlightthickness=1
        )
        tk.Label(
            card, text=title, font=(FONT, 13, "bold"),
            bg=COLORS["white"], fg=COLORS["text"]
        ).pack(anchor="w", padx=20, pady=(18, 12))
        return card

    def _field_label(self, parent, row, col, label):
        tk.Label(
            parent, text=label, font=(FONT, 10, "bold"),
            bg=COLORS["white"], fg=COLORS["text"]
        ).grid(row=row, column=col, sticky="w",
               padx=(0, 12), pady=(5, 4))

    def _entry_field(self, parent, row, col, label, default=None):
        self._field_label(parent, row, col, label)
        entry = tk.Entry(
            parent, font=(FONT, 10), relief="solid", bd=1,
            bg=COLORS["white"], fg=COLORS["text"]
        )
        entry.grid(row=row + 1, column=col, sticky="ew",
                   padx=(0, 16), pady=(0, 10))
        if default is not None:
            entry.insert(0, str(default))
        return entry

    def _record_table_card(self, title, columns, widths):
        card = tk.Frame(
            self.main_container, bg=COLORS["white"],
            highlightbackground=COLORS["border"], highlightthickness=1
        )
        card.pack(fill="both", expand=True, padx=24, pady=(10, 16))
        header = tk.Frame(card, bg=COLORS["white"])
        header.pack(fill="x", padx=20, pady=(16, 10))
        tk.Label(
            header, text=title, font=(FONT, 13, "bold"),
            bg=COLORS["white"], fg=COLORS["text"]
        ).pack(side="left")

        self.search_var = tk.StringVar()
        search = tk.Entry(
            header, textvariable=self.search_var, font=(FONT, 10),
            relief="solid", bd=1, width=22
        )
        search.pack(side="right", ipady=5)
        search.bind("<Return>", lambda event: self.refresh())
        make_button(header, "Search", self.refresh).pack(
            side="right", padx=6
        )

        table_wrap = tk.Frame(card, bg=COLORS["white"])
        table_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.tree = styled_tree(table_wrap, columns, widths, height=8)
        self.tree.pack(fill="both", expand=True)

        actions = tk.Frame(card, bg=COLORS["white"])
        actions.pack(fill="x", padx=20, pady=(0, 14))
        make_button(
            actions, "Delete Selected Record", self.delete_selected,
            bg=COLORS["red"]
        ).pack(side="right")
        return card

    def build_deaths(self):
        page_header(
            self.main_container, "Death & Loss Records",
            "Track deceased and missing pigs."
        )

        form_card = self._make_inline_card("✚  Record Death or Loss")
        form_card.pack(fill="x", padx=24, pady=(12, 10))

        form = tk.Frame(form_card, bg=COLORS["white"])
        form.pack(fill="x", padx=20, pady=(0, 12))
        for col in (1, 3):
            form.grid_columnconfigure(col, weight=1)

        self._animals = animal_choices()
        animal_values = [
            f"{a['tag_no']} – {a['name'] or 'Unnamed'}"
            for a in self._animals
        ]

        self._field_label(form, 0, 0, "Animal *")
        self.death_animal = ttk.Combobox(
            form, values=animal_values, state="readonly", font=(FONT, 10)
        )
        self.death_animal.grid(
            row=1, column=0, columnspan=2, sticky="ew",
            padx=(0, 16), pady=(0, 10)
        )

        self._field_label(form, 0, 2, "Record Type *")
        self.death_type = ttk.Combobox(
            form, values=["Death", "Missing"], state="readonly",
            font=(FONT, 10)
        )
        self.death_type.set("Death")
        self.death_type.grid(
            row=1, column=2, columnspan=2, sticky="ew",
            padx=(0, 0), pady=(0, 10)
        )

        self.death_date = self._entry_field(
            form, 2, 0, "Event Date *", date.today().isoformat()
        )

        self._field_label(form, 4, 0, "Reason / Details")
        self.death_reason = tk.Text(
            form, height=3, font=(FONT, 10), relief="solid",
            bd=1, wrap="word"
        )
        self.death_reason.grid(
            row=5, column=0, columnspan=4, sticky="ew",
            pady=(0, 12)
        )

        footer = tk.Frame(form_card, bg=COLORS["white"])
        footer.pack(fill="x", padx=20, pady=(0, 16))
        tk.Frame(footer, bg=COLORS["border"], height=1).pack(
            fill="x", pady=(0, 14)
        )
        make_button(
            footer, "▣  Save Record", self.save_death,
            bg=COLORS["primary"]
        ).pack(side="right")

        self._record_table_card(
            "☷  All Records",
            ("Date", "Animal", "Type", "Reason"),
            (130, 220, 130, 500)
        )
        self.refresh()

    def save_death(self):
        try:
            idx = self.death_animal.current()
            if idx < 0:
                messagebox.showwarning(
                    "Missing Information", "Please select an animal."
                )
                return
            event_date = self.death_date.get().strip()
            if not event_date:
                messagebox.showwarning(
                    "Missing Information", "Please enter the event date."
                )
                return

            event_type = self.death_type.get().strip()
            if event_type not in ("Death", "Missing"):
                messagebox.showwarning(
                    "Missing Information", "Please select a record type."
                )
                return

            add_event({
                "animal_id": self._animals[idx]["animal_id"],
                "event_type": event_type,
                "event_date": event_date,
                "description": self.death_reason.get("1.0", "end").strip() or None,
                "responsible_staff": (
                    self.user.get("username") if isinstance(self.user, dict)
                    else getattr(self.user, "username", None)
                )
            })
            messagebox.showinfo(
                "Success", "Death / loss record saved successfully!"
            )
            self.death_animal.set("")
            self.death_type.set("Death")
            self.death_date.delete(0, "end")
            self.death_date.insert(0, date.today().isoformat())
            self.death_reason.delete("1.0", "end")
            self.refresh()
        except Exception as error:
            messagebox.showerror("Error", str(error))

    def build_sales(self):
        page_header(
            self.main_container, "Sales Records",
            "Manage pig sales and revenue."
        )

        self.sales_total_card = stat_card(
            self.main_container, "▣  TOTAL SALES", "₱0.00", "Gross revenue",
            COLORS["primary"]
        )
        self.sales_total_card.pack(
            anchor="w", padx=24, pady=(12, 10), ipadx=60 
        )

        form_card = self._make_inline_card("✚  Record New Sale")
        form_card.pack(fill="x", padx=24, pady=(8, 10))
        form = tk.Frame(form_card, bg=COLORS["white"])
        form.pack(fill="x", padx=20, pady=(0, 12))
        for col in (1, 3):
            form.grid_columnconfigure(col, weight=1)

        self._animals = animal_choices()
        animal_values = [
            f"{a['tag_no']} – {a['name'] or 'Unnamed'}"
            for a in self._animals
        ]

        self._field_label(form, 0, 0, "Animal *")
        self.sale_animal = ttk.Combobox(
            form, values=animal_values, state="readonly", font=(FONT, 10)
        )
        self.sale_animal.grid(
            row=1, column=0, columnspan=2, sticky="ew",
            padx=(0, 16), pady=(0, 10)
        )

        self.sale_date = self._entry_field(
            form, 0, 2, "Sale Date *", date.today().isoformat()
        )
        self.sale_quantity = self._entry_field(
            form, 2, 0, "Quantity *", "1"
        )
        self.sale_price = self._entry_field(
            form, 2, 2, "Price (₱) *"
        )
        self.sale_buyer = self._entry_field(
            form, 4, 0, "Buyer"
        )

        self._field_label(form, 6, 0, "Notes")
        self.sale_notes = tk.Text(
            form, height=3, font=(FONT, 10), relief="solid",
            bd=1, wrap="word"
        )
        self.sale_notes.grid(
            row=7, column=0, columnspan=4, sticky="ew",
            pady=(0, 12)
        )

        footer = tk.Frame(form_card, bg=COLORS["white"])
        footer.pack(fill="x", padx=20, pady=(0, 16))
        tk.Frame(footer, bg=COLORS["border"], height=1).pack(
            fill="x", pady=(0, 14)
        )
        make_button(
            footer, "▣  Save Sale", self.save_sale,
            bg=COLORS["primary"]
        ).pack(side="right")

        self._record_table_card(
            "☷  All Sales Records",
            ("Date", "Animal", "Quantity", "Price (₱)", "Buyer", "Notes"),
            (120, 190, 90, 120, 160, 300)
        )
        self.refresh()

    def save_sale(self):
        try:
            idx = self.sale_animal.current()
            if idx < 0:
                messagebox.showwarning(
                    "Missing Information", "Please select an animal."
                )
                return
            sale_date = self.sale_date.get().strip()
            if not sale_date:
                messagebox.showwarning(
                    "Missing Information", "Please enter the sale date."
                )
                return

            quantity = int(self.sale_quantity.get().strip())
            price = float(self.sale_price.get().strip())
            if quantity <= 0 or price < 0:
                raise ValueError("Quantity must be greater than zero and price cannot be negative.")

            notes = self.sale_notes.get("1.0", "end").strip()
            description_parts = [f"Quantity: {quantity}"]
            if notes:
                description_parts.append(f"Notes: {notes}")

            add_event({
                "animal_id": self._animals[idx]["animal_id"],
                "event_type": "Sale",
                "event_date": sale_date,
                "description": "\n".join(description_parts),
                "amount": price * quantity,
                "buyer": self.sale_buyer.get().strip() or None,
                "responsible_staff": (
                    self.user.get("username") if isinstance(self.user, dict)
                    else getattr(self.user, "username", None)
                )
            })
            messagebox.showinfo("Success", "Sale recorded successfully!")
            self.sale_animal.set("")
            self.sale_date.delete(0, "end")
            self.sale_date.insert(0, date.today().isoformat())
            self.sale_quantity.delete(0, "end")
            self.sale_quantity.insert(0, "1")
            self.sale_price.delete(0, "end")
            self.sale_buyer.delete(0, "end")
            self.sale_notes.delete("1.0", "end")
            self.refresh()
        except ValueError as error:
            messagebox.showwarning("Invalid Information", str(error))
        except Exception as error:
            messagebox.showerror("Error", str(error))

    def build_standard_events(self):
        page_header(self.main_container, self.meta["title"], self.meta["subtitle"])
        bar = tk.Frame(self.main_container, bg=COLORS["bg"])
        bar.pack(fill="x", padx=24, pady=6)
        self.search_var = tk.StringVar()
        tk.Entry(
            bar, textvariable=self.search_var, font=(FONT, 11),
            relief="solid", bd=1, width=30
        ).pack(side="left", ipady=5)
        make_button(bar, "Search", self.refresh).pack(side="left", padx=6)
        make_button(
            bar, f"+ Add {self.meta['title']}", self.open_form,
            bg=COLORS["green"]
        ).pack(side="right")

        wrap = tk.Frame(
            self.main_container, bg=COLORS["white"],
            highlightbackground=COLORS["border"], highlightthickness=1
        )
        wrap.pack(fill="both", expand=True, padx=24, pady=(6, 12))
        cols = ("Tag", "Animal", "Date", "Description",
                "Staff", "Amount", "Buyer")
        widths = (90, 130, 100, 220, 130, 90, 120)
        self.tree = styled_tree(wrap, cols, widths)
        self.tree.pack(fill="both", expand=True, padx=12, pady=12)

        make_button(
            self.main_container, "Delete", self.delete_selected, bg=COLORS["red"]
        ).pack(anchor="e", padx=24, pady=(0, 16))
        self.refresh()

    def refresh(self):
        if not hasattr(self, "tree"):
            return
        for row in self.tree.get_children():
            self.tree.delete(row)

        search_text = self.search_var.get().strip()
        if self.key == "deaths":
            rows = [
                r for r in list_events("", search_text)
                if r["event_type"] in ("Death", "Missing")
            ]
            for r in rows:
                self.tree.insert(
                    "", "end", iid=r["event_id"],
                    values=(
                        r["event_date"],
                        f"{r['tag_no']} – {r['animal_name'] or 'Unnamed'}",
                        r["event_type"],
                        r["description"] or "—"
                    )
                )

        elif self.key == "sales":
            rows = list_events("Sale", search_text)
            total = sum(float(r["amount"] or 0) for r in rows)
            # The total card reflects all sales, not only filtered search results.
            all_sales = list_events("Sale", "")
            grand_total = sum(float(r["amount"] or 0) for r in all_sales)
            self._update_sales_total(grand_total)

            for r in rows:
                description = r.get("description") or ""
                quantity = "1"
                notes = description
                for line in description.splitlines():
                    if line.startswith("Quantity: "):
                        quantity = line[len("Quantity: "):]
                    elif line.startswith("Notes: "):
                        notes = line[len("Notes: "):]
                self.tree.insert(
                    "", "end", iid=r["event_id"],
                    values=(
                        r["event_date"],
                        f"{r['tag_no']} – {r['animal_name'] or 'Unnamed'}",
                        quantity,
                        f"₱{(float(r['amount'] or 0) / max(int(quantity), 1)):,.2f}",
                        r["buyer"] or "—",
                        notes or "—"
                    )
                )

        elif self.key == "births":
            rows = list_events("Birth", search_text)
            for r in rows:
                description = r.get("description") or ""
                mother = "—"
                notes = description
                for line in description.splitlines():
                    if line.startswith("Mother: "):
                        mother = line[len("Mother: "):]
                    elif line.startswith("Notes: "):
                        notes = line[len("Notes: "):]
                if not description.startswith("Mother: ") and not description.startswith("Notes: "):
                    notes = description
                self.tree.insert(
                    "", "end", iid=r["event_id"],
                    values=(
                        r["event_date"],
                        f"{r['tag_no']} – {r['animal_name'] or 'Unnamed'}",
                        mother,
                        notes or "—"
                    )
                )
        else:
            rows = list_events(self.meta["type"], search_text)
            for r in rows:
                self.tree.insert("", "end", iid=r["event_id"], values=(
                    r["tag_no"], r["animal_name"] or "—", r["event_date"],
                    (r["description"] or "")[:40],
                    r["responsible_staff"] or "—",
                    f"{r['amount']}" if r["amount"] else "—",
                    r["buyer"] or "—"
                ))

    def _update_sales_total(self, amount):
        # Update the summary card's value label while preserving its styling.
        try:
            inner = self.sales_total_card.winfo_children()[1]
            labels = [w for w in inner.winfo_children()
                      if isinstance(w, tk.Label)]
            if len(labels) >= 2:
                labels[1].configure(text=f"₱{amount:,.2f}")
        except (tk.TclError, IndexError):
            pass

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(
                "Select", "Select a record first."
            )
            return
        if messagebox.askyesno(
            "Delete", "Are you sure you want to delete this record?"
        ):
            delete_event(int(sel[0]))
            self.refresh()

    def open_form(self):
        EventFormDialog(
            self, self.meta["type"], self.meta["title"], self.refresh
        )


class EventFormDialog:
    def __init__(self, parent, etype, title, on_saved):
        self.etype = etype
        self.on_saved = on_saved
        self.win = tk.Toplevel(parent)
        self.win.title(f"Add {title}")
        self.win.geometry("520x480")
        self.win.configure(bg=COLORS["white"])
        self.win.transient(parent); self.win.grab_set()

        tk.Label(self.win, text=f"Add {title}", font=(FONT, 16, "bold"),
                 bg=COLORS["white"]).pack(pady=(18, 8))
        f = tk.Frame(self.win, bg=COLORS["white"], padx=24, pady=8)
        f.pack(fill="both", expand=True)

        self._animals = animal_choices()
        self.animal_combo = form_combo(
            f, 0, "Animal",
            [f"{a['tag_no']} – {a['name'] or 'Unnamed'}" for a in self._animals])
        self.date_e = form_row(f, 1, "Event Date (YYYY-MM-DD)")
        self.date_e.insert(0, date.today().isoformat())
        self.desc_e = form_row(f, 2, "Description")
        self.staff_e = form_row(f, 3, "Responsible Staff")
        self.amount_e = form_row(f, 4, "Amount (Sales only)")
        self.buyer_e = form_row(f, 5, "Buyer (Sales only)")

        btns = tk.Frame(self.win, bg=COLORS["white"], pady=12)
        btns.pack(fill="x")
        make_button(btns, "Save", self.save,
                    bg=COLORS["green"]).pack(side="right", padx=16)
        make_button(btns, "Cancel", self.win.destroy,
                    bg=COLORS["text_muted"]).pack(side="right")

    def save(self):
        try:
            idx = self.animal_combo.current()
            if idx < 0:
                messagebox.showwarning("Validation", "Select an animal.",
                                       parent=self.win); return
            add_event({
                "animal_id": self._animals[idx]["animal_id"],
                "event_type": self.etype,
                "event_date": self.date_e.get().strip() or date.today().isoformat(),
                "description": self.desc_e.get().strip() or None,
                "responsible_staff": self.staff_e.get().strip() or None,
                "amount": float(self.amount_e.get()) if self.amount_e.get().strip() else None,
                "buyer": self.buyer_e.get().strip() or None,
            })
            messagebox.showinfo("Saved", "Event recorded.", parent=self.win)
            self.win.destroy(); self.on_saved()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.win)


# =====================================================================
# PAGE: FEED INVENTORY
# =====================================================================
class FeedPage(tk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent, bg=COLORS["bg"])
        self.user = user
        self.build()

    def build(self):
        page_header(self, "Feed Inventory", "Manage feed stock levels and purchases.")
        self.form_card = tk.Frame(self, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        self.form_card.pack(fill="x", padx=24, pady=(12, 10))
        tk.Label(self.form_card, text="✚  Add Feed Stock", font=(FONT, 13, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=20, pady=(18, 10))
        form = tk.Frame(self.form_card, bg=COLORS["white"])
        form.pack(fill="x", padx=20, pady=(0, 14))
        for c in (1, 3): form.grid_columnconfigure(c, weight=1)
        self.fields = {}
        specs = [
            ("Feed Type *", "feed_type", "entry", 0, 0),
            ("Brand", "brand", "entry", 0, 2),
            ("Quantity *", "quantity", "entry", 2, 0),
            ("Unit", "unit", "combo", 2, 2),
            ("Min Stock Alert", "min_stock", "entry", 4, 0),
            ("Supplier", "supplier", "entry", 4, 2),
            ("Purchase Date *", "purchase_date", "entry", 6, 0),
            ("Cost (₱)", "cost", "entry", 6, 2),
        ]
        for label, key, kind, row, col in specs:
            tk.Label(form, text=label, font=(FONT, 10, "bold"), bg=COLORS["white"], fg=COLORS["text"]).grid(row=row, column=col, sticky="w", padx=(0, 12), pady=(4, 4))
            if kind == "combo":
                w = ttk.Combobox(form, values=["kg", "sacks", "bags", "g", "lbs"], state="readonly", font=(FONT, 10))
                w.set("kg")
            else:
                w = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1, bg=COLORS["white"], fg=COLORS["text"])
            w.grid(row=row + 1, column=col, sticky="ew", padx=(0, 16), pady=(0, 8), ipady=5 if kind == "entry" else 2)
            self.fields[key] = w
        self.fields["min_stock"].insert(0, "10")
        self.fields["purchase_date"].insert(0, date.today().strftime("%m/%d/%Y"))
        footer = tk.Frame(self.form_card, bg=COLORS["white"])
        footer.pack(fill="x", padx=20, pady=(0, 16))
        tk.Frame(footer, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 14))
        make_button(footer, "▣  Save Feed Record", self.save_record).pack(side="right")

        history = tk.Frame(self, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        history.pack(fill="both", expand=True, padx=24, pady=(10, 16))
        tk.Label(history, text="☷  Feed Inventory History", font=(FONT, 13, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=20, pady=(16, 10))
        table_wrap = tk.Frame(history, bg=COLORS["white"])
        table_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        cols = ("FEED TYPE", "BRAND", "QUANTITY", "UNIT", "SUPPLIER", "DATE", "COST (₱)")
        self.tree = styled_tree(table_wrap, cols, (160, 140, 110, 80, 160, 120, 110), height=8)
        self.tree.pack(fill="both", expand=True)
        actions = tk.Frame(history, bg=COLORS["white"])
        actions.pack(fill="x", padx=20, pady=(0, 14))
        make_button(actions, "Edit Selected", self.edit_selected, bg=COLORS["orange"]).pack(side="left", padx=4)
        make_button(actions, "Delete Selected", self.delete_selected, bg=COLORS["red"]).pack(side="left", padx=4)
        self.refresh()

    def _value(self, key):
        w = self.fields[key]
        return w.get().strip()

    def _clear_form(self):
        for key, w in self.fields.items():
            if isinstance(w, ttk.Combobox): w.set("kg")
            else: w.delete(0, "end")
        self.fields["min_stock"].insert(0, "10")
        self.fields["purchase_date"].insert(0, date.today().strftime("%m/%d/%Y"))

    def _form_data(self):
        feed_type = self._value("feed_type")
        qty = float(self._value("quantity"))
        min_stock = float(self._value("min_stock") or 10)
        raw_date = self._value("purchase_date")
        try: purchase_date = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
        except ValueError: purchase_date = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
        cost = self._value("cost")
        if not feed_type: raise ValueError("Feed Type is required.")
        if qty < 0 or min_stock < 0 or (cost and float(cost) < 0): raise ValueError("Quantity, stock alert, and cost cannot be negative.")
        return {"feed_type": feed_type, "brand": self._value("brand"), "quantity": qty,
                "unit": self._value("unit") or "kg", "min_stock": min_stock,
                "supplier": self._value("supplier"), "purchase_date": purchase_date,
                "cost": float(cost) if cost else None, "notes": None}

    def save_record(self):
        try:
            data = self._form_data()
            add_feed(data)
            messagebox.showinfo("Saved", "Feed record saved successfully.")
            self._clear_form(); self.refresh()
        except ValueError as e: messagebox.showwarning("Invalid Information", str(e))
        except Exception as e: messagebox.showerror("Error", str(e))

    def refresh(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for r in list_feed():
            qty = float(r.get("quantity") or 0)
            threshold = float(r.get("min_stock") or 10)
            self.tree.insert("", "end", iid=r["feed_id"], tags=("low",) if qty <= threshold else (), values=(
                r.get("feed_type") or "—", r.get("brand") or "—", f"{qty:g}", r.get("unit") or "kg",
                r.get("supplier") or "—", r.get("purchase_date") or "—",
                f"₱{float(r.get('cost') or 0):,.2f}" if r.get("cost") not in (None, "") else "—"))
        self.tree.tag_configure("low", foreground=COLORS["red"])

    def _selected(self):
        sel = self.tree.selection()
        if not sel: messagebox.showinfo("Select", "Select a feed record first."); return None
        return int(sel[0])

    def edit_selected(self):
        fid = self._selected()
        if fid is None: return
        row = next((r for r in list_feed() if int(r["feed_id"]) == fid), None)
        if not row: return
        for key in ("feed_type", "brand", "quantity", "unit", "min_stock", "supplier", "cost"):
            w = self.fields[key]
            value = row.get(key, "")
            if isinstance(w, ttk.Combobox): w.set(str(value or "kg"))
            else: w.delete(0, "end"); w.insert(0, str(value if value is not None else ""))
        w = self.fields["purchase_date"]; w.delete(0, "end")
        try: w.insert(0, datetime.strptime(str(row.get("purchase_date"))[:10], "%Y-%m-%d").strftime("%m/%d/%Y"))
        except Exception: w.insert(0, str(row.get("purchase_date") or ""))
        self.editing_id = fid
        # Switch the save action to update the selected row.
        for child in self.form_card.winfo_children():
            if isinstance(child, tk.Frame):
                for button in child.winfo_children():
                    if isinstance(button, tk.Button) and "Save Feed Record" in button.cget("text"):
                        button.configure(text="▣  Update Feed Record", command=self.update_record)

    def update_record(self):
        try:
            update_feed(self.editing_id, self._form_data())
            self.editing_id = None
            for child in self.form_card.winfo_children():
                if isinstance(child, tk.Frame):
                    for button in child.winfo_children():
                        if isinstance(button, tk.Button) and "Update Feed Record" in button.cget("text"):
                            button.configure(text="▣  Save Feed Record", command=self.save_record)
            self._clear_form(); self.refresh()
            messagebox.showinfo("Updated", "Feed record updated successfully.")
        except Exception as e: messagebox.showerror("Error", str(e))

    def delete_selected(self):
        fid = self._selected()
        if fid is not None and messagebox.askyesno("Delete", "Delete this feed record?"):
            delete_feed(fid); self.refresh()


# =====================================================================
# PAGE: EXPENSES (Updated with Scrollable Layout & UI Matching)
# =====================================================================
class ExpensesPage(tk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent, bg=COLORS["bg"])
        self.user = user
        
        # Add scrollable canvas layout
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.main_container = tk.Frame(self.canvas, bg=COLORS["bg"])

        self.main_container.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", 
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.main_container, anchor="nw")
        
        self.build()

    def build(self):
        page_header(self.main_container, "Expenses", "Track farm expenses and costs.")
        
        # Top cards frame to hold stat card on left
        top_cards_frame = tk.Frame(self.main_container, bg=COLORS["bg"])
        top_cards_frame.pack(fill="x", padx=24, pady=(0, 10))
        
        # Total Expenses Card (compact, left aligned)
        self.total_card = stat_card(top_cards_frame, "▦  TOTAL EXPENSES", "₱0.00", "Recorded farm expenses", COLORS["red"])
        self.total_card.pack(side="left", ipadx=40)

        # Form Card
        form_card = tk.Frame(self.main_container, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        form_card.pack(fill="x", padx=24, pady=(12, 10))
        tk.Label(form_card, text="➕ Record New Expense", font=(FONT, 13, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=20, pady=(18, 12))
        
        form = tk.Frame(form_card, bg=COLORS["white"])
        form.pack(fill="x", padx=20, pady=(0, 12))
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        def add_field(row, col, label, widget):
            tk.Label(form, text=label, font=(FONT, 10, "bold"), bg=COLORS["white"], fg=COLORS["text"]).grid(
                row=row*2, column=col, sticky="w", padx=(0, 10), pady=(5, 4))
            widget.grid(row=row*2+1, column=col, sticky="ew", padx=(0, 16) if col==0 else 0, pady=(0, 10), ipady=5 if isinstance(widget, tk.Entry) else 2)
            return widget

        # Row 0
        self.date_e = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1, bg=COLORS["white"], fg=COLORS["text"])
        self.date_e.insert(0, date.today().strftime("%m/%d/%Y"))
        add_field(0, 0, "Date *", self.date_e)

        self.cat_combo = ttk.Combobox(form, values=ExpenseFormDialog.CATEGORIES, state="readonly", font=(FONT, 10))
        self.cat_combo.set("Feed")
        self.cat_combo.configure(background="#EAE8E6")
        add_field(0, 1, "Category *", self.cat_combo)

        # Row 1
        self.amount_e = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1, bg=COLORS["white"], fg=COLORS["text"])
        add_field(1, 0, "Amount (₱) *", self.amount_e)

        # Description (Full width)
        tk.Label(form, text="Description", font=(FONT, 10, "bold"), bg=COLORS["white"], fg=COLORS["text"]).grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 4))
        self.desc_e = tk.Text(form, height=3, font=(FONT, 10), relief="solid", bd=1, wrap="word", bg=COLORS["white"], fg=COLORS["text"])
        self.desc_e.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        # Save Button area
        button_area = tk.Frame(form_card, bg=COLORS["white"])
        button_area.pack(fill="x", padx=20, pady=(0, 16))
        tk.Frame(button_area, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 14))
        make_button(button_area, "💾 Save Expense", self.save_expense, bg=COLORS["sidebar"]).pack(side="right")

        # Table Card (History)
        history = tk.Frame(self.main_container, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        history.pack(fill="both", expand=True, padx=24, pady=(10, 16))
        
        records_header = tk.Frame(history, bg=COLORS["white"])
        records_header.pack(fill="x", padx=20, pady=(16, 10))

        # Left aligned search area
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(records_header, textvariable=self.search_var, font=(FONT, 10), relief="solid", bd=1, width=22)
        search_entry.insert(0, "Search expenses...")
        search_entry.bind("<FocusIn>", lambda e: search_entry.delete(0, 'end') if search_entry.get() == 'Search expenses...' else None)
        search_entry.bind("<FocusOut>", lambda e: search_entry.insert(0, 'Search expenses...') if not search_entry.get() else None)
        search_entry.pack(side="left", padx=(0, 8), ipady=5)
        search_entry.bind("<Return>", lambda event: self.refresh())
        
        make_button(records_header, "Search", self.refresh, bg=COLORS["sidebar"]).pack(side="left", padx=(0, 8))
        make_button(records_header, "C Reset", self.reset, bg=COLORS["white"], fg=COLORS["text"]).pack(side="left")
        records_header.winfo_children()[-1].configure(highlightbackground=COLORS["border"], highlightthickness=1, bd=0)

        table_wrap = tk.Frame(history, bg=COLORS["white"])
        table_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        
        columns = ("DATE", "CATEGORY", "DESCRIPTION", "AMOUNT (₱)")
        widths = (140, 160, 500, 150)
        self.tree = styled_tree(table_wrap, columns, widths, height=7)
        self.tree.pack(fill="both", expand=True)

        actions = tk.Frame(history, bg=COLORS["white"])
        actions.pack(fill="x", padx=20, pady=(0, 14))
        make_button(actions, "Edit Selected", self.edit_selected, bg=COLORS["orange"]).pack(side="left", padx=4)
        make_button(actions, "Delete Selected", self.delete_selected, bg=COLORS["red"]).pack(side="left", padx=4)

        self.refresh()

    def reset(self):
        self.search_var.set("Search expenses...")
        self.refresh()

    def _date_value(self):
        raw = self.date_e.get().strip()
        try: return datetime.strptime(raw, "%m/%d/%Y").date().isoformat()
        except ValueError: return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()

    def save_expense(self):
        try:
            amount_str = self.amount_e.get().strip()
            if not amount_str: raise ValueError("Amount is required.")
            amount = float(amount_str)
            if amount < 0: raise ValueError("Amount cannot be negative.")
            if not self.cat_combo.get(): raise ValueError("Please select a category.")
            
            add_expense({"category": self.cat_combo.get(), "description": self.desc_e.get("1.0", "end").strip() or None,
                         "amount": amount, "expense_date": self._date_value(), "recorded_by": self.user.get("username"), "notes": None})
                         
            self.amount_e.delete(0, "end")
            self.desc_e.delete("1.0", "end")
            self.date_e.delete(0, "end")
            self.date_e.insert(0, date.today().strftime("%m/%d/%Y"))
            self.refresh()
            messagebox.showinfo("Saved", "Expense recorded successfully.")
        except ValueError as e: 
            messagebox.showwarning("Invalid Information", str(e))
        except Exception as e: 
            messagebox.showerror("Error", str(e))

    def refresh(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        
        search_val = self.search_var.get().strip()
        if search_val == "Search expenses...": 
            search_val = ""
            
        rows = list_expenses(search_val)
        total_rows = list_expenses()
        total = sum(float(r.get("amount") or 0) for r in total_rows)
        try:
            inner = self.total_card.winfo_children()[1]
            labels = [w for w in inner.winfo_children() if isinstance(w, tk.Label)]
            labels[1].configure(text=f"₱{total:,.2f}")
        except (tk.TclError, IndexError): pass
        
        for r in rows:
            self.tree.insert("", "end", iid=r["expense_id"], values=(r["expense_date"], r["category"], r.get("description") or "—", f"₱{float(r['amount'] or 0):,.2f}"))

    def _selected(self):
        sel = self.tree.selection()
        if not sel: messagebox.showinfo("Select", "Select an expense first."); return None
        return int(sel[0])

    def edit_selected(self):
        eid = self._selected()
        if eid is None: return
        rows, _ = execute_query("SELECT * FROM expenses WHERE expense_id=%s", (eid,), fetch=True)
        if rows: ExpenseFormDialog(self, rows[0], self.refresh)

    def delete_selected(self):
        eid = self._selected()
        if eid is not None and messagebox.askyesno("Delete", "Delete this expense?"):
            delete_expense(eid); self.refresh()


class ExpenseFormDialog:
    CATEGORIES = ["Feed", "Medicine", "Veterinary", "Equipment",
                  "Utilities", "Labor", "Other"]

    def __init__(self, parent, expense, on_saved):
        self.expense = expense
        self.on_saved = on_saved
        self.win = tk.Toplevel(parent)
        self.win.title("Expense")
        self.win.geometry("480x420")
        self.win.configure(bg=COLORS["white"])
        self.win.transient(parent); self.win.grab_set()

        tk.Label(self.win, text="Expense Record", font=(FONT, 16, "bold"),
                 bg=COLORS["white"]).pack(pady=(18, 8))
        f = tk.Frame(self.win, bg=COLORS["white"], padx=24, pady=8)
        f.pack(fill="both", expand=True)

        self.cat_combo = form_combo(f, 0, "Category", self.CATEGORIES)
        self.desc_e = form_row(f, 1, "Description")
        self.amount_e = form_row(f, 2, "Amount (₱)")
        self.date_e = form_row(f, 3, "Date (YYYY-MM-DD)")
        self.by_e = form_row(f, 4, "Recorded By")
        self.notes_e = form_row(f, 5, "Notes")

        if expense:
            self.cat_combo.set(expense["category"])
            self.desc_e.insert(0, expense["description"] or "")
            self.amount_e.insert(0, str(expense["amount"] or ""))
            self.date_e.insert(0, str(expense["expense_date"] or ""))
            self.by_e.insert(0, expense["recorded_by"] or "")
            self.notes_e.insert(0, expense["notes"] or "")
        else:
            self.cat_combo.set("Feed")
            self.date_e.insert(0, date.today().isoformat())

        btns = tk.Frame(self.win, bg=COLORS["white"], pady=12)
        btns.pack(fill="x")
        make_button(btns, "Save", self.save,
                    bg=COLORS["green"]).pack(side="right", padx=16)
        make_button(btns, "Cancel", self.win.destroy,
                    bg=COLORS["text_muted"]).pack(side="right")

    def save(self):
        try:
            data = {
                "category": self.cat_combo.get() or "Other",
                "description": self.desc_e.get().strip() or None,
                "amount": float(self.amount_e.get().strip() or 0),
                "expense_date": self.date_e.get().strip() or date.today().isoformat(),
                "recorded_by": self.by_e.get().strip() or None,
                "notes": self.notes_e.get().strip() or None,
            }
            if self.expense:
                update_expense(self.expense["expense_id"], data)
            else:
                add_expense(data)
            messagebox.showinfo("Saved", "Expense saved.", parent=self.win)
            self.win.destroy(); self.on_saved()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.win)


# =====================================================================
# PAGE: REPORTS
# =====================================================================
class ReportsPage(tk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent, bg=COLORS["bg"])
        self.user = user; self.current_rows = []; self.current_headers = []
        self.build()

    def build(self):
        page_header(self, "Reports", "Generate and export farm reports.")
        controls = tk.Frame(self, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        controls.pack(fill="x", padx=24, pady=(12, 10))
        inner = tk.Frame(controls, bg=COLORS["white"]); inner.pack(fill="x", padx=20, pady=16)
        tk.Label(inner, text="Report Type", font=(FONT, 10, "bold"), bg=COLORS["white"]).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.report_combo = ttk.Combobox(inner, values=["Animal Inventory", "Health Records", "Birth Records", "Death / Loss Records", "Sales Records", "Feed Inventory", "Expenses"], state="readonly", font=(FONT, 10), width=24)
        self.report_combo.set("Animal Inventory"); self.report_combo.grid(row=1, column=0, sticky="ew", padx=(0, 14), pady=(5, 0))
        tk.Label(inner, text="From Date", font=(FONT, 10, "bold"), bg=COLORS["white"]).grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.from_e = tk.Entry(inner, font=(FONT, 10), relief="solid", bd=1, width=16); self.from_e.grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(5, 0)); self.from_e.insert(0, "01/01/2026")
        tk.Label(inner, text="To Date", font=(FONT, 10, "bold"), bg=COLORS["white"]).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.to_e = tk.Entry(inner, font=(FONT, 10), relief="solid", bd=1, width=16); self.to_e.grid(row=1, column=2, sticky="ew", padx=(0, 14), pady=(5, 0)); self.to_e.insert(0, date.today().strftime("%m/%d/%Y"))
        make_button(inner, "▶  Run Report", self.generate).grid(row=1, column=3, padx=6, pady=(5, 0))
        make_button(inner, "⇩  Export CSV", self.export_csv, bg=COLORS["white"], fg=COLORS["text"], highlightbackground=COLORS["border"], highlightthickness=1).grid(row=1, column=4, padx=6, pady=(5, 0))
        result = tk.Frame(self, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        result.pack(fill="both", expand=True, padx=24, pady=(10, 18))
        tk.Label(result, text="☷  Report Results", font=(FONT, 13, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=20, pady=(16, 10))
        self.tree_wrap = tk.Frame(result, bg=COLORS["white"]); self.tree_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.tree = None
        self.generate()

    def _make_tree(self, headers, widths):
        if self.tree: self.tree.destroy()
        self.tree = styled_tree(self.tree_wrap, headers, widths, height=16)
        self.tree.pack(fill="both", expand=True)
        self.current_headers = list(headers)

    def _date_filter(self, rows, key):
        def parse(v):
            if not v: return None
            try: return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
            except ValueError: return None
        try: start = datetime.strptime(self.from_e.get().strip(), "%m/%d/%Y").date() if self.from_e.get().strip() else None
        except ValueError: start = datetime.strptime(self.from_e.get().strip(), "%Y-%m-%d").date()
        try: end = datetime.strptime(self.to_e.get().strip(), "%m/%d/%Y").date() if self.to_e.get().strip() else None
        except ValueError: end = datetime.strptime(self.to_e.get().strip(), "%Y-%m-%d").date()
        return [r for r in rows if (parse(r.get(key)) is None or ((start is None or parse(r.get(key)) >= start) and (end is None or parse(r.get(key)) <= end)))]

    def generate(self):
        choice = self.report_combo.get(); self.current_rows = []
        if choice == "Animal Inventory":
            rows = list_animals(); headers = ("ANIMAL TAG", "ANIMAL NAME", "SPECIES", "BREED", "SEX", "HEALTH STATUS", "LOCATION")
            self._make_tree(headers, (130, 160, 100, 130, 90, 150, 130))
            for a in rows: self._add((a["tag_no"], a["name"] or "—", a["species"], a["breed"] or "—", a["sex"], a["health_status"], a["location"] or "—"))
        elif choice == "Health Records":
            rows = self._date_filter(list_health(), "exam_date"); self._make_tree(("TAG", "ANIMAL", "DATE", "DIAGNOSIS", "TREATMENT", "VET", "STATUS"), (100, 140, 110, 160, 160, 120, 110))
            for r in rows: self._add((r["tag_no"], r["animal_name"] or "—", r["exam_date"], r["diagnosis"] or "—", r["treatment"] or "—", r["veterinarian"] or "—", r["health_status"]))
        elif choice in ("Birth Records", "Death / Loss Records", "Sales Records"):
            typ = {"Birth Records":"Birth", "Death / Loss Records":None, "Sales Records":"Sale"}[choice]
            rows = self._date_filter(list_events(typ or ""), "event_date")
            if choice == "Death / Loss Records": rows = [r for r in rows if r["event_type"] in ("Death", "Missing")]
            self._make_tree(("TYPE", "TAG", "ANIMAL", "DATE", "DESCRIPTION", "STAFF", "AMOUNT (₱)"), (100, 100, 150, 110, 260, 130, 130))
            for r in rows: self._add((r["event_type"], r["tag_no"], r["animal_name"] or "—", r["event_date"], r["description"] or "—", r["responsible_staff"] or "—", f"₱{float(r.get('amount') or 0):,.2f}"))
        elif choice == "Feed Inventory":
            rows = list_feed(); self._make_tree(("FEED TYPE", "BRAND", "QUANTITY", "UNIT", "SUPPLIER", "DATE", "COST (₱)"), (150, 130, 110, 80, 150, 120, 120))
            for r in rows: self._add((r.get("feed_type"), r.get("brand") or "—", r.get("quantity"), r.get("unit"), r.get("supplier") or "—", r.get("purchase_date"), r.get("cost") or "—"))
        else:
            rows = self._date_filter(list_expenses(), "expense_date"); self._make_tree(("DATE", "CATEGORY", "DESCRIPTION", "AMOUNT (₱)", "RECORDED BY"), (130, 150, 300, 140, 150))
            for r in rows: self._add((r["expense_date"], r["category"], r.get("description") or "—", f"₱{float(r.get('amount') or 0):,.2f}", r.get("recorded_by") or "—"))

    def _add(self, values):
        self.tree.insert("", "end", values=values); self.current_rows.append(values)

    def export_csv(self):
        if not self.current_rows: messagebox.showinfo("Empty", "Run a report first."); return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")], initialfile=f"pepa_report_{datetime.now():%Y%m%d_%H%M%S}.csv")
        if not path: return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f); writer.writerow(self.current_headers); writer.writerows(self.current_rows)
            messagebox.showinfo("Exported", f"Report exported successfully:\n{path}")
        except Exception as e: messagebox.showerror("Error", str(e))


# =====================================================================
# PAGE: USERS
# =====================================================================
class UsersPage(tk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent, bg=COLORS["bg"])
        self.current_user = user
        self.build()

    def build(self):
        page_header(self, "User Management", "Manage system access and roles.")
        if self.current_user["role"] == "Admin":
            card = tk.Frame(self, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
            card.pack(fill="x", padx=24, pady=(12, 10))
            tk.Label(card, text="♟  Add User", font=(FONT, 13, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=20, pady=(18, 10))
            form = tk.Frame(card, bg=COLORS["white"]); form.pack(fill="x", padx=20, pady=(0, 12))
            form.grid_columnconfigure(1, weight=1); form.grid_columnconfigure(3, weight=1)
            def field(row, col, label, widget):
                tk.Label(form, text=label, font=(FONT, 10, "bold"), bg=COLORS["white"], fg=COLORS["text"]).grid(row=row*2, column=col, sticky="w", padx=(0, 12), pady=(4, 4))
                widget.grid(row=row*2+1, column=col, sticky="ew", padx=(0, 16), pady=(0, 10), ipady=5 if isinstance(widget, tk.Entry) else 2)
            self.full_e = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1)
            self.user_e = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1)
            self.pass_e = tk.Entry(form, font=(FONT, 10), relief="solid", bd=1, show="•")
            self.role_combo = ttk.Combobox(form, values=["Admin", "Farm Staff"], state="readonly", font=(FONT, 10)); self.role_combo.set("Farm Staff")
            field(0, 0, "Full Name *", self.full_e); field(0, 2, "Username *", self.user_e); field(1, 0, "Password *", self.pass_e); field(1, 2, "Role", self.role_combo)
            footer = tk.Frame(card, bg=COLORS["white"]); footer.pack(fill="x", padx=20, pady=(0, 16))
            tk.Frame(footer, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 14))
            make_button(footer, "♟  Create User", self.create_user).pack(side="right")

        table_card = tk.Frame(self, bg=COLORS["white"], highlightbackground=COLORS["border"], highlightthickness=1)
        table_card.pack(fill="both", expand=True, padx=24, pady=(10, 16))
        tk.Label(table_card, text="♟  System Users", font=(FONT, 13, "bold"), bg=COLORS["white"], fg=COLORS["text"]).pack(anchor="w", padx=20, pady=(16, 10))
        table = tk.Frame(table_card, bg=COLORS["white"]); table.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self.tree = styled_tree(table, ("ID", "USERNAME", "FULL NAME", "ROLE", "STATUS", "ACTIONS"), (70, 150, 220, 130, 120, 140), height=10)
        self.tree.pack(fill="both", expand=True)
        actions = tk.Frame(table_card, bg=COLORS["white"]); actions.pack(fill="x", padx=20, pady=(0, 14))
        if self.current_user["role"] == "Admin":
            make_button(actions, "Activate / Deactivate", self.toggle_selected, bg=COLORS["orange"]).pack(side="left", padx=4)
            make_button(actions, "Delete Selected", self.delete_selected, bg=COLORS["red"]).pack(side="left", padx=4)
        self.refresh()

    def create_user(self):
        fn = self.full_e.get().strip(); un = self.user_e.get().strip(); pw = self.pass_e.get()
        if not fn or not un or len(pw) < 6:
            messagebox.showwarning("Validation", "Enter a full name, username, and a password with at least 6 characters."); return
        try:
            add_user(un, pw, fn, self.role_combo.get() or "Farm Staff")
            self.full_e.delete(0, "end"); self.user_e.delete(0, "end"); self.pass_e.delete(0, "end"); self.role_combo.set("Farm Staff")
            self.refresh(); messagebox.showinfo("Created", "User account created successfully.")
        except Exception as e: messagebox.showerror("Error", str(e))

    def refresh(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for u in list_users():
            status = "● Active" if u["is_active"] else "○ Inactive"
            action = "You" if u["user_id"] == self.current_user["user_id"] else "Manage"
            self.tree.insert("", "end", iid=u["user_id"], values=(u["user_id"], u["username"], u["full_name"], u["role"], status, action))
        self.tree.tag_configure("active", foreground=COLORS["green"])

    def _selected(self):
        sel = self.tree.selection()
        if not sel: messagebox.showinfo("Select", "Select a user first."); return None
        return int(sel[0])

    def toggle_selected(self):
        uid = self._selected()
        if uid is None: return
        if uid == self.current_user["user_id"]:
            messagebox.showwarning("Not allowed", "You cannot deactivate yourself."); return
        rows, _ = execute_query("SELECT is_active FROM users WHERE user_id=%s", (uid,), fetch=True)
        if rows: toggle_user(uid, not bool(rows[0]["is_active"])); self.refresh()

    def delete_selected(self):
        uid = self._selected()
        if uid is None: return
        if uid == self.current_user["user_id"]:
            messagebox.showwarning("Not allowed", "You cannot delete yourself."); return
        if messagebox.askyesno("Delete", "Delete this user account?"):
            delete_user(uid); self.refresh()


class UserFormDialog:
    def __init__(self, parent, on_saved):
        self.on_saved = on_saved
        self.win = tk.Toplevel(parent)
        self.win.title("Add User")
        self.win.geometry("460x400")
        self.win.configure(bg=COLORS["white"])
        self.win.transient(parent); self.win.grab_set()

        tk.Label(self.win, text="Add User", font=(FONT, 16, "bold"),
                 bg=COLORS["white"]).pack(pady=(18, 8))
        f = tk.Frame(self.win, bg=COLORS["white"], padx=24, pady=8)
        f.pack(fill="both", expand=True)

        self.full_e = form_row(f, 0, "Full Name")
        self.user_e = form_row(f, 1, "Username")
        self.pass_e = form_row(f, 2, "Password (min 6)", show="•")
        self.role_combo = form_combo(f, 3, "Role", ["Admin", "Farm Staff"])
        self.role_combo.set("Farm Staff")

        btns = tk.Frame(self.win, bg=COLORS["white"], pady=12)
        btns.pack(fill="x")
        make_button(btns, "Save", self.save,
                    bg=COLORS["green"]).pack(side="right", padx=16)
        make_button(btns, "Cancel", self.win.destroy,
                    bg=COLORS["text_muted"]).pack(side="right")

    def save(self):
        fn = self.full_e.get().strip()
        un = self.user_e.get().strip()
        pw = self.pass_e.get()
        if not fn or not un or len(pw) < 6:
            messagebox.showwarning("Validation",
                "Fill all fields. Password ≥ 6 characters.", parent=self.win)
            return
        try:
            add_user(un, pw, fn, self.role_combo.get())
            messagebox.showinfo("Saved", "User created.", parent=self.win)
            self.win.destroy(); self.on_saved()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.win)


# =====================================================================
# MAIN WINDOW
# =====================================================================
class MainWindow(tk.Frame):
    def __init__(self, root, user):
        super().__init__(root, bg=COLORS["bg"])
        self.root = root
        self.user = user
        self.pack(fill="both", expand=True)
        self._logo = None
        self._current_page = None
        self._build()

    def _build(self):
        self.sidebar = Sidebar(self, self.navigate, self.logout)
        self.sidebar.pack(side="left", fill="y")

        right_container = tk.Frame(self, bg=COLORS["bg"])
        right_container.pack(side="left", fill="both", expand=True)

        # Reduced top bar height to match reference image tighter
        top = tk.Frame(right_container, bg=COLORS["lavender"], height=42)
        top.pack(fill="x")
        top.pack_propagate(False)

        left = tk.Frame(top, bg=COLORS["lavender"])
        left.pack(side="left", padx=24, pady=8)
        tk.Label(left, text="🏠  Pepa | Swine Registration and Monitoring System",
                 font=(FONT, 11, "bold"), bg=COLORS["lavender"],
                 fg=COLORS["text"]).pack(side="left")

        right = tk.Frame(top, bg=COLORS["lavender"])
        right.pack(side="right", padx=24, pady=8)
        
        user_name = self.user.get("full_name") or "System Administrator"
        user_role = self.user.get("role") or "Admin"
        
        tk.Label(right, text=f"👤 {user_name} ({user_role})",
                 font=(FONT, 10, "bold"), bg=COLORS["lavender"],
                 fg=COLORS["purple_accent"]).pack(side="right")

        self.content = tk.Frame(right_container, bg=COLORS["bg"])
        self.content.pack(fill="both", expand=True)

        self.navigate("dashboard")

    def navigate(self, key, payload=None):
        self.sidebar.set_active(key)
        if self._current_page:
            self._current_page.destroy()

        pages = {
            "dashboard": lambda: DashboardPage(self.content, self.user, self.navigate),
            "animals":   lambda: AnimalsPage(self.content, self.user, self.navigate),
            "animal_form": lambda: AnimalFormPage(self.content, self.user, self.navigate, payload),
            "health":    lambda: HealthPage(self.content, self.user),
            "births":    lambda: EventsPage(self.content, self.user, "births"),
            "deaths":    lambda: EventsPage(self.content, self.user, "deaths"),
            "sales":     lambda: EventsPage(self.content, self.user, "sales"),
            "feed":      lambda: FeedPage(self.content, self.user),
            "expenses":  lambda: ExpensesPage(self.content, self.user),
            "reports":   lambda: ReportsPage(self.content, self.user),
            "users":     lambda: UsersPage(self.content, self.user),
        }
        page = pages.get(key, pages["dashboard"])()
        page.pack(fill="both", expand=True)
        self._current_page = page

    def logout(self):
        if messagebox.askyesno("Log out", "Are you sure you want to log out?"):
            self.destroy()
            LoginWindow(self.root, self._on_login_success)

    def _on_login_success(self, user):
        self.destroy()
        MainWindow(self.root, user)


# =====================================================================
# ENTRY POINT
# =====================================================================
def start_app(root, user):
    for w in root.winfo_children():
        w.destroy()
    root.title("PEPA – Swine Registration and Monitoring System")
    root.state("zoomed")
    root.minsize(1024, 640)
    root.configure(bg=COLORS["bg"])
    MainWindow(root, user)


def main():
    ok, msg = test_connection()
    root = tk.Tk()

    if not ok:
        messagebox.showerror(
            "Database connection failed",
            f"Could not connect to MySQL:\n\n{msg}\n\n"
            "Check your .env file and that the pepa_db database "
            "has been created with schema.sql.")
        root.destroy()
        return

    LoginWindow(root, lambda u: start_app(root, u))
    root.mainloop()


if __name__ == "__main__":
    main()