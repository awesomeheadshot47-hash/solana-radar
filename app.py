"""Mobile-first research dashboard. No wallets or trades."""
import json
import sqlite3
import streamlit as st
from radar import connect, scan

st.set_page_config(page_title='Solana Radar', page_icon='🛰️', layout='wide')
st.markdown('''<style>
.block-container {padding-top:1.4rem;max-width:1100px}
[data-testid="stMetric"] {border:1px solid #334155;border-radius:12px;padding:12px}
@media(max-width:640px){.block-container{padding-left:1rem;padding-right:1rem}}
</style>''', unsafe_allow_html=True)
st.title('🛰️ Solana Radar')
st.caption('Research dashboard • Public DexScreener token profiles • No trading or buy signals')
st.warning('Coverage is incomplete: recently listed profiles are NOT every newly minted Solana token. Risk checks are preliminary and do not establish safety.')

with st.sidebar:
    st.header('Controls')
    limit = st.slider('Profiles per scan', 5, 30, 15, 5)
    st.caption('A manual scan requests live public data. Hosting and API rate limits apply.')
    st.caption('No wallet connection, private keys, or automated trading.')

if st.button('🔄 Scan recent Solana profiles', type='primary', use_container_width=True):
    with st.spinner('Fetching public profiles and pair data...'):
        try:
            db = connect()
            scan(db, limit=limit)
            db.close()
            st.success('Scan completed. Results updated below.')
        except Exception as exc:
            st.error(f'Scan could not complete: {exc}')

try:
    db = connect()
    obs = db.execute('''SELECT o.token,o.observed_at,o.created_at,o.liquidity_usd,o.volume_h1,
      o.txns_h1,o.narrative,o.risk_flags,o.price_usd,o.pair,o.token_name,o.token_symbol,o.token_icon
      FROM observations o JOIN (SELECT token,MAX(id) AS id FROM observations GROUP BY token) latest
      ON o.id=latest.id ORDER BY o.id DESC LIMIT 100''').fetchall()
    alerts = db.execute('SELECT observed_at,token,message FROM alerts ORDER BY id DESC LIMIT 30').fetchall()
    samples = db.execute('SELECT COUNT(*),COUNT(DISTINCT token) FROM observations').fetchone()
    db.close()
except sqlite3.Error as exc:
    st.error(f'Database error: {exc}')
    st.stop()

c1,c2,c3=st.columns(3)
c1.metric('Profiles recorded', samples[1]); c2.metric('Observations', samples[0]); c3.metric('New-profile alerts',len(alerts))
tab1,tab2,tab3=st.tabs(['Discoveries','Alerts','Methods'])
with tab1:
    if not obs:
        st.info('No observations yet. Tap “Scan recent Solana profiles” to begin.')
    for token, observed, created, liq, vol, txns, theme, flags, price, pair, name, symbol, icon in obs:
        flags=json.loads(flags or '[]')
        with st.expander(f'{name or "Name unavailable"} ({symbol or "?"}) · {theme or "Unclassified"}'):
            if icon and isinstance(icon, str) and icon.startswith('https://'):
                st.image(icon, width=72)
            st.write(f'**Name:** {name or "Unavailable"}  |  **Ticker:** {symbol or "Unavailable"}')
            st.caption('Names, symbols and logos are third-party metadata and may be misleading or missing.')
            a,b=st.columns(2)
            a.metric('Liquidity (observed)', f'${liq:,.0f}' if liq is not None else 'Unknown')
            b.metric('1h volume', f'${vol:,.0f}' if vol is not None else 'Unknown')
            st.write(f'**Observed (UTC):** {observed}')
            st.write(f'**Pair created (ms epoch):** {created if created else "Unknown"}')
            st.write(f'**1h transactions:** {txns} (may be unavailable)')
            st.write('**Risk and data limitations:**')
            for flag in flags: st.write('• '+flag)
            st.code(token, language=None)
            st.link_button('View token on DexScreener',f'https://dexscreener.com/solana/{token}')
with tab2:
    st.caption('New-profile discovery alerts appear here after a manual scan. Push notifications are not configured.')
    for when, token, msg in alerts:
        st.info(f'{when} UTC · {token[:7]}…{token[-5:]}\n\n{msg}')
with tab3:
    st.markdown('''**Data:** DexScreener public latest-token-profiles and token-pairs endpoints.

**Narrative:** Basic keyword classification from available profile text/links. This is *not* AI analysis of X, Telegram, or social sentiment.

**Risk:** Low/missing liquidity and incomplete pair information. Holder concentration, mint/freeze authority, wallet clusters and Token-2022 extensions are **not yet checked**.

**Backtesting:** Not implemented. Stored snapshots support future evaluation, but they cannot establish prediction accuracy.

**Hosting:** Streamlit Community Cloud may sleep, and local SQLite storage may reset after redeployment. For persistent monitoring use managed database and an independently scheduled collector.

**Safety:** No buy/sell recommendations, no wallet integration, and no order execution.''')
