"""CRUD operations for database"""

from sqlalchemy.orm import Session
from typing import List, Optional

from . import models, schemas


# Product CRUD operations
def create_product(db: Session, product: schemas.ProductCreate) -> models.Product:
    """Create a new product"""
    db_product = models.Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def get_product(db: Session, product_id: int) -> Optional[models.Product]:
    """Get product by ID"""
    return db.query(models.Product).filter(models.Product.id == product_id).first()


def get_products(db: Session, skip: int = 0, limit: int = 100) -> List[models.Product]:
    """Get all products with pagination"""
    return db.query(models.Product).offset(skip).limit(limit).all()


def update_product(
    db: Session,
    product_id: int,
    product_update: schemas.ProductUpdate
) -> Optional[models.Product]:
    """Update a product"""
    db_product = get_product(db, product_id)
    if not db_product:
        return None

    # Update only provided fields
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_product, field, value)

    db.commit()
    db.refresh(db_product)
    return db_product


def delete_product(db: Session, product_id: int) -> bool:
    """Delete a product"""
    db_product = get_product(db, product_id)
    if not db_product:
        return False

    db.delete(db_product)
    db.commit()
    return True


# Order CRUD operations
def create_order(db: Session, order: schemas.OrderCreate) -> models.Order:
    """Create a new order"""
    # Create order
    db_order = models.Order(
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        status=models.OrderStatus.PENDING
    )

    # Calculate total and create order items
    total = 0.0
    for item in order.items:
        product = get_product(db, item.product_id)
        if not product:
            raise ValueError(f"Product {item.product_id} not found")

        if product.stock < item.quantity:
            raise ValueError(f"Insufficient stock for product {product.id}")

        # Create order item
        order_item = models.OrderItem(
            product_id=item.product_id,
            quantity=item.quantity,
            price=product.price
        )
        db_order.items.append(order_item)

        # Update total
        total += product.price * item.quantity

        # Update product stock
        product.stock -= item.quantity

    db_order.total = total

    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


def get_order(db: Session, order_id: int) -> Optional[models.Order]:
    """Get order by ID"""
    return db.query(models.Order).filter(models.Order.id == order_id).first()


def get_orders(db: Session, skip: int = 0, limit: int = 100) -> List[models.Order]:
    """Get all orders with pagination"""
    return db.query(models.Order).offset(skip).limit(limit).all()


def update_order_status(
    db: Session,
    order_id: int,
    status: models.OrderStatus
) -> Optional[models.Order]:
    """Update order status"""
    db_order = get_order(db, order_id)
    if not db_order:
        return None

    db_order.status = status
    db.commit()
    db.refresh(db_order)
    return db_order


def cancel_order(db: Session, order_id: int) -> bool:
    """Cancel an order and restore product stock"""
    db_order = get_order(db, order_id)
    if not db_order:
        return False

    # Restore product stock
    for item in db_order.items:
        product = get_product(db, item.product_id)
        if product:
            product.stock += item.quantity

    # Delete order
    db.delete(db_order)
    db.commit()
    return True
