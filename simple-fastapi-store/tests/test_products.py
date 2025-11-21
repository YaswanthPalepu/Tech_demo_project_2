"""Tests for product endpoints"""

import pytest
from fastapi import status


def test_create_product(client, sample_product_data):
    """Test creating a new product"""
    response = client.post("/products/", json=sample_product_data)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == sample_product_data["name"]
    assert data["price"] == sample_product_data["price"]
    assert data["stock"] == sample_product_data["stock"]
    assert "id" in data
    assert "created_at" in data


def test_create_product_validation_error(client):
    """Test creating product with invalid data"""
    invalid_data = {
        "name": "",  # Empty name
        "price": -10,  # Negative price
        "stock": -5  # Negative stock
    }

    response = client.post("/products/", json=invalid_data)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_list_products_empty(client):
    """Test listing products when database is empty"""
    response = client.get("/products/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_list_products_with_data(client, sample_product):
    """Test listing products with existing data"""
    response = client.get("/products/")

    assert response.status_code == status.HTTP_200_OK
    products = response.json()
    assert len(products) == 1
    assert products[0]["id"] == sample_product.id
    assert products[0]["name"] == sample_product.name


def test_list_products_pagination(client, db):
    """Test product list pagination"""
    # Create multiple products
    from app.models import Product
    for i in range(5):
        product = Product(
            name=f"Product {i}",
            description=f"Description {i}",
            price=10.0 + i,
            stock=10
        )
        db.add(product)
    db.commit()

    # Test with limit
    response = client.get("/products/?skip=0&limit=3")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 3

    # Test with skip
    response = client.get("/products/?skip=2&limit=10")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 3


def test_get_product_success(client, sample_product):
    """Test getting a product by ID"""
    response = client.get(f"/products/{sample_product.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == sample_product.id
    assert data["name"] == sample_product.name
    assert data["price"] == sample_product.price


def test_get_product_not_found(client):
    """Test getting a non-existent product"""
    response = client.get("/products/99999")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_update_product_success(client, sample_product):
    """Test updating a product"""
    update_data = {
        "name": "Updated Product",
        "price": 39.99
    }

    response = client.put(f"/products/{sample_product.id}", json=update_data)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["price"] == update_data["price"]
    assert data["stock"] == sample_product.stock  # Unchanged


def test_update_product_partial(client, sample_product):
    """Test partially updating a product"""
    update_data = {"price": 49.99}

    response = client.put(f"/products/{sample_product.id}", json=update_data)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["price"] == update_data["price"]
    assert data["name"] == sample_product.name  # Unchanged


def test_update_product_not_found(client):
    """Test updating a non-existent product"""
    update_data = {"name": "Updated"}

    response = client.put("/products/99999", json=update_data)

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_update_product_validation_error(client, sample_product):
    """Test updating product with invalid data"""
    invalid_data = {"price": -10}

    response = client.put(f"/products/{sample_product.id}", json=invalid_data)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_delete_product_success(client, sample_product):
    """Test deleting a product"""
    response = client.delete(f"/products/{sample_product.id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify product is deleted
    response = client.get(f"/products/{sample_product.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_delete_product_not_found(client):
    """Test deleting a non-existent product"""
    response = client.delete("/products/99999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_product_lifecycle(client):
    """Test complete product lifecycle"""
    # Create
    product_data = {
        "name": "Lifecycle Product",
        "description": "Testing full lifecycle",
        "price": 19.99,
        "stock": 50
    }
    response = client.post("/products/", json=product_data)
    assert response.status_code == status.HTTP_201_CREATED
    product_id = response.json()["id"]

    # Read
    response = client.get(f"/products/{product_id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == product_data["name"]

    # Update
    update_data = {"price": 24.99}
    response = client.put(f"/products/{product_id}", json=update_data)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["price"] == 24.99

    # Delete
    response = client.delete(f"/products/{product_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify deleted
    response = client.get(f"/products/{product_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
