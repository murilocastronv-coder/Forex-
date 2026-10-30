import json, os, subprocess
from flask import Flask, jsonify
app = Flask(__name__)
WIN_PYTHON = r'C:\\Python311\\python.exe'
@app.get('/')
def home():
    return jsonify({'service': 'MT5 Wine proof of concept', 'mode': 'connection-check-only', 'orders_enabled': False, 'status_endpoint': '/mt5-check'})
@app.get('/health')
def health():
    return jsonify({'ok': True, 'service': 'mt5-wine-poc', 'orders_enabled': False})
@app.get('/mt5-check')
def mt5_check():
    try:
        p = subprocess.run(['wine', WIN_PYTHON, '/app/mt5_probe.py'], capture_output=True, text=True, timeout=90, env=os.environ.copy())
        lines = [x for x in p.stdout.splitlines() if x.strip()]
        data = json.loads(lines[-1]) if lines else {'ok': False, 'stage': 'process', 'error': p.stderr[-1500:] or 'No probe output'}
        if p.stderr: data['diagnostic'] = p.stderr[-1000:]
        return jsonify(data), 200 if p.returncode == 0 and data.get('ok') else 503
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'stage': 'timeout', 'error': 'MT5 check exceeded 90 seconds'}), 504
    except Exception as e:
        return jsonify({'ok': False, 'stage': 'server', 'error': str(e)}), 500
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '10000')))
