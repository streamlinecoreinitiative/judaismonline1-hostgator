import datetime
import subprocess

COMMANDS = [
    ['python', 'daily_post.py'],
    ['python', 'freeze.py'],
]

def run(cmd):
    print('Running:', ' '.join(cmd))
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    for cmd in COMMANDS:
        run(cmd)
    run(['git', 'add', 'docs'])
    msg = f"Update site {datetime.date.today().isoformat()}"
    run(['git', 'commit', '-m', msg])
    run(['git', 'push'])

