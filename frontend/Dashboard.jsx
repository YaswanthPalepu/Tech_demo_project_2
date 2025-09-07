import { useEffect, useState } from "react";

export default function Dashboard() {
  const [data,setData]=useState(null);
  useEffect(()=>{ fetch("/dashboard/metrics").then(r=>r.json()).then(setData); },[]);
  if(!data) return <div>Loading…</div>;
  return (
    <div style={{fontFamily:"Inter, system-ui", padding:24}}>
      <h1>Test Metrics</h1>
      <div style={{display:"grid", gap:16, gridTemplateColumns:"repeat(3, 1fr)"}}>
        <Card title="Coverage" value={`${data.coverage}%`} />
        <Card title="Tests" value={data.tests} />
        <Card title="Failures" value={data.failures} />
      </div>
    </div>
  );
}

function Card({title,value}) {
  return <div style={{padding:16, borderRadius:12, boxShadow:"0 2px 10px rgba(0,0,0,.1)"}}>
    <div style={{opacity:.6}}>{title}</div>
    <div style={{fontSize:32, fontWeight:700}}>{value}</div>
  </div>;
}
