import datetime
import subprocess

import sys

COMMANDS = [
    [sys.executable, 'daily_post.py'],
    [sys.executable, 'update_news.py'],
    [sys.executable, 'freeze.py'],
]

def run(cmd):
    print('Running:', ' '.join(cmd))
    # Pasa el entorno actual (incluyendo NEWSDATA_API_KEY) a los subprocesos
    import os
    env = os.environ.copy()
    subprocess.run(cmd, check=True, env=env)

if __name__ == '__main__':
    for cmd in COMMANDS:
        run(cmd)
    print("Site content updated locally.")

