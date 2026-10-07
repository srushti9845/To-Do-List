"""Task Management Application - Flask + SQLite"""
import os
import re
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deploying"  # needed for sessions

STATUSES = ["Pending", "In Progress", "Completed"]
PRIORITIES = ["Low", "Medium", "High"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they do not exist."""
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL,
            email    TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            title       TEXT NOT NULL,
            description TEXT DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'Pending',
            priority    TEXT NOT NULL DEFAULT 'Medium',
            due_date    TEXT,
            category    TEXT DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """
    )
    db.commit()
    db.close()


# ------------------------------------------------------------ auth helpers
def login_required(view):
    """Protect normal pages: redirect to login."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access the dashboard.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def api_login_required(view):
    """Protect API routes: return JSON 401."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Unauthorized. Please log in."), 401
        return view(*args, **kwargs)
    return wrapped


# ------------------------------------------------------------------ pages
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "error")
        elif len(name) < 2 or len(name) > 60:
            flash("Name must be between 2 and 60 characters.", "error")
        elif not EMAIL_RE.match(email):
            flash("Please enter a valid email address.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            db = get_db()
            exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                flash("This email is already registered. Please log in.", "error")
            else:
                db.execute(
                    "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                    (name, email, generate_password_hash(password)),
                )
                db.commit()
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user_name=session["user_name"])


# -------------------------------------------------------------- API helpers
def task_to_dict(row):
    t = dict(row)
    today = date.today().isoformat()
    t["is_overdue"] = bool(t["due_date"]) and t["due_date"] < today and t["status"] != "Completed"
    return t


def validate_task(data):
    """Return (clean_data, error_message)."""
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    status = data.get("status") or "Pending"
    priority = data.get("priority") or "Medium"
    due_date = (data.get("due_date") or "").strip()
    category = (data.get("category") or "").strip()

    if not title:
        return None, "Task title cannot be empty."
    if len(title) > 100:
        return None, "Task title must be 100 characters or fewer."
    if len(description) > 1000:
        return None, "Description must be 1000 characters or fewer."
    if len(category) > 40:
        return None, "Category must be 40 characters or fewer."
    if status not in STATUSES:
        return None, "Invalid status."
    if priority not in PRIORITIES:
        return None, "Invalid priority."
    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            return None, "Invalid due date. Use the format YYYY-MM-DD."
    return {
        "title": title, "description": description, "status": status,
        "priority": priority, "due_date": due_date or None, "category": category,
    }, None


def get_own_task(task_id):
    return get_db().execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, session["user_id"])
    ).fetchone()


# ------------------------------------------------------------------ API
@app.route("/api/tasks", methods=["GET"])
@api_login_required
def list_tasks():
    sql = "SELECT * FROM tasks WHERE user_id = ?"
    params = [session["user_id"]]

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    category = request.args.get("category", "")
    sort = request.args.get("sort", "due_asc")

    if q:
        sql += " AND title LIKE ?"
        params.append(f"%{q}%")
    if status in STATUSES:
        sql += " AND status = ?"
        params.append(status)
    if priority in PRIORITIES:
        sql += " AND priority = ?"
        params.append(priority)
    if category:
        sql += " AND category = ?"
        params.append(category)

    if sort == "due_desc":
        sql += " ORDER BY due_date IS NULL, due_date DESC, id DESC"
    elif sort == "newest":
        sql += " ORDER BY id DESC"
    else:
        sql += " ORDER BY due_date IS NULL, due_date ASC, id DESC"

    rows = get_db().execute(sql, params).fetchall()
    return jsonify(tasks=[task_to_dict(r) for r in rows])


@app.route("/api/stats", methods=["GET"])
@api_login_required
def stats():
    db = get_db()
    uid = session["user_id"]
    today = date.today().isoformat()

    def count(extra="", args=()):
        return db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? " + extra, (uid, *args)
        ).fetchone()[0]

    cats = db.execute(
        "SELECT DISTINCT category FROM tasks WHERE user_id = ? AND category != '' ORDER BY category",
        (uid,),
    ).fetchall()
    return jsonify(
        total=count(),
        pending=count("AND status = 'Pending'"),
        in_progress=count("AND status = 'In Progress'"),
        completed=count("AND status = 'Completed'"),
        overdue=count("AND due_date IS NOT NULL AND due_date < ? AND status != 'Completed'", (today,)),
        categories=[c["category"] for c in cats],
    )


@app.route("/api/tasks", methods=["POST"])
@api_login_required
def create_task():
    clean, error = validate_task(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO tasks (user_id, title, description, status, priority, due_date, category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session["user_id"], clean["title"], clean["description"], clean["status"],
         clean["priority"], clean["due_date"], clean["category"]),
    )
    db.commit()
    return jsonify(task=task_to_dict(get_own_task(cur.lastrowid))), 201


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
@api_login_required
def update_task(task_id):
    if not get_own_task(task_id):
        return jsonify(error="Task not found."), 404
    clean, error = validate_task(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    db = get_db()
    db.execute(
        "UPDATE tasks SET title=?, description=?, status=?, priority=?, due_date=?, category=? "
        "WHERE id=? AND user_id=?",
        (clean["title"], clean["description"], clean["status"], clean["priority"],
         clean["due_date"], clean["category"], task_id, session["user_id"]),
    )
    db.commit()
    return jsonify(task=task_to_dict(get_own_task(task_id)))


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@api_login_required
def delete_task(task_id):
    if not get_own_task(task_id):
        return jsonify(error="Task not found."), 404
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, session["user_id"]))
    db.commit()
    return jsonify(message="Task deleted.")


@app.route("/api/tasks/<int:task_id>/complete", methods=["PATCH"])
@api_login_required
def complete_task(task_id):
    if not get_own_task(task_id):
        return jsonify(error="Task not found."), 404
    db = get_db()
    db.execute("UPDATE tasks SET status='Completed' WHERE id=? AND user_id=?",
               (task_id, session["user_id"]))
    db.commit()
    return jsonify(task=task_to_dict(get_own_task(task_id)))


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify(error="Not found."), 404
    return redirect(url_for("login"))


# Create tables automatically whenever the app starts
init_db()

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False)
