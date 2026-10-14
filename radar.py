#!/usr/bin/env python3
"""Research-only Solana token profile monitor. Standard library only."""
import argparse, datetime as dt, json, os, sqlite3, time, urllib.request, urllib.error
from pathlib import Path

BASE = 'https://api.dexscreener.com'
DB = Path(__file__).with_name('radar.sqlite3')
USER_AGENT = 'SolanaRadarResearch/0.1'

def fetch(path):
    req = urllib.request.Request(BASE + path, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)

def connect():
    db = sqlite3.connect(DB)
    db.execute('''CREATE TABLE IF NOT EXISTS observations (
        id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, token TEXT NOT NULL,
        pair TEXT, created_at INTEGER, liquidity_usd REAL, volume_h1 REAL,
        txns_h1 INTEGER, price_usd REAL, fdv REAL, narrative TEXT,
        risk_flags TEXT, source TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS obs_token_time ON observations(token, observed_at)')
    db.execute('''CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY, observed_at TEXT, token TEXT, message TEXT)''')
    for name in ('token_name', 'token_symbol', 'token_icon'):
        try:
            db.execute(f'ALTER TABLE observations ADD COLUMN {name} TEXT')
        except sqlite3.OperationalError:
            pass
    db.commit()
    return db

def narrative(profile):
    text = ' '.join(str(profile.get(k) or '') for k in ('description', 'url'))
    text += ' ' + ' '.join(str(x.get('url') or '') for x in profile.get('links', []) if isinstance(x, dict))
    text = text.lower()
    groups = {'AI': ('artificial intelligence', ' ai ', 'agent'),
              'Animal': ('dog', 'cat', 'frog', 'penguin', 'monkey'),
              'Political': ('president', 'election', 'politic'),
              'Gaming': ('game', 'gaming', 'gamer')}
    return ', '.join(k for k, terms in groups.items() if any(t in ' '+text+' ' for t in terms)) or 'Unclassified'

def pair_data(token):
    try:
        payload = fetch('/token-pairs/v1/solana/' + token)
    except (urllib.error.URLError, ValueError) as exc:
        print(f'  Pair lookup unavailable for {token[:10]}: {exc}')
        return None
    pairs = payload if isinstance(payload, list) else []
    return max(pairs, key=lambda p: float((p.get('liquidity') or {}).get('usd') or 0), default=None)

def assess(pair):
    if not pair:
        return ['No pair data available; risk unknown']
    flags = []
    liq = (pair.get('liquidity') or {}).get('usd')
    if liq is None:
        flags.append('Liquidity unavailable')
    elif float(liq) < 10000:
        flags.append('Low observed liquidity (<$10k)')
    if not pair.get('pairCreatedAt'):
        flags.append('Pair creation time unavailable')
    if not pair.get('txns'):
        flags.append('Transaction data unavailable')
    flags.append('Mint authority, holder concentration and Token-2022 permissions NOT checked')
    return flags

def scan(db, limit=20):
    profiles = fetch('/token-profiles/latest/v1')
    if not isinstance(profiles, list):
        raise ValueError('Unexpected token profiles API response')
    profiles = [p for p in profiles if p.get('chainId') == 'solana' and p.get('tokenAddress')][:limit]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    count = 0
    for p in profiles:
        token = p['tokenAddress']
        exists = db.execute('SELECT 1 FROM observations WHERE token=? LIMIT 1', (token,)).fetchone()
        pair = pair_data(token)
        flags = assess(pair)
        tx = (pair or {}).get('txns') or {}
        h1 = tx.get('h1') or {}
        liquidity = (pair or {}).get('liquidity') or {}
        volume = (pair or {}).get('volume') or {}
        base = (pair or {}).get('baseToken') or {}
        quote = (pair or {}).get('quoteToken') or {}
        identity = base if base.get('address') == token else quote if quote.get('address') == token else {}
        info = (pair or {}).get('info') or {}
        icon = info.get('imageUrl') or p.get('icon')
        db.execute('''INSERT INTO observations
            (observed_at,token,pair,created_at,liquidity_usd,volume_h1,txns_h1,price_usd,fdv,narrative,risk_flags,source,token_name,token_symbol,token_icon)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (now,token,(pair or {}).get('pairAddress'),(pair or {}).get('pairCreatedAt'),
             liquidity.get('usd'),volume.get('h1'),int(h1.get('buys') or 0)+int(h1.get('sells') or 0),
             float((pair or {}).get('priceUsd') or 0) or None,(pair or {}).get('fdv'),
             narrative(p),json.dumps(flags),'DexScreener public API',identity.get('name'),identity.get('symbol'),icon))
        if not exists:
            msg = f'NEW PROFILE {token} | narrative={narrative(p)} | flags={"; ".join(flags)}'
            print('[RESEARCH ALERT]', msg)
            db.execute('INSERT INTO alerts (observed_at,token,message) VALUES (?,?,?)',(now,token,msg))
        count += 1
    db.commit()
    print(f'Observed {count} Solana profiles at {now}. These are listed profiles, NOT all new mints.')

def report(db):
    rows = db.execute('''SELECT token, MAX(observed_at), COUNT(*), MAX(liquidity_usd), MAX(volume_h1)
        FROM observations GROUP BY token ORDER BY MAX(observed_at) DESC LIMIT 25''').fetchall()
    if not rows: print('No observations yet. Run: python radar.py scan')
    for token, last, n, liq, vol in rows:
        print(f'{token} | last={last} | samples={n} | max_liq=${liq or 0:,.0f} | max_h1_volume=${vol or 0:,.0f}')

def backtest(db):
    # Coverage diagnostic only; never claim predictive accuracy from these samples.
    total = db.execute('SELECT COUNT(DISTINCT token) FROM observations').fetchone()[0]
    repeated = db.execute('SELECT COUNT(*) FROM (SELECT token FROM observations GROUP BY token HAVING COUNT(*)>=2)').fetchone()[0]
    print(f'Coverage: {total} distinct profiles; {repeated} have 2+ observations.')
    print('A valid predictive backtest requires timestamped historical launch universe, fixed outcome labels,')
    print('survivorship-bias controls and information-availability checks. Not implemented in this prototype.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Research-only Solana profile monitor (no trading)')
    parser.add_argument('command', choices=['scan','watch','report','backtest'])
    parser.add_argument('--limit', type=int, default=20, help='Maximum profiles checked per scan (1-30)')
    parser.add_argument('--interval', type=int, default=300, help='Watch interval in seconds (min 120)')
    args = parser.parse_args()
    db = connect()
    if args.command == 'report': report(db)
    elif args.command == 'backtest': backtest(db)
    else:
        while True:
            try: scan(db, max(1,min(args.limit,30)))
            except (urllib.error.URLError, ValueError, TimeoutError) as exc: print('Scan failed:',exc)
            if args.command == 'scan': break
            time.sleep(max(120,args.interval))
