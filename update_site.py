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
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    for cmd in COMMANDS:
        run(cmd)
    print("Site content updated locally.")

