"""Tests for order endpoints"""

import pytest
from fastapi import status
from app.models import OrderStatus


def test_create_order_success(client, sample_order_data):
    """Test creating a new order"""
    response = client.post("/orders/", json=sample_order_data)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["customer_name"] == sample_order_data["customer_name"]
    assert data["customer_email"] == sample_order_data["customer_email"]
    assert data["status"] == OrderStatus.PENDING.value
    assert "id" in data
    assert "total" in data
    assert len(data["items"]) == len(sample_order_data["items"])


def test_create_order_product_not_found(client):
    """Test creating order with non-existent product"""
    order_data = {
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "items": [
            {
                "product_id": 99999,  # Non-existent
                "quantity": 1
            }
        ]
    }

    response = client.post("/orders/", json=order_data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "not found" in response.json()["detail"].lower()


def test_create_order_insufficient_stock(client, sample_product):
    """Test creating order with insufficient stock"""
    order_data = {
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "items": [
            {
                "product_id": sample_product.id,
                "quantity": 1000  # More than available stock
            }
        ]
    }

    response = client.post("/orders/", json=order_data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "insufficient stock" in response.json()["detail"].lower()


def test_create_order_validation_error(client, sample_product):
    """Test creating order with invalid data"""
    invalid_data = {
        "customer_name": "",  # Empty name
        "customer_email": "invalid-email",  # Invalid email
        "items": []  # Empty items
    }

    response = client.post("/orders/", json=invalid_data)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_order_updates_stock(client, sample_product, sample_order_data, db):
    """Test that creating order updates product stock"""
    initial_stock = sample_product.stock
    order_quantity = sample_order_data["items"][0]["quantity"]

    response = client.post("/orders/", json=sample_order_data)
    assert response.status_code == status.HTTP_201_CREATED

    # Refresh product from database
    db.refresh(sample_product)

    # Verify stock was decreased
    assert sample_product.stock == initial_stock - order_quantity


def test_list_orders_empty(client):
    """Test listing orders when database is empty"""
    response = client.get("/orders/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_list_orders_with_data(client, sample_order):
    """Test listing orders with existing data"""
    response = client.get("/orders/")

    assert response.status_code == status.HTTP_200_OK
    orders = response.json()
    assert len(orders) == 1
    assert orders[0]["id"] == sample_order.id
    assert orders[0]["customer_name"] == sample_order.customer_name


def test_list_orders_pagination(client, db, sample_product):
    """Test order list pagination"""
    # Create multiple orders
    from app.models import Order, OrderItem, OrderStatus
    for i in range(5):
        order = Order(
            customer_name=f"Customer {i}",
            customer_email=f"customer{i}@example.com",
            status=OrderStatus.PENDING,
            total=29.99
        )
        order_item = OrderItem(
            product_id=sample_product.id,
            quantity=1,
            price=sample_product.price
        )
        order.items.append(order_item)
        db.add(order)
    db.commit()

    # Test with limit
    response = client.get("/orders/?skip=0&limit=3")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 3

    # Test with skip
    response = client.get("/orders/?skip=2&limit=10")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 3


def test_get_order_success(client, sample_order):
    """Test getting an order by ID"""
    response = client.get(f"/orders/{sample_order.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == sample_order.id
    assert data["customer_name"] == sample_order.customer_name
    assert len(data["items"]) > 0


def test_get_order_not_found(client):
    """Test getting a non-existent order"""
    response = client.get("/orders/99999")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_update_order_status_success(client, sample_order):
    """Test updating order status"""
    status_update = {"status": OrderStatus.PROCESSING.value}

    response = client.put(f"/orders/{sample_order.id}/status", json=status_update)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == OrderStatus.PROCESSING.value


def test_update_order_status_to_shipped(client, sample_order):
    """Test updating order status to shipped"""
    status_update = {"status": OrderStatus.SHIPPED.value}

    response = client.put(f"/orders/{sample_order.id}/status", json=status_update)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == OrderStatus.SHIPPED.value


def test_update_order_status_not_found(client):
    """Test updating status of non-existent order"""
    status_update = {"status": OrderStatus.PROCESSING.value}

    response = client.put("/orders/99999/status", json=status_update)

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_cancel_order_success(client, sample_order, sample_product, db):
    """Test canceling an order"""
    # Record initial stock
    initial_stock = sample_product.stock

    response = client.delete(f"/orders/{sample_order.id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify order is deleted
    response = client.get(f"/orders/{sample_order.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Verify stock was restored
    db.refresh(sample_product)
    assert sample_product.stock == initial_stock + sample_order.items[0].quantity


def test_cancel_order_not_found(client):
    """Test canceling a non-existent order"""
    response = client.delete("/orders/99999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_order_total_calculation(client, sample_product):
    """Test that order total is calculated correctly"""
    order_data = {
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "items": [
            {
                "product_id": sample_product.id,
                "quantity": 3
            }
        ]
    }

    response = client.post("/orders/", json=order_data)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    expected_total = sample_product.price * 3
    assert data["total"] == expected_total


def test_order_lifecycle(client, sample_product):
    """Test complete order lifecycle"""
    # Create order
    order_data = {
        "customer_name": "Lifecycle Customer",
        "customer_email": "lifecycle@example.com",
        "items": [
            {
                "product_id": sample_product.id,
                "quantity": 2
            }
        ]
    }
    response = client.post("/orders/", json=order_data)
    assert response.status_code == status.HTTP_201_CREATED
    order_id = response.json()["id"]

    # Read order
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == OrderStatus.PENDING.value

    # Update status to processing
    response = client.put(
        f"/orders/{order_id}/status",
        json={"status": OrderStatus.PROCESSING.value}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == OrderStatus.PROCESSING.value

    # Update status to shipped
    response = client.put(
        f"/orders/{order_id}/status",
        json={"status": OrderStatus.SHIPPED.value}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == OrderStatus.SHIPPED.value

    # Cancel order
    response = client.delete(f"/orders/{order_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify deleted
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_root_endpoint(client):
    """Test root endpoint"""
    response = client.get("/")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "message" in data
    assert "version" in data
