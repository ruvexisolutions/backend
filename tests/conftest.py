import os
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.core.models import SalonModel, UserModel
from app.core.security import hash_password, create_access_token

# Test in-memory SQLite database
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def seed_test_data(db_session):
    now = datetime.utcnow()
    trial_end = now + timedelta(days=7)

    # 1. Salon A (In 7-Day Trial)
    salon_a = SalonModel(
        id="sln_tenant_a",
        name="Atelier Lumiere (Tenant A)",
        slug="atelier-lumiere",
        branch="Bandra Studio",
        city="Mumbai",
        phone="+919800011111",
        email="manager@lumiere.com",
        trial_started_at=now,
        trial_ends_at=trial_end,
        subscription_status="trial",
        subscription_plan="free_trial",
        upi_id="lumiere.pos@icici",
        upi_payee_name="Atelier Lumiere",
        upi_enabled=True,
        cash_enabled=True,
    )
    db_session.add(salon_a)

    # Manager A
    mgr_a = UserModel(
        id="usr_mgr_a",
        salon_id=salon_a.id,
        name="Aarav Sharma",
        email="manager@lumiere.com",
        phone="+919800011111",
        role="SALON_MANAGER",
        password_hash=hash_password("password123"),
    )
    db_session.add(mgr_a)

    # Receptionist A
    rec_a = UserModel(
        id="usr_rec_a",
        salon_id=salon_a.id,
        name="Riya Sen",
        email="reception@lumiere.com",
        phone="+919800022222",
        role="SALON_RECEPTIONIST",
        password_hash=hash_password("password123"),
    )
    db_session.add(rec_a)

    # 2. Salon B (Second Tenant)
    salon_b = SalonModel(
        id="sln_tenant_b",
        name="Velvet Crown Atelier (Tenant B)",
        slug="velvet-crown",
        branch="Indiranagar Studio",
        city="Bengaluru",
        phone="+919800033333",
        email="manager@velvet.com",
        trial_started_at=now,
        trial_ends_at=trial_end,
        subscription_status="active",
        subscription_plan="pro",
        upi_id="velvet.pos@icici",
        upi_payee_name="Velvet Crown Atelier",
        upi_enabled=True,
        cash_enabled=True,
    )
    db_session.add(salon_b)

    # Manager B
    mgr_b = UserModel(
        id="usr_mgr_b",
        salon_id=salon_b.id,
        name="Vikram Verma",
        email="manager@velvet.com",
        phone="+919800033333",
        role="SALON_MANAGER",
        password_hash=hash_password("password123"),
    )
    db_session.add(mgr_b)

    db_session.commit()

    token_mgr_a = create_access_token({
        "sub": mgr_a.id,
        "email": mgr_a.email,
        "role": mgr_a.role,
        "salon_id": salon_a.id,
    })

    token_rec_a = create_access_token({
        "sub": rec_a.id,
        "email": rec_a.email,
        "role": rec_a.role,
        "salon_id": salon_a.id,
    })

    token_mgr_b = create_access_token({
        "sub": mgr_b.id,
        "email": mgr_b.email,
        "role": mgr_b.role,
        "salon_id": salon_b.id,
    })

    return {
        "salon_a": salon_a,
        "salon_b": salon_b,
        "mgr_a": mgr_a,
        "rec_a": rec_a,
        "mgr_b": mgr_b,
        "token_mgr_a": token_mgr_a,
        "token_rec_a": token_rec_a,
        "token_mgr_b": token_mgr_b,
    }
