"""Launch isolated public-demo processes using private, local configuration."""
import os
from pathlib import Path
import shutil
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / '.env')
load_dotenv(ROOT / '.local' / 'portal.env', override=True)
mode = sys.argv[1]
if mode == 'web':
    if not os.environ.get('DEMO_GATE_PASSWORD'):
        raise RuntimeError('Missing shared demo password')
    os.environ.update(DEMO_GATE_ENABLED='1', NEXT_BUILD_DIR='.next-public', API_ORIGIN='http://127.0.0.1:8001')
    node = shutil.which('node')
    os.execv(node, [node, str(ROOT / 'node_modules/next/dist/bin/next'), 'start', '--hostname', '127.0.0.1', '--port', '3001'])
elif mode == 'api':
    os.environ['DEMO_SECURE_COOKIES'] = '1'
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8001'])
else:
    raise RuntimeError('Expected web or api')
