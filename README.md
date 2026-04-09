# Frappify API

A Flask-based REST API that acts as a proxy layer between the Frappify frontend apps and Frappe/ERPNext instances. It handles authentication, session management, request proxying, and WebSocket forwarding.

## Requirements

- Python 3.13+
- PostgreSQL

## Setup

### 1. Clone and navigate

```bash
cd api
```

### 2. Create a virtual environment

```bash
python3 -m venv env
source env/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the `api/` directory:

```env
# Flask
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret-key

# Token expiry
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRES_DAYS=7

# Database
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/frappe_proxy

# Mail
MAIL_SERVER=localhost
MAIL_PORT=1025
MAIL_USE_TLS=False
MAIL_USE_SSL=False
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=no-reply@frappify.local
EMAIL_VERIFICATION_SALT=email-verification
EMAIL_VERIFICATION_MAX_AGE=86400
PASSWORD_RESET_SALT=password-reset
PASSWORD_RESET_MAX_AGE=3600

# Rate limiting
RATE_LIMIT_ENABLED=True
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_KEY_STRATEGY=ip
RATE_LIMIT_EXEMPT_PATHS=/api/health

# WebSocket proxy
WEBSOCKET_PROXY_ENABLED=True
WEBSOCKET_PROXY_TIMEOUT_SECONDS=30

# SQLAlchemy pool
SQLALCHEMY_POOL_RECYCLE_SECONDS=1800
SQLALCHEMY_POOL_TIMEOUT_SECONDS=30
```

### 5. Set up the database

Make sure PostgreSQL is running and the database exists, then run migrations:

```bash
flask db upgrade
```

### 6. Run the development server

```bash
python app.py
```

The API will be available at `http://localhost:5000`.

## Running Tests

```bash
pytest tests/
```

To use a separate test database, set `TEST_DATABASE_URL` in your environment (defaults to an in-memory SQLite database).

## Production Deployment

The project includes a `passenger_wsgi.py` entry point for Phusion Passenger deployments. The `application` WSGI callable is also exported from `app.py` for use with any WSGI server (e.g. Gunicorn):

```bash
gunicorn app:application
```

## Project Structure

```
app/
├── __init__.py       # App factory
├── auth.py           # Authentication helpers
├── config.py         # Configuration classes
├── cookies.py        # Cookie proxy utilities
├── extensions.py     # Flask extension instances
├── models.py         # SQLAlchemy models
├── rate_limiter.py   # Rate limiting middleware
└── routes.py         # API route blueprints
migrations/           # Alembic database migrations
tests/                # Pytest test suite
app.py                # WSGI entry point
requirements.txt      # Python dependencies
```
