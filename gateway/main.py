from fastapi import FastAPI, WebSocket, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import os, json, asyncio, random, time
import asyncpg
import redis.asyncio as aioredis

APP_ENV = os.getenv("APP_ENV", "dev")
DB_URL = os.getenv("DB_URL")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "11111111-1111-1111-1111-111111111111")

app = FastAPI(title="Markets Gateway", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

class IndicatorResp(BaseModel):
    symbol: str
    tf: str
    at: str
    data: Dict[str, float]

class Candle(BaseModel):
    ts: str; open: float; high: float; low: float; close: float; volume: float

class WatchlistResp(BaseModel):
    symbols: List[str]

class SummaryItem(BaseModel):
    symbol: str
    tf: str
    at: str
    data: Dict[str, float]
    direction: str
    score: float

@app.on_event("startup")
async def startup():
    app.state.db = await asyncpg.connect(dsn=DB_URL)
    try:
        await app.state.db.set_type_codec("json",  encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        await app.state.db.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    except Exception:
        pass
    app.state.redis = await aioredis.from_url(REDIS_URL)
    # تأكد من وجود ووتش ليست
    await app.state.db.execute(
        """INSERT INTO watchlists (user_id,name,symbols)
           SELECT $1,'Default','{}'::text[]
           WHERE NOT EXISTS (SELECT 1 FROM watchlists WHERE user_id=$1)""",
        DEFAULT_USER_ID
    )

@app.on_event("shutdown")
async def shutdown():
    await app.state.redis.close()
    await app.state.db.close()

@app.get("/health")
async def health():
    return {"ok": True, "env": APP_ENV}

# ---------- Indicators ----------
@app.get("/symbols/{symbol}/indicators", response_model=IndicatorResp)
async def get_indicators(symbol: str, tf: str = "1d", at: str = "latest"):
    key = f"ind:{symbol}:{tf}:{at}"
    cached = await app.state.redis.get(key)
    if cached: return json.loads(cached)

    row = await app.state.db.fetchrow(
        "SELECT ts, data FROM indicators WHERE symbol=$1 AND tf=$2 ORDER BY ts DESC LIMIT 1",
        symbol.upper(), tf
    )
    if not row: raise HTTPException(404, "No indicators")
    data = row["data"] if isinstance(row["data"], dict) else json.loads(row["data"])
    resp = IndicatorResp(symbol=symbol.upper(), tf=tf, at=row["ts"].isoformat(), data=data)
    await app.state.redis.setex(key, 30, json.dumps(resp.model_dump()))
    return resp

# ---------- Prices (for sparkline) ----------
@app.get("/symbols/{symbol}/prices", response_model=List[Candle])
async def get_prices(symbol: str, tf: str = "1d", limit: int = 200):
    rows = await app.state.db.fetch(
        """SELECT ts, open, high, low, close, volume
           FROM prices WHERE symbol=$1 AND tf=$2
           ORDER BY ts DESC LIMIT $3""",
        symbol.upper(), tf, limit
    )
    rows = list(reversed(rows))
    return [
        {"ts": r["ts"].isoformat(), "open": float(r["open"]), "high": float(r["high"]),
         "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["volume"])} for r in rows
    ]

# ---------- Watchlist endpoints ----------
@app.get("/watchlist", response_model=WatchlistResp)
async def get_watchlist():
    row = await app.state.db.fetchrow("SELECT symbols FROM watchlists WHERE user_id=$1 ORDER BY id ASC LIMIT 1", DEFAULT_USER_ID)
    syms = list(row["symbols"]) if row and row["symbols"] else []
    return {"symbols": [s.upper() for s in syms]}

class AddReq(BaseModel):
    symbol: str

@app.post("/watchlist", response_model=WatchlistResp)
async def add_symbol(req: AddReq):
    sym = req.symbol.upper().strip()
    if not sym: raise HTTPException(400, "Empty symbol")
    await app.state.db.execute(
        """UPDATE watchlists
           SET symbols = (SELECT ARRAY(SELECT DISTINCT s FROM unnest(symbols || $2::text[]) as s))
           WHERE user_id=$1 AND name='Default'""",
        DEFAULT_USER_ID, [sym]
    )
    return await get_watchlist()

@app.delete("/watchlist/{symbol}", response_model=WatchlistResp)
async def remove_symbol(symbol: str):
    sym = symbol.upper().strip()
    await app.state.db.execute(
        "UPDATE watchlists SET symbols = array_remove(symbols, $2) WHERE user_id=$1 AND name='Default'",
        DEFAULT_USER_ID, sym
    )
    return await get_watchlist()

# ---------- Summary (direction + score) ----------
@app.get("/summary", response_model=List[SummaryItem])
async def summary(tf: str = "1d"):
    row = await app.state.db.fetchrow("SELECT symbols FROM watchlists WHERE user_id=$1 ORDER BY id ASC LIMIT 1", DEFAULT_USER_ID)
    syms = list(row["symbols"]) if row and row["symbols"] else []
    out = []
    for s in syms:
        r = await app.state.db.fetchrow(
            "SELECT ts, data FROM indicators WHERE symbol=$1 AND tf=$2 ORDER BY ts DESC LIMIT 1",
            s, tf
        )
        if not r: continue
        data = r["data"] if isinstance(r["data"], dict) else json.loads(r["data"])
        # نفس منطق التحليل لاشتقاق الاتجاه والسكور
        score = 0.0
        if data.get("ma50",0) > data.get("ma200",0): score += 0.4
        if data.get("rsi14",0) > 55:                 score += 0.3
        # ملاحظة: عامل الحجم/الاختراق يُحتسب في التحليل نفسه؛ هنا نكتفي بالمؤشرات
        direction = "up" if score>=0.6 else ("down" if score<=0.4 else "neutral")
        out.append({
            "symbol": s, "tf": tf, "at": r["ts"].isoformat(),
            "data": data, "direction": direction, "score": round(score,2)
        })
    return out

# ---------- WebSocket demo (ticks) ----------
@app.websocket("/ws/prices")
async def ws_prices(ws: WebSocket, symbols: str = Query(...), tf: str = "1m"):
    await ws.accept()
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    bases = {s: 100.0 + random.random()*10 for s in syms}
    try:
        while True:
            t = int(time.time()*1000)
            for s in syms:
                bases[s] += random.uniform(-0.2, 0.2)
                await ws.send_json({"t": t, "symbol": s, "price": round(bases[s], 2), "tf": tf})
            await asyncio.sleep(1.0)
    except Exception:
        try: await ws.close()
        except: pass

@app.get('/')
async def root():
    return {'ok': True, 'message': 'Markets Gateway running. See /health and /docs.'}

