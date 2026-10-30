import json, os, sys
try:
    import MetaTrader5 as mt5
except Exception as e:
    print(json.dumps({'ok': False, 'stage': 'import', 'error': str(e)})); sys.exit(2)
login = int(os.getenv('XM_LOGIN', '0'))
password = os.getenv('XM_PASSWORD', '')
server = os.getenv('XM_SERVER', '')
if not login or not password or not server:
    print(json.dumps({'ok': False, 'stage': 'config', 'error': 'XM_LOGIN, XM_PASSWORD and XM_SERVER are required'})); sys.exit(2)
initialized = mt5.initialize(login=login, password=password, server=server, timeout=60000)
if not initialized:
    print(json.dumps({'ok': False, 'stage': 'initialize', 'error': str(mt5.last_error())})); sys.exit(3)
try:
    a = mt5.account_info()
    t = mt5.terminal_info()
    if a is None:
        print(json.dumps({'ok': False, 'stage': 'account_info', 'error': str(mt5.last_error())})); sys.exit(4)
    if int(a.trade_mode) != int(mt5.ACCOUNT_TRADE_MODE_DEMO) or int(a.login) != login or str(a.server) != server:
        print(json.dumps({'ok': False, 'stage': 'safety', 'error': 'Not the configured demo account; trading disabled'})); sys.exit(5)
    if not mt5.symbol_select('EURUSD', True):
        print(json.dumps({'ok': False, 'stage': 'symbol_select', 'error': str(mt5.last_error())})); sys.exit(6)
    tick = mt5.symbol_info_tick('EURUSD')
    if tick is None:
        print(json.dumps({'ok': False, 'stage': 'tick', 'error': str(mt5.last_error())})); sys.exit(7)
    print(json.dumps({'ok': True, 'stage': 'connected_demo', 'login': int(a.login), 'server': str(a.server), 'balance': float(a.balance), 'currency': str(a.currency), 'symbol': 'EURUSD', 'bid': float(tick.bid), 'ask': float(tick.ask), 'terminal_connected': bool(t.connected) if t else None, 'trading_enabled': False}))
finally:
    mt5.shutdown()
