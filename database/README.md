# Database Module

This module provides database access for the AWS Cost Optimization Tool using SQLAlchemy ORM, compatible with Roll framework.

## Features

- **SQLAlchemy ORM**: Modern Python SQL toolkit and ORM
- **Async Support**: Full async/await support with aiosqlite
- **Multiple Database Support**: SQLite (development) and PostgreSQL (production)
- **Roll Compatible**: Works seamlessly with Roll framework
- **Migration Utilities**: Built-in tools for database initialization and migration

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Initialize Database

```bash
# Create tables
python database/migrations/migrate.py init

# Seed initial data
python database/migrations/migrate.py seed
```

## Usage

### Synchronous Usage

```python
from database import get_session, init_db
from database.models import RawInstance, EtlRun

# Initialize database (run once)
init_db()

# Query data
with get_session() as session:
    instances = session.query(RawInstance).filter_by(service_type='ec2').all()
    for instance in instances:
        print(f"Instance: {instance.instance_id}, Region: {instance.region}")
```

### Asynchronous Usage

```python
from database import get_async_session, init_db
from database.models import RawInstance
from sqlalchemy import select

# Initialize database (run once)
init_db()

# Query data asynchronously
async with get_async_session() as session:
    result = await session.execute(
        select(RawInstance).where(RawInstance.service_type == 'ec2')
    )
    instances = result.scalars().all()
```

### Using with Roll Framework

```python
from roll import Roll
from database import get_session, init_db
from database.models import RawInstance

app = Roll()

# Initialize database on startup
init_db()

@app.route('/instances')
async def list_instances(request, response):
    with get_session() as session:
        instances = session.query(RawInstance).all()
        response.json = {
            'instances': [
                {'id': i.instance_id, 'type': i.service_type}
                for i in instances
            ]
        }
```

## Configuration

Database connection is configured via environment variables:

```bash
# SQLite (default for development)
DATABASE_URL=sqlite:///./data/etl_database.db

# PostgreSQL (for production)
DATABASE_URL=postgresql://user:password@localhost:5432/aws_cost_db

# Environment
ENVIRONMENT=development  # or production
```

## Models

### EtlRun
Tracks ETL job execution history.

### RawInstance
Stores AWS resource instances (EC2, RDS, EBS).

### RawMetric
Stores CloudWatch metrics for instances.

### InstanceTag
Stores instance tags.

### DataFreshness
Tracks data freshness per service type.

### EtlLock
Manages ETL process locking.

### AnalysisCache
Caches analysis results for instances.

### AwsPricing
Stores AWS pricing data.

### EbsPricing
Stores EBS volume pricing data.

## Migration Commands

```bash
# Initialize database tables
python database/migrations/migrate.py init

# Reset database (drop and recreate all tables)
python database/migrations/migrate.py reset

# Seed initial data
python database/migrations/migrate.py seed

# Backup database
python database/migrations/migrate.py backup --path backup.db

# Migrate data from old database
python database/migrations/migrate.py migrate-data --old-db path/to/old.db

# Verify schema
python database/migrations/migrate.py verify
```

## Directory Structure

```
database/
├── __init__.py          # Module exports
├── client.py            # Database client and session management
├── models.py            # SQLAlchemy model definitions
├── README.md            # This file
└── migrations/
    └── migrate.py       # Migration utilities
```

## Development

### Adding New Models

1. Define the model in `models.py`:

```python
class NewModel(Base):
    __tablename__ = 'new_models'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

2. Export the model in `__init__.py`:

```python
from database.models import NewModel
```

3. Run migration to create the table:

```bash
python database/migrations/migrate.py init
```

### Running Tests

```bash
python -m pytest tests/
```

## License

MIT License
