import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
type Ind = { symbol: string; tf: string; at: string; data: Record<string, number> } | null;
type Candle = { ts: string; open: number; high: number; low: number; close: number; volume: number };
type SummaryItem = { symbol: string; tf: string; at: string; data: Record<string, number>; direction: "up"|"down"|"neutral"; score: number };
type WatchlistResp = { symbols: string[] };
const API = "http://localhost:8000";
async function safeJSON(res: Response) {
  if (!res.ok) return null;
  try { return await res.json(); } catch { return null; }
}
function Sparkline({ values }: { values: number[] }) {
  const width = 220, height = 56, pad = 4;
  const path = useMemo(() => {
    if (!values.length) return "";
    const min = Math.min(...values), max = Math.max(...values);
    const norm = (v: number) => (max===min) ? height/2 : pad + (height-2*pad) * (1 - (v-min)/(max-min));
    const step = (width - 2*pad) / (values.length - 1 || 1);
    let d = `M ${pad} ${norm(values[0])}`;
    values.forEach((v,i)=> d += ` L ${pad+i*step} ${norm(v)}`);
    return d;
  }, [values]);
  return <svg width={width} height={height}><path d={path} fill="none" stroke="currentColor" strokeWidth={2}/></svg>;
}
function DirectionBadge({ d }: { d: "up"|"down"|"neutral"}) {
  const map = { up: { c:"#16a34a", t:"↑ صعود" }, down: { c:"#dc2626", t:"↓ هبوط" }, neutral: { c:"#6b7280", t:"• حياد" } };
  return <span style={{background: map[d].c, color:"#fff", padding:"2px 8px", borderRadius:12, fontSize:12}}>{map[d].t}</span>;
}
function Card({ s, tf, onRemove }: { s: string; tf: "1d"|"4h"|"1h"; onRemove: (sym: string)=>void }) {
  const [ind, setInd] = useState<Ind>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  useEffect(()=> {
    let alive = true;
    (async ()=>{
      setLoading(true); setErr(null);
      const indRes = await fetch(`${API}/symbols/${s}/indicators?tf=${tf}`).then(safeJSON);
      const canRes = await fetch(`${API}/symbols/${s}/prices?tf=${tf}&limit=60`).then(safeJSON);
      if (!alive) return;
      if (!indRes) setErr("لا توجد مؤشرات بعد لهذا الرمز (قد يكون جديدًا).");
      setInd(indRes);
      setCandles(Array.isArray(canRes) ? canRes : []);
      setLoading(false);
    })().catch(() => { if (alive) { setErr("تعذّر جلب البيانات"); setLoading(false); }});
    return ()=> { alive = false; };
  }, [s, tf]);
  const closes = useMemo(()=> candles.map(c=>c.close), [candles]);
  const dir: "up"|"down"|"neutral" = useMemo(()=> {
    if(!ind || !ind.data) return "neutral";
    const {ma50, ma200, rsi14} = ind.data;
    let score = 0; if(ma50>ma200) score += 0.4; if(rsi14>55) score += 0.3;
    return score>=0.6? "up": (score<=0.4? "down":"neutral");
  }, [ind]);
  const fmt = (n?: number)=> n===undefined? "-" : n.toFixed(2);
  return (
    <div style={{border:"1px solid #eee", borderRadius:12, padding:14}}>
      <div style={{display:"flex", justifyContent:"space-between", alignItems:"center"}}>
        <strong style={{fontSize:18}}>{s}</strong>
        <div style={{display:"flex", gap:8, alignItems:"center"}}>
          <DirectionBadge d={dir}/>
          <button onClick={()=>onRemove(s)} style={{padding:"4px 10px", borderRadius:8, border:"1px solid #dc2626", background:"#dc2626", color:"#fff"}}>حذف</button>
        </div>
      </div>
      {loading ? <div style={{marginTop:8}}>جاري التحميل…</div> :
       err ? <div style={{marginTop:8, color:"#b45309", background:"#fef3c7", padding:8, borderRadius:8}}>
              {err} — جرّب انتظار دقيقة ثم تحديث الصفحة أو احذف الرمز إن لم يكن مدعومًا.
            </div> :
       <>
        <div style={{display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:8, marginTop:8}}>
          <div>MA50<br/><b>{fmt(ind?.data?.ma50)}</b></div>
          <div>MA200<br/><b>{fmt(ind?.data?.ma200)}</b></div>
          <div>RSI(14)<br/><b>{fmt(ind?.data?.rsi14)}</b></div>
          <div>Vol SMA20<br/><b>{fmt(ind?.data?.vol_sma20)}</b></div>
        </div>
        <div style={{marginTop:8, color:"#666", fontSize:12}}>آخر تحديث: {ind ? new Date(ind.at).toLocaleString() : "-"}</div>
        <div style={{marginTop:8, color:"#333"}}><Sparkline values={closes}/></div>
       </>
      }
    </div>
  );
}
function App() {
  const [wl, setWl] = useState<string[]>([]);
  const [newSym, setNewSym] = useState("");
  const [tf, setTf] = useState<"1d"|"4h"|"1h">("1d");
  const load = ()=> fetch(`${API}/watchlist`).then(safeJSON).then(d=> setWl(d?.symbols || []));
  useEffect(()=> { load(); }, []);
  const runNow = async ()=> {
    await fetch(`${API}/jobs/run-analysis`, { method:"POST" });
    alert("تم إرسال أمر التحديث الفوري. انتظر ثواني ثم حدّث الصفحة.");
  };
  const tgTest = async ()=> {
    const r = await fetch(`${API}/telegram/test`).then(safeJSON);
    if (r?.ok) alert("تم إرسال رسالة اختبار تيليغرام ✅");
    else alert("لم تُرسل رسالة. تأكد من TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID في .env");
  };
  const add = async ()=> {
    const sym = newSym.trim().toUpperCase();
    if(!sym) return;
    await fetch(`${API}/watchlist`, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({symbol:sym}) });
    setNewSym(""); load();
  };
  const remove = async (s: string)=> {
    await fetch(`${API}/watchlist/${s}`, { method:"DELETE" });
    load();
  };
  return (
    <div style={{fontFamily:"system-ui, sans-serif", padding:20, maxWidth:1100, margin:"0 auto"}}>
      <h2>لوحة متابعة — Markets MVP</h2>
      <div style={{display:"flex", gap:12, alignItems:"center", flexWrap:"wrap", marginBottom:12}}>
        <input value={newSym} onChange={e=>setNewSym(e.target.value)} placeholder="أضف رمزًا: AAPL أو BTC-USD" style={{padding:8, borderRadius:8, border:"1px solid #ddd"}}/>
        <button onClick={add} style={{padding:"8px 14px", borderRadius:8, border:"1px solid #10b981", background:"#10b981", color:"#fff"}}>إضافة</button>
        <button onClick={runNow} style={{padding:"8px 14px", borderRadius:8, border:"1px solid #2563eb", background:"#2563eb", color:"#fff"}}>تحديث المؤشرات الآن</button>
        <button onClick={tgTest} style={{padding:"8px 14px", borderRadius:8, border:"1px solid #0ea5e9", background:"#0ea5e9", color:"#fff"}}>اختبار تيليغرام</button>
        <select value={tf} onChange={e=>setTf(e.target.value as any)} style={{padding:8, borderRadius:8, border:"1px solid #ddd"}}>
          <option value="1d">TF: 1D</option>
          <option value="4h">TF: 4H (قريبًا)</option>
          <option value="1h">TF: 1H (قريبًا)</option>
        </select>
      </div>
      {wl.length===0 ? <div>أضف رموزًا لقائمة المتابعة…</div> :
        <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(280px, 1fr))", gap:12}}>
          {wl.map(s=> <Card key={s} s={s} tf={tf} onRemove={remove}/>)}
        </div>
      }
    </div>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
