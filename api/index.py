import sys
import os

# Ensure root folder is on Python module path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard import app
