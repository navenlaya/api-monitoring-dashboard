import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const apiBase = import.meta.env.VITE_API_BASE ?? "/api";
const demoToken = import.meta.env.VITE_DEMO_TRAFFIC_TOKEN ?? "";

function authHeader() {
  const t = localStorage.getItem("token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function tokenRole(token) {
  try {
    const [, payload] = token.split(".");
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return json.role || "";
  } catch {
    return "";
  }
}

async function apiGet(path) {
  const r = await fetch(`${apiBase}${path}`, { headers: { ...authHeader() } });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

export default function App() {
  const [username, setUsername] = useState("viewer");
  const [password, setPassword] = useState("viewer-change-me");
  const [token, setToken] = useState(() => localStorage.getItem("token") || "");
  const [error, setError] = useState("");
  const [windowMinutes, setWindowMinutes] = useState(15);
  const [serviceFilter, setServiceFilter] = useState("");
  const [services, setServices] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [series, setSeries] = useState([]);

  const loggedIn = Boolean(token);
  const role = token ? tokenRole(token) : "";
  const isAdmin = role === "admin";

  const login = async () => {
    setError("");
    try {
      const r = await fetch(`${apiBase}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(body || "login failed");
      }
      const data = await r.json();
      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken("");
  };

  const refresh = useCallback(async () => {
    if (!token) return;
    setError("");
    try {
      const q = new URLSearchParams();
      if (serviceFilter) q.set("service_name", serviceFilter);
      q.set("limit", "400");
      const metricsPath = `/metrics?${q.toString()}`;
      const [svc, al, sum, met] = await Promise.all([
        apiGet("/services"),
        apiGet("/alerts?resolved=false&limit=50"),
        apiGet(`/metrics/summary?window_minutes=${windowMinutes}`),
        apiGet(metricsPath),
      ]);
      setServices(svc.services || []);
      setAlerts(al || []);
      setSummary(sum);

      const buckets = new Map();
      for (const m of met) {
        const svcName = m.service_name;
        if (serviceFilter && svcName !== serviceFilter) continue;
        const t = new Date(m.timestamp).getTime();
        const bucket = Math.floor(t / 60000) * 60000;
        const key = `${svcName}:${bucket}`;
        const cur = buckets.get(key) || {
          ts: bucket,
          service_name: svcName,
          latSum: 0,
          n: 0,
          errors: 0,
        };
        cur.latSum += m.latency_ms;
        cur.n += 1;
        if (m.status_code >= 400) cur.errors += 1;
        buckets.set(key, cur);
      }
      const chart = [...buckets.values()]
        .sort((a, b) => a.ts - b.ts)
        .map((b) => ({
          t: new Date(b.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          avgLatency: Math.round(b.latSum / Math.max(1, b.n)),
          errorRate: Math.round((1000 * b.errors) / Math.max(1, b.n)) / 10,
        }));
      setSeries(chart);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, [token, serviceFilter, windowMinutes]);

  const startDemoTraffic = async () => {
    setError("");
    try {
      const r = await fetch(`${apiBase}/demo/traffic/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(demoToken ? { "X-Demo-Token": demoToken } : {}),
          ...authHeader(),
        },
        body: JSON.stringify({ seconds: 45, rps: 8, chaos_bias: 0.65 }),
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(body || `demo traffic failed (${r.status})`);
      }
      await refresh();
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  useEffect(() => {
    if (!token) return;
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [token, refresh]);

  const serviceOptions = useMemo(() => {
    const names = new Set(services.map((s) => s.service_name));
    (summary?.by_service || []).forEach((s) => names.add(s.service_name));
    return [...names].sort();
  }, [services, summary]);

  return (
    <div className="layout">
      <div className="topbar">
        <div>
          <h2 style={{ margin: 0 }}>API Monitoring</h2>
          <div className="muted">Latency, errors, alerts — production-style wiring</div>
        </div>
        {!loggedIn ? (
          <div className="row">
            <input value={username} onChange={(e) => setUsername(e.target.value)} />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button className="primary" onClick={login}>
              Login
            </button>
          </div>
        ) : (
          <div className="row">
            <span className="muted">JWT active</span>
            <button onClick={logout}>Logout</button>
          </div>
        )}
      </div>

      {error ? <div className="panel" style={{ borderColor: "#6b2f2f" }}>{error}</div> : null}

      {!loggedIn ? (
        <div className="panel muted">
          Use viewer (read-only) or admin. Defaults: viewer / viewer-change-me, admin / admin-change-me
          (set via env in Docker).
        </div>
      ) : null}

      {loggedIn ? (
        <>
          <div className="panel row">
            <label className="muted">
              Window
              <select
                value={windowMinutes}
                onChange={(e) => setWindowMinutes(Number(e.target.value))}
                style={{ marginLeft: 8 }}
              >
                {[5, 15, 30, 60].map((m) => (
                  <option key={m} value={m}>
                    {m} min
                  </option>
                ))}
              </select>
            </label>
            <label className="muted">
              Service
              <select
                value={serviceFilter}
                onChange={(e) => setServiceFilter(e.target.value)}
                style={{ marginLeft: 8 }}
              >
                <option value="">all</option>
                {serviceOptions.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary" onClick={refresh}>
              Refresh
            </button>
            {isAdmin || demoToken ? (
              <button onClick={startDemoTraffic}>Start 45s demo traffic</button>
            ) : null}
          </div>

          <div className="grid">
            {services.map((s) => (
              <div key={s.service_name} className="card">
                <div style={{ fontWeight: 700 }}>{s.service_name}</div>
                <div className={`status-${s.status}`}>{s.status}</div>
                <div className="muted" style={{ marginTop: 8 }}>
                  last: {s.last_metric_at || "—"}
                </div>
              </div>
            ))}
          </div>

          <div className="panel">
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Latency & error rate (1‑minute buckets)</div>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <LineChart data={series}>
                  <CartesianGrid stroke="#2a3140" strokeDasharray="3 3" />
                  <XAxis dataKey="t" stroke="#9aa4b2" />
                  <YAxis yAxisId="left" stroke="#9aa4b2" />
                  <YAxis yAxisId="right" orientation="right" stroke="#9aa4b2" />
                  <Tooltip contentStyle={{ background: "#111522", border: "1px solid #2a3140" }} />
                  <Line yAxisId="left" type="monotone" dataKey="avgLatency" dot={false} stroke="#5b8cff" name="avg latency (ms)" />
                  <Line yAxisId="right" type="monotone" dataKey="errorRate" dot={false} stroke="#ff6b6b" name="error rate %" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="panel">
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Active alerts</div>
            {alerts.length === 0 ? <div className="muted">No open alerts</div> : null}
            {alerts.map((a) => (
              <div key={a.id} className={`alert ${a.resolved ? "resolved" : ""}`}>
                <div style={{ fontWeight: 600 }}>
                  {a.service_name} · {a.alert_type}
                </div>
                <div className="muted">{a.message}</div>
              </div>
            ))}
          </div>

          <div className="panel">
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Summary ({windowMinutes}m)</div>
            <div className="muted" style={{ marginBottom: 8 }}>
              From <code>/metrics/summary</code> (Redis‑cached briefly)
            </div>
            <div className="grid">
              {(summary?.by_service || []).map((s) => (
                <div key={s.service_name} className="card">
                  <div style={{ fontWeight: 700 }}>{s.service_name}</div>
                  <div className="muted">requests: {s.request_count}</div>
                  <div className="muted">errors: {s.error_count}</div>
                  <div className="muted">avg latency: {Math.round(s.avg_latency_ms)} ms</div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
