"""Pytest configuration: add src/ to sys.path for all test modules."""
import sys
import os

# Ensure every test file can import from src/ without any prefix
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
