# تحليل: يقرأ الووتش ليست من DB، يجلب أسعار (Tiingo/ccxt إن وُجدت مفاتيح)، يحسب مؤشرات وإشارات دورياً.
import os, json, asyncio, time, math
from datetime import datetime, timedelta, timezone
import asyncpg
import pandas as pd
import pandas_ta as ta
import requests
import ccxt
from apscheduler.schedulers.asyncio import AsyncIOScheduler

DB_URL = os.getenv("DB_URL")
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "11111111-1111-1111-1111-111111111111")
TIINGO_API_KEY = os.getenv("TIINGO_API_KEY", "").strip()
USE_TIINGO = os.getenv("USE_TIINGO", "0") == "1"
CRYPTO_EXCHANGES = [e.strip() for e in os.getenv("CRYPTO_EXCHANGES","coinbase,kraken").split(",") if e.strip()]

def log(msg): print(f"[analysis] {datetime.now().isoformat()} | {msg}", flush=True)

# ---------- Data fetchers ----------
def is_crypto(sym: str) -> bool:
    return "-" in sym and sym.upper().endswith("-USD")

def sym_to_ccxt(sym: str) -> str:
    # "BTC-USD" -> "BTC/USD"
    return sym.replace("-", "/")

def fetch_tiingo_daily(sym: str, start: datetime):
    if not TIINGO_API_KEY: return None
    url = f"https://api.tiingo.com/tiingo/daily/{sym}/prices"
    params = {"startDate": start.strftime("%Y-%m-%d"), "token": TIINGO_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200: return None
        arr = r.json()
        rows = []
        for a in arr:
            ts = datetime.fromisoformat(a["date"].replace("Z","+00:00"))
            open_, high, low, close, vol = a["open"], a["high"], a["low"], a["close"], a.get("volume", 0) or 0
            rows.append((ts, open_, high, low, close, vol))
        return rows
    except Exception:
        return None

def fetch_ccxt_daily(sym: str, limit=400):
    markets = []
    for exname in CRYPTO_EXCHANGES:
        try:
            ex = getattr(ccxt, exname)()
            pair = sym_to_ccxt(sym)
            if not ex.has.get("fetchOHLCV", False): continue
            ohlcv = ex.fetch_ohlcv(pair, timeframe="1d", limit=limit)  # [ms, o, h, l, c, v]
            rows = []
            for t,o,h,l,c,v in ohlcv:
                ts = datetime.fromtimestamp(t/1000, tz=timezone.utc)
                rows.append((ts, o,h,l,c, v or 0))
            if rows: return rows
        except Exception:
            continue
    return None

async def seed_for_symbol(conn, sym: str, days=320):
    # إن وُجد مزوّد فعّال استخدمه، وإلا ازرع صناعي
    start = datetime.now(timezone.utc) - timedelta(days=days)
    rows = None
    if is_crypto(sym):
        rows = fetch_ccxt_daily(sym, limit=days)
    elif USE_TIINGO:
        rows = fetch_tiingo_daily(sym, start=start)

    if rows is None:
        # صناعي
        base = 100.0; rows=[]
        for i in range(days):
            ts = start + timedelta(days=i)
            base *= (1 + (0.0015 * (1 if i%7!=0 else -1)))
            close = base
            open_ = close * 1.001
            high = max(open_, close) * 1.0025
            low  = min(open_, close) * 0.9975
            vol  = 1000 + (i%30)*12
            rows.append((ts, open_, high, low, close, vol))

    # اكتب إلى prices
    batch = [(sym, "provider", "1d", ts, o,h,l,c,v) for (ts,o,h,l,c,v) in rows]
    await conn.executemany(
        """INSERT INTO prices(symbol,venue,tf,ts,open,high,low,close,volume)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
           ON CONFLICT (symbol,tf,ts) DO NOTHING""",
        batch
    )

async def get_watchlist(conn):
    row = await conn.fetchrow(
        "SELECT symbols FROM watchlists WHERE user_id=$1 ORDER BY id ASC LIMIT 1",
        DEFAULT_USER_ID
    )
    syms = list(row["symbols"]) if row and row["symbols"] else []
    if not syms: syms = ["AAPL","NVDA","SPY","BTC-USD","ETH-USD"]
    return [s.upper() for s in syms]

async def fetch_df(conn, sym, tf="1d", lookback=500):
    rows = await conn.fetch(
      """SELECT ts, open, high, low, close, volume
         FROM prices WHERE symbol=$1 AND tf=$2
         ORDER BY ts DESC LIMIT $3""",
      sym, tf, lookback
    )
    if not rows: return None
    df = pd.DataFrame(rows, columns=["ts","open","high","low","close","volume"])
    df = df.sort_values("ts").set_index("ts")
    return df

def compute_indicators(df: pd.DataFrame):
    close = df["close"]; volume = df["volume"]
    return {
        "ma50":  float(ta.sma(close, length=50).iloc[-1]),
        "ma200": float(ta.sma(close, length=200).iloc[-1]),
        "rsi14": float(ta.rsi(close, length=14).iloc[-1]),
        "vol_sma20": float(ta.sma(volume, length=20).iloc[-1]),
    }

def direction_and_score(ind: dict, df: pd.DataFrame):
    score = 0.0
    if ind["ma50"] > ind["ma200"]: score += 0.4
    if ind["rsi14"] > 55:          score += 0.3
    if df["volume"].iloc[-1] > ind["vol_sma20"]: score += 0.2
    # اختراق 60 يوم بسيط
    if df["close"].iloc[-1] > df["high"].rolling(60).max().iloc[-2]: score += 0.2
    score = min(score, 1.0)
    if score >= 0.6: dir_ = "up"
    elif score <= 0.4: dir_ = "down"
    else: dir_ = "neutral"
    return dir_, score

async def compute_for_symbol(conn, sym, tf="1d"):
    df = await fetch_df(conn, sym, tf)
    if df is None or len(df) < 210:
        return
    ind = compute_indicators(df)
    ts = df.index[-1].to_pydatetime()
    await conn.execute(
      """INSERT INTO indicators(symbol, tf, ts, data)
         VALUES ($1,$2,$3,$4)
         ON CONFLICT (symbol,tf,ts) DO UPDATE SET data=EXCLUDED.data""",
      sym, tf, ts, json.dumps(ind)
    )
    dir_, score = direction_and_score(ind, df)
    detail = {"direction": dir_, "score": score}
    await conn.execute(
      """INSERT INTO signals(symbol, tf, ts, rule_id, fired, score, detail)
         VALUES ($1,$2,$3,'00000000-0000-0000-0000-000000000001',$4,$5,$6)
         ON CONFLICT DO NOTHING""",
      sym, tf, ts, score>=0.6, score, json.dumps(detail)
    )

async def initial_cycle(conn):
    syms = await get_watchlist(conn)
    for s in syms:
        cnt = await conn.fetchval("SELECT count(*) FROM prices WHERE symbol=$1 AND tf='1d'", s)
        if not cnt or cnt < 250:
            log(f"seeding {s} ...")
            await seed_for_symbol(conn, s)
        await compute_for_symbol(conn, s, "1d")

async def periodic_cycle():
    async with asyncpg.create_pool(dsn=DB_URL, min_size=1, max_size=4) as pool:
        async with pool.acquire() as conn:
            await initial_cycle(conn)

async def main():
    await periodic_cycle()
    from apscheduler.triggers.interval import IntervalTrigger
    sched = AsyncIOScheduler()
    sched.add_job(lambda: asyncio.create_task(periodic_cycle()), IntervalTrigger(minutes=5))
    sched.start()
    while True:
        await asyncio.sleep(3600)

if __name__=="__main__":
    asyncio.run(main())
