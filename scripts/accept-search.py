"""One sequential search check per channel; retain envelopes and a compact manifest."""
import argparse
import datetime
import json
import platform
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--cli', default='agent-reach')
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--channels', nargs='+', default=['github','twitter','youtube','bilibili','xiaohongshu','linkedin','boss','xueqiu','web'])
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
report = {'started': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'platform': platform.platform(), 'scope': 'search/jobs only', 'results': []}
for channel in args.channels:
    if not channel.replace('_','').isalnum():
        parser.error('invalid channel')
    command = [args.cli, 'check', channel, '--search', '--timeout', '120']
try:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=150, check=False)
    
    # 1. Si le CLI a échoué (ex: canal introuvable)
    if completed.returncode != 0:
        raise RuntimeError(f"CLI failed with code {completed.returncode}")
        
    # 2. Si le CLI n'a rien affiché
    if not completed.stdout.strip():
        raise ValueError("Empty stdout")
        
    # 3. Parser le JSON (on utilise strip() pour éviter les erreurs d'espaces)
    result = json.loads(completed.stdout.strip())
    
    # 4. Sécurité : s'assurer que le résultat est bien un dictionnaire avant de modifier
    if not isinstance(result, dict):
        result = {'ok': False, 'error': {'code': 'InvalidResultType'}}
        
    if completed.stderr:
        # Do not persist raw stderr: upstream may include browser URLs or credentials.
        result['stderr_present'] = True

except (ValueError, subprocess.TimeoutExpired, FileNotFoundError, RuntimeError) as exc:
    result = {'ok': False, 'error': {'code': type(exc).__name__}}
    (args.out / (channel+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    row = {'channel':channel,'ok':result.get('ok',False),'checks':result.get('results',[])}
    report['results'].append(row)
    (args.out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(row,ensure_ascii=False),flush=True)
report['finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
report['ok'] = all(r['ok'] for r in report['results'])
(args.out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if report['ok'] else 1)
