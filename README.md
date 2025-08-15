# Markets MVP (Stocks + Crypto)
> إصدار MVP تعليمي. ليس نصيحة استثمارية.

## التشغيل السريع
1) انسخ `.env.example` إلى `.env`.
2) شغّل:
```bash
docker compose up --build
```
- واجهة API: http://localhost:8000/docs
- الواجهة الأمامية: http://localhost:5173
- WebSocket (تجريبي): ws://localhost:8000/ws/prices?symbols=AAPL,BTC-USD&tf=1m
