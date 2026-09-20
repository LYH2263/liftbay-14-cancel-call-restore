import { useEffect, useState } from "react";
import { api } from "../api/client";
type B = { id: number; name: string; floors: number };
type Call = { id: number; floor: number; direction: string; passengers: number; status: string; assigned_car_id: number | null; score: string };
const CANCELLABLE = new Set(["waiting", "assigned"]);
export default function CallsPage() {
  const [buildings, setBuildings] = useState<B[]>([]);
  const [rows, setRows] = useState<Call[]>([]);
  const [bid, setBid] = useState<number | "">("");
  const [floor, setFloor] = useState(5);
  const [dir, setDir] = useState("up");
  const [pax, setPax] = useState(1);
  const [err, setErr] = useState("");
  const reload = () => api<Call[]>("/calls").then(setRows);
  useEffect(() => {
    api<B[]>("/buildings").then(b => { setBuildings(b); if (b[0]) setBid(b[0].id); });
    reload();
  }, []);
  async function create() {
    setErr("");
    try {
      await api("/calls", { method: "POST", body: JSON.stringify({ building_id: bid, floor, direction: dir, passengers: pax }) });
      reload();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  async function cancel(c: Call) {
    if (!window.confirm(`取消呼梯 #${c.id}（${c.floor}F ${c.direction}，${c.passengers} 人）？`)) return;
    setErr("");
    try {
      await api(`/calls/${c.id}/cancel`, { method: "POST" });
      reload();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  return (<>
    <h2>呼梯</h2>
    <div className="toolbar">
      <select value={bid} onChange={e => setBid(Number(e.target.value))}>{buildings.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
      <input type="number" value={floor} onChange={e => setFloor(Number(e.target.value))} style={{ width: 72 }} />
      <select value={dir} onChange={e => setDir(e.target.value)}><option value="up">上行</option><option value="down">下行</option></select>
      <input type="number" value={pax} min={1} onChange={e => setPax(Number(e.target.value))} style={{ width: 64 }} />
      <button onClick={create}>登记呼梯</button>
    </div>
    {err && <div className="err">{err}</div>}
    <table className="table"><thead><tr><th>ID</th><th>楼层</th><th>方向</th><th>人数</th><th>状态</th><th>轿厢</th><th>评分</th><th>操作</th></tr></thead>
    <tbody>{rows.map(c => <tr key={c.id}><td>{c.id}</td><td className="mono">{c.floor}</td><td>{c.direction}</td><td>{c.passengers}</td><td>{c.status}</td><td>{c.assigned_car_id ?? "—"}</td><td className="mono">{c.score || "—"}</td>
      <td>{CANCELLABLE.has(c.status) ? <button className="btn-danger" onClick={() => cancel(c)}>取消</button> : "—"}</td></tr>)}</tbody></table>
  </>);
}
