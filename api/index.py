import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard import app

try:
    from mangum import Mangum
    handler = Mangum(app)
except Exception:
    handler = app

