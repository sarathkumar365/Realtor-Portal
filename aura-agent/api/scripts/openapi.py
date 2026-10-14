"""Print the API's OpenAPI document, for the admin app's generated types.

Run from aura-agent/api/ (it reads .env like the service does):

    .venv/bin/python scripts/openapi.py > openapi.json
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

print(json.dumps(app.openapi(), indent=1))
