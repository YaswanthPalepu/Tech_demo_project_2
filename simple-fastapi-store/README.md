# Simple FastAPI Store - Clean Test Project

A minimal FastAPI project for testing AI test generation systems.

## Features

- ✅ Simple CRUD operations (Products & Orders)
- ✅ No authentication complexity
- ✅ SQLAlchemy with SQLite
- ✅ Clean, testable code
- ✅ ~400 lines total
- ✅ Perfect for testing multi-iteration test generation

## Project Structure

```
simple-fastapi-store/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app with endpoints
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py       # Pydantic schemas
│   ├── database.py      # Database setup
│   └── crud.py          # Database operations
├── tests/
│   ├── __init__.py
│   ├── conftest.py      # Test fixtures
│   ├── test_products.py # Product tests (80% coverage)
│   └── test_orders.py   # Order tests (80% coverage)
├── requirements.txt
├── pytest.ini
└── README.md
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn app.main:app --reload

# Visit API docs
open http://localhost:8000/docs
```

## Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term

# View coverage report
open htmlcov/index.html
```

## Endpoints

### Products
- `POST /products/` - Create product
- `GET /products/` - List all products
- `GET /products/{product_id}` - Get product by ID
- `PUT /products/{product_id}` - Update product
- `DELETE /products/{product_id}` - Delete product

### Orders
- `POST /orders/` - Create order
- `GET /orders/` - List all orders
- `GET /orders/{order_id}` - Get order by ID
- `PUT /orders/{order_id}/status` - Update order status
- `DELETE /orders/{order_id}` - Cancel order

## Expected Coverage

With manual tests included:
- **Initial Coverage:** 80-85%
- **After AI generation:** Should reach 90%+ in 2-3 iterations

## Testing AI Test Generation

This project is designed to validate multi-iteration test generation systems:

```bash
# 1. Run manual tests to get baseline
pytest tests/ --cov=app --cov-report=xml --cov-report=html

# 2. Run coverage gap analyzer
python src/coverage_gap_analyzer.py --target ./app --current-dir . --output coverage_gaps.json

# 3. Run multi-iteration orchestrator
python multi_iteration_orchestrator.py --target ./app --iterations 3 --target-coverage 90
```

## Why This Project?

- ✅ **No auth complexity** - No API keys, no JWT, no OAuth
- ✅ **No middleware** - Simple request/response flow
- ✅ **Clean code** - Easy to understand and test
- ✅ **Realistic** - Real-world CRUD operations
- ✅ **Well-tested** - 80%+ manual test coverage
- ✅ **Small** - ~400 lines, easy to debug

## License

MIT
