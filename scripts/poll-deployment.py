"""Run from a systemd timer on the private demo server; no GitHub token needed."""
import json
import re
import subprocess
import urllib.request
from pathlib import Path

BASE = 'https://api.github.com/repos/codyssey-iumsae/IumOn'
ROOT = '/home1/ncloud/iumon'


def get(path):
    request = urllib.request.Request(BASE + path, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'iumon-deploy-poller',
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    sha = get('/commits/main')['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid commit SHA')
    marker = Path('/home1/ncloud/iumon-deployed-sha')
    if marker.exists() and marker.read_text().strip() == sha:
        return
    runs = get('/actions/workflows/repository-hygiene.yml/runs?branch=main&event=push&per_page=20')['workflow_runs']
    matching = [run for run in runs if run['head_sha'] == sha and run['head_repository']['full_name'] == 'codyssey-iumsae/IumOn']
    if not matching:
        return
    latest = max(matching, key=lambda run: (run['id'], run.get('run_attempt', 1)))
    if latest['status'] != 'completed' or latest['conclusion'] != 'success':
        return
    subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=ROOT, check=True, timeout=120)
    exists = subprocess.run(['git', 'cat-file', '-e', f'{sha}:scripts/deploy.sh'],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if exists.returncode != 0:
        print('Waiting for deployment scripts to be merged into main.')
        return
    script = subprocess.check_output(['git', 'show', f'{sha}:scripts/deploy.sh'], cwd=ROOT, timeout=30)
    subprocess.run(['bash', '-s', '--', sha], input=script, cwd=ROOT, check=True, timeout=1500)


if __name__ == '__main__':
    main()
