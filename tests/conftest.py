"""Shared test fixtures for DiskStat tests."""
import pytest


@pytest.fixture
def sample_tree():
    """Return a sample directory tree for testing."""
    return {
        "name": "root",
        "path": "/mnt/data",
        "size": 200,
        "category": "folder",
        "children": [
            {
                "name": "notes.txt",
                "path": "/mnt/data/notes.txt",
                "size": 100,
                "category": "doc",
            },
            {
                "name": "app",
                "path": "/mnt/data/app",
                "size": 100,
                "category": "folder",
                "children": [
                    {
                        "name": "main.py",
                        "path": "/mnt/data/app/main.py",
                        "size": 20,
                        "category": "code",
                    },
                ],
            },
        ],
    }
