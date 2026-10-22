# Hotel Management System (Flask + SQLite)

A web app to browse hotel rooms, book a stay, and manage rooms and bookings as an admin.
It uses SQLite, which is built into Python, so there is no database server or password to set up.

## Features
- Guests: browse available rooms, filter by room type, view details, book with a live price estimate, get a booking confirmation
- Admin: log in, dashboard with room and booking stats, add or delete rooms, view bookings, check guests out
- Validation: no past check-in dates, check-out must be after check-in, rooms can't be double-booked

## Tech stack
Python, Flask, Jinja2 templates, SQLite, plain CSS

## How to run
1. Install Python 3.8 or newer (tick "Add Python to PATH" on Windows).
2. Open a terminal in this folder and run:
   ```
   pip install -r requirements.txt
   python app.py
   ```
   On Windows you can also double-click `run.bat`.
3. Open http://127.0.0.1:5000

The database file `hotel.db` is created automatically from `schema.sql` with sample rooms and bookings.
Delete `hotel.db` to reset to the sample data.

## Admin login
- URL: http://127.0.0.1:5000/admin/login
- Username: `admin`
- Password: `adminpass`

To change them, set the `ADMIN_USERNAME`, `ADMIN_PASSWORD` and `SECRET_KEY` environment variables.

## Project structure
```
app.py            Flask routes and database code
schema.sql        Database tables
templates/        HTML pages (Jinja2)
static/style.css  Styling
```
