import os
import re
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Database URL: SQLite by default for zero-setup friction, or PostgreSQL/Supabase
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./billcare.db")

# Convert legacy 'postgres://' or standard 'postgresql://' to explicit 'postgresql+psycopg2://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# Sanitize special characters in PostgreSQL password (such as #, $, %, etc.)
if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgresql+"):
    try:
        pattern = re.compile(r"^(postgresql(?:\+[a-z0-9]+)?:\/\/)([^:]+):(.*)@([^@]+)$")
        match = pattern.match(DATABASE_URL)
        if match:
            scheme, user, raw_password, rest = match.groups()
            # If password contains characters that break URI parsing
            if "#" in raw_password or not re.search(r"^([a-zA-Z0-9_\-\.~]|%[0-9a-fA-F]{2})+$", raw_password):
                # Unquote in case partially quoted, then safely quote all reserved chars
                unquoted = urllib.parse.unquote(raw_password)
                encoded_pw = urllib.parse.quote(unquoted, safe="")
                DATABASE_URL = f"{scheme}{user}:{encoded_pw}@{rest}"

            # Ensure sslmode=require for Supabase cloud hosts
            if "supabase.co" in rest and "sslmode=" not in rest:
                delimiter = "&" if "?" in rest else "?"
                DATABASE_URL = f"{DATABASE_URL}{delimiter}sslmode=require"
    except Exception:
        pass

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
