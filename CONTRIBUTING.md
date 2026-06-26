# Contributing to diskstat

Thank you for contributing to this disk usage analysis tool!

## Development Setup

### Prerequisites
- Python 3.11+
- uv (recommended) or pip

### Setup
```bash
git clone https://github.com/stennu718/diskstat.git
cd diskstat
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Tests
```bash
pytest tests/ -v
```

### Linting
```bash
ruff check .
mypy diskstat/
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/description`)
3. Write tests for new functionality
4. Ensure all tests pass
5. Add type hints to new code
6. Commit with clear message
7. Open a Pull Request

## Code Style
- Python 3.11+ with type hints
- PEP 8, enforced by ruff
- Security-first approach (no shell=True, proper escaping)
- All new features must include tests
