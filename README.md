# AWS Cost Optimization Tool

A comprehensive Python-based tool for monitoring and optimizing AWS resource costs. This application analyzes your AWS infrastructure to identify idle resources, calculate potential savings, and provide actionable recommendations for cost reduction.

## Features

- **Multi-Service Support**: Analyzes EC2, RDS, EBS, and S3 resources
- **Idle Resource Detection**: Identifies underutilized resources based on CPU, memory, network, and I/O metrics
- **Cost Analysis**: Calculates potential savings from resource optimization
- **Interactive Dashboard**: Streamlit-based web interface for visualizing cost optimization opportunities
- **CLI Support**: Command-line interface for automation and scripting
- **Multi-Database Support**: Works with PostgreSQL, MySQL, Oracle, MSSQL, and SQLite
- **Docker Ready**: Fully containerized deployment with Docker Compose
- **Multi-Environment**: Support for multiple AWS accounts/environments (Green/Red)

## Architecture

```
├── main.py                 # Application entry point
├── core/                   # Core configuration and utilities
│   ├── config.py          # Configuration management
│   ├── constants.py       # Application constants
│   └── logger.py          # Logging utilities
├── analysis/              # Analysis modules
│   ├── cost_calculator.py # Cost calculation logic
│   ├── idle_analyzer.py   # Idle resource detection
│   └── metrics_analyzer.py# Metrics analysis
├── services/              # AWS service managers
│   ├── ec2_manager.py     # EC2 operations
│   ├── rds_manager.py     # RDS operations
│   ├── ebs_manager.py     # EBS operations
│   └── s3_manager.py      # S3 operations
├── etl/                   # ETL pipeline
│   ├── orchestrator.py    # ETL orchestration
│   ├── data_provider.py   # Data fetching
│   └── pricing_loader.py  # Pricing data loader
├── database/              # Database layer
│   ├── client.py          # Database client
│   ├── models.py          # SQLAlchemy models
│   └── migrations/        # Database migrations
├── ui/                    # User interfaces
│   ├── dashboard.py       # Streamlit dashboard
│   ├── cli.py             # CLI interface
│   └── charts.py          # Chart components
└── utils/                 # Utility modules
    ├── validators.py      # Input validation
    ├── alerting.py        # Alerting system
    └── rate_limiter.py    # API rate limiting
```

## Prerequisites

- Python 3.9+
- AWS Account with appropriate IAM permissions
- Database (PostgreSQL recommended for production)

## Installation

### Option 1: Local Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd COST-OPTIMISATION-AWS
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Run the application**
   ```bash
   # Dashboard mode
   streamlit run main.py
   
   # CLI mode
   python main.py --service rds --check-all
   ```

### Option 2: Docker Deployment

1. **Configure environment**
   ```bash
   cp .env.docker.example .env.docker
   # Edit .env.docker with your configuration
   ```

2. **Build and run**
   ```bash
   docker-compose up -d
   ```

3. **Access the application**
   - Dashboard: http://localhost:8501
   - pgAdmin: http://localhost:5050
   - ngrok: http://localhost:4040

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLAlchemy connection string | SQLite |
| `AWS_ACCESS_KEY_ID` | AWS Access Key | - |
| `AWS_SECRET_ACCESS_KEY` | AWS Secret Key | - |
| `AWS_DEFAULT_REGION` | AWS Region | `us-east-1` |
| `PRICING_JSON_DIR` | Directory for pricing data | `./pricing` |

### Multi-Environment Setup

The tool supports multiple AWS environments:

- **Default**: Primary AWS account
- **Green**: Secondary environment (e.g., development)
- **Red**: Tertiary environment (e.g., production)

Configure additional environments using:
- `AWS_GREEN_ACCESS_KEY_ID`
- `AWS_GREEN_SECRET_ACCESS_KEY`
- `AWS_RED_ACCESS_KEY_ID`
- `AWS_RED_SECRET_ACCESS_KEY`

## Usage

### Dashboard Mode

Launch the interactive Streamlit dashboard:

```bash
streamlit run main.py
```

Features:
- Resource overview and cost summary
- Idle resource identification
- Cost optimization recommendations
- Historical trend analysis
- Multi-environment comparison

### CLI Mode

Run analysis from command line:

```bash
# Check all RDS instances
python main.py --service rds --check-all

# Check specific EC2 instance
python main.py --service ec2 --instance-id i-1234567890abcdef0

# Analyze S3 buckets
python main.py --service s3 --analyze
```

### ETL Pipeline

Run the ETL pipeline to fetch and process AWS data:

```bash
# Full ETL run
python -m etl.orchestrator

# Specific service
python -m etl.orchestrator --service rds
```

## Idle Resource Detection

The tool analyzes multiple metrics to identify idle resources:

### RDS Instances
- CPU Utilization (< 5% average)
- Database Connections (0 active)
- Read/Write IOPS (minimal activity)
- Network Throughput (low traffic)
- Last connection activity

### EC2 Instances
- CPU Utilization (< 5% average)
- Network I/O (minimal traffic)
- Disk I/O (minimal activity)
- Instance state and uptime

### EBS Volumes
- IOPS activity
- Throughput metrics
- Attachment status
- Volume type and size

### S3 Buckets
- Request frequency
- Object lifecycle
- Storage class optimization
- Access patterns

## Cost Calculation

The tool calculates potential savings based on:

- **On-demand pricing**: Current AWS pricing
- **Reserved Instance recommendations**: For stable workloads
- **Right-sizing suggestions**: Based on utilization
- **Storage optimization**: Tiered storage recommendations

## Database Support

The application supports multiple database backends:

| Database | Connection String Format |
|----------|-------------------------|
| PostgreSQL | `postgresql://user:pass@host:port/db` |
| MySQL | `mysql+pymysql://user:pass@host:port/db` |
| Oracle | `oracle+oracledb://user:pass@host:port/db` |
| MSSQL | `mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+17+for+SQL+Server` |
| SQLite | `sqlite:///path/to/database.db` |

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_cost_calculator.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

## Security

### IAM Permissions

Minimum required IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "rds:Describe*",
        "rds:ListTagsForResource",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics",
        "s3:ListAllMyBuckets",
        "s3:GetBucket*",
        "pricing:GetProducts"
      ],
      "Resource": "*"
    }
  ]
}
```

### Best Practices

- Use IAM roles instead of access keys when possible
- Rotate credentials regularly
- Use least-privilege permissions
- Enable CloudTrail for audit logging

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Verify DATABASE_URL format
   - Check network connectivity
   - Ensure database user has required permissions

2. **AWS API Throttling**
   - The tool includes built-in rate limiting
   - Adjust `MAX_CONCURRENT_WORKERS` in config if needed

3. **Missing Pricing Data**
   - Ensure pricing JSON files are present
   - Run pricing loader: `python -m etl.pricing_loader`

### Logs

Logs are stored in the `logs/` directory:
- `app.log`: Application logs
- `etl.log`: ETL pipeline logs
- `error.log`: Error logs

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- AWS SDK for Python (boto3)
- Streamlit for the dashboard framework
- Plotly for interactive visualizations
- SQLAlchemy for database abstraction
