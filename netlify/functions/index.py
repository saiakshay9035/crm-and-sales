import sys
import os

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database import init_db
init_db()

from dashboard import app
from mangum import Mangum

handler = Mangum(app, lifespan="off")

