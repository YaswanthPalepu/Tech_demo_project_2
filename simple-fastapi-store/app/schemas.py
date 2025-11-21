"""Pydantic schemas for request/response validation"""

from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime
from .models import OrderStatus


# Product schemas
class ProductBase(BaseModel):
    """Base product schema"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0)


class ProductCreate(ProductBase):
    """Schema for creating a product"""
    pass


class ProductUpdate(BaseModel):
    """Schema for updating a product"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    stock: Optional[int] = Field(None, ge=0)


class ProductResponse(ProductBase):
    """Schema for product response"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Order Item schemas
class OrderItemBase(BaseModel):
    """Base order item schema"""
    product_id: int
    quantity: int = Field(..., gt=0)


class OrderItemCreate(OrderItemBase):
    """Schema for creating order item"""
    pass


class OrderItemResponse(BaseModel):
    """Schema for order item response"""
    id: int
    product_id: int
    quantity: int
    price: float

    class Config:
        from_attributes = True


# Order schemas
class OrderBase(BaseModel):
    """Base order schema"""
    customer_name: str = Field(..., min_length=1, max_length=100)
    customer_email: EmailStr


class OrderCreate(OrderBase):
    """Schema for creating an order"""
    items: List[OrderItemCreate] = Field(..., min_items=1)


class OrderStatusUpdate(BaseModel):
    """Schema for updating order status"""
    status: OrderStatus


class OrderResponse(OrderBase):
    """Schema for order response"""
    id: int
    status: OrderStatus
    total: float
    created_at: datetime
    items: List[OrderItemResponse]

    class Config:
        from_attributes = True
