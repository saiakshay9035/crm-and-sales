import os
import sys

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database import init_db

init_db()

from mangum import Mangum

from dashboard import app

handler = Mangum(app, lifespan="off")

