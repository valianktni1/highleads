"""Load the persistent application secret, then start the single-owner app."""
import os
import secrets
from pathlib import Path

secret_path = Path('/data/.app-secret')
if not secret_path.exists():
    try:
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'w') as handle:
            handle.write(secrets.token_urlsafe(48))
os.environ['APP_SECRET'] = secret_path.read_text().strip()

import uvicorn
uvicorn.run('app:app', host='0.0.0.0', port=8000, proxy_headers=False)
