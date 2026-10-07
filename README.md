# Task Management Application (Flask + SQLite)

## 1. Setup (Windows / VS Code)
1. Install Python 3.10+ from python.org (tick "Add Python to PATH").
2. Open VS Code > File > Open Folder > select the `task-management-app` folder.
3. Open the terminal: Terminal > New Terminal.
4. Create a virtual environment:   `python -m venv venv`
5. Activate it (Windows):          `venv\Scripts\activate`
   (Mac/Linux):                    `source venv/bin/activate`
6. Install packages:               `pip install -r requirements.txt`
7. Run the app:                    `python app.py`
8. Open http://127.0.0.1:5000 in your browser.

If PowerShell blocks activation, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 2. Database
No manual step needed. `database.db` and both tables (users, tasks) are created
automatically the first time you run `python app.py`.

## 3. Testing
Registration: /register -> fill name/email/password -> Register. Try the same email again
(duplicate error), an empty field, or a short password.
Login: /login -> correct credentials open the dashboard; wrong ones show an error.
Unauthorized: log out, then visit /dashboard or /api/tasks (redirected / 401).
CRUD: Add Task -> fill form -> Save (Create). Cards appear (Read). Edit button (Update).
Complete button (PATCH). Delete button (Delete). Try an empty title or search/filter/sort.
Isolation: register a second user; they must not see the first user's tasks.
