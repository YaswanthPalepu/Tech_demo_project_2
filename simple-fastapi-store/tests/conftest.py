"""Test fixtures and configuration"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app import models

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_store.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Create a fresh database for each test"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """Create test client with database override"""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def sample_product_data():
    """Sample product data for testing"""
    return {
        "name": "Test Product",
        "description": "A test product",
        "price": 29.99,
        "stock": 100
    }


@pytest.fixture
def sample_product(db, sample_product_data):
    """Create a sample product in the database"""
    product = models.Product(**sample_product_data)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@pytest.fixture
def sample_order_data(sample_product):
    """Sample order data for testing"""
    return {
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "items": [
            {
                "product_id": sample_product.id,
                "quantity": 2
            }
        ]
    }


@pytest.fixture
def sample_order(db, sample_product):
    """Create a sample order in the database"""
    order = models.Order(
        customer_name="Jane Doe",
        customer_email="jane@example.com",
        status=models.OrderStatus.PENDING,
        total=59.98
    )
    order_item = models.OrderItem(
        product_id=sample_product.id,
        quantity=2,
        price=sample_product.price
    )
    order.items.append(order_item)

    db.add(order)
    db.commit()
    db.refresh(order)
    return order
