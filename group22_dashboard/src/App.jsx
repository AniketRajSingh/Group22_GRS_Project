import React, { useState, useEffect, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Line, Bar, Doughnut } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Title, Tooltip, Legend, Filler
);

import './App.css';

// ─── Colour tokens ─────────────────────────────────────────────────────────────
const C = {
  indigo: '#6366f1', indigoD: '#4f46e5',
  violet: '#8b5cf6',
  emerald: '#10b981', emeraldD: '#059669',
  amber: '#f59e0b',
  sky: '#0ea5e9',
  rose: '#f43f5e',
  pink: '#ec4899',
  slate: '#64748b', slateL: '#94a3b8', slateXL: '#f1f5f9',
};

// ─── Chart helpers ─────────────────────────────────────────────────────────────
function valToY(val, pMin, dRange, h, pad) {
  const y = h - pad - ((val - pMin) / dRange) * (h - 2 * pad);
  return Math.max(pad, Math.min(h - pad, y));
}
function buildPoints(data, key, pMin, dRange, w, h, pad) {
  if (!data || data.length < 1) return '';
  return data.map((d, i) => {
    const x = pad + (i / Math.max(1, data.length - 1)) * (w - 2 * pad);
    return `${x},${valToY(d[key] || 0, pMin, dRange, h, pad)}`;
  }).join(' ');
}

// ─── Single Sparkline ──────────────────────────────────────────────────────────
const LineChart = ({ data, dataKey, color, label, unit, isBadIfIncreasing = false }) => {
  const W = 300, H = 110, PAD = 20;
  const vals = data.map(d => d[dataKey] || 0);
  const minV = Math.min(...(vals.length ? vals : [0]));
  const maxV = Math.max(...(vals.length ? vals : [1]));
  const range = Math.max(1, maxV - minV);
  const pMin = Math.max(0, minV - range * 0.08);
  const pMax = maxV + range * 0.08;
  const dRange = Math.max(0.001, pMax - pMin);

  const latest = data.length > 0 ? data[data.length - 1][dataKey] : null;
  const prev = data.length > 1 ? data[data.length - 2][dataKey] : null;
  const rising = latest !== null && prev !== null && latest > prev;
  const trendColor = data.length >= 2 && latest !== prev
    ? (rising ? (isBadIfIncreasing ? C.rose : C.emerald) : (isBadIfIncreasing ? C.emerald : C.rose))
    : color;

  const pts = buildPoints(data, dataKey, pMin, dRange, W, H, PAD);

  return (
    <div className="chart-wrapper">
      <div className="chart-label">
        <span className="chart-label-text">{label}</span>
        <span className="chart-label-val" style={{ color: trendColor }}>
          {latest !== null ? `${latest.toFixed(1)}${unit}` : '—'}
          {latest !== null && prev !== null && (
            <span className="chart-arrow">{rising ? '▲' : latest < prev ? '▼' : '●'}</span>
          )}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="live-chart">
        {[0, 0.33, 0.66, 1].map(t => (
          <line key={t} x1={PAD} y1={PAD + (H - 2 * PAD) * t} x2={W - PAD} y2={PAD + (H - 2 * PAD) * t}
            stroke={C.slateXL} strokeWidth="1" />
        ))}
        {data.length > 1 && <polyline fill="none" stroke={trendColor} strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round" points={pts} className="chart-path" />}
        {data.length > 0 && (() => {
          const lx = PAD + ((data.length - 1) / Math.max(1, data.length - 1)) * (W - 2 * PAD);
          const ly = valToY(data[data.length - 1][dataKey] || 0, pMin, dRange, H, PAD);
          return <circle cx={lx} cy={ly} r="4" fill={trendColor} stroke="white" strokeWidth="1.5" className="chart-active-dot" />;
        })()}
      </svg>
      <div className="chart-range-row"><span>{pMin.toFixed(0)}</span><span>{pMax.toFixed(0)}</span></div>
    </div>
  );
};

// ─── Multi-latency Overlay ────────────────────────────────────────────────
const LatencyMultiChart = ({ data }) => {
  const W = 600, H = 140, PAD = 22;
  const LINES = [
    { key: 'lat', label: 'Mean', color: C.indigo },
    { key: 'p95', label: 'P95', color: C.amber },
    { key: 'p99', label: 'P99', color: C.rose },
  ];
  const allVals = data.flatMap(d => LINES.map(l => d[l.key] || 0)).filter(v => v > 0);
  const minV = Math.min(...(allVals.length ? allVals : [0]));
  const maxV = Math.max(...(allVals.length ? allVals : [1]));
  const range = Math.max(1, maxV - minV);
  const pMin = Math.max(0, minV - range * 0.08);
  const pMax = maxV + range * 0.12;
  const dRange = Math.max(0.001, pMax - pMin);

  return (
    <div className="chart-wrapper chart-wrapper-wide">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <span className="chart-label-text" style={{ fontSize: '0.75rem' }}>Latency Overlay — Mean / P95 / P99</span>
        <div style={{ display: 'flex', gap: '1.25rem' }}>
          {LINES.map(l => {
            const latest = data.length > 0 ? (data[data.length - 1][l.key] || 0) : null;
            return (
              <span key={l.key} style={{ fontSize: '0.72rem', fontWeight: 700, color: l.color, display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 14, height: 3, background: l.color, display: 'inline-block', borderRadius: 2 }}></span>
                {l.label}: {latest !== null ? `${latest.toFixed(0)}ms` : '—'}
              </span>
            );
          })}
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="live-chart" style={{ height: 120 }}>
        {[0, 0.25, 0.5, 0.75, 1].map(t => (
          <line key={t} x1={PAD} y1={PAD + (H - 2 * PAD) * t} x2={W - PAD} y2={PAD + (H - 2 * PAD) * t}
            stroke={C.slateXL} strokeWidth="1" />
        ))}
        <text x={PAD - 2} y={PAD + 4} fill={C.slateL} fontSize="9" textAnchor="end">{pMax.toFixed(0)}</text>
        <text x={PAD - 2} y={H - PAD + 4} fill={C.slateL} fontSize="9" textAnchor="end">{pMin.toFixed(0)}</text>
        {LINES.map(l => {
          const pts = buildPoints(data, l.key, pMin, dRange, W, H, PAD);
          if (!pts) return null;
          return <polyline key={l.key} fill="none" stroke={l.color} strokeWidth="2.5"
            strokeLinecap="round" strokeLinejoin="round" points={pts} opacity={l.key === 'lat' ? 1 : 0.85} />;
        })}
        {data.length > 0 && LINES.map(l => {
          const lx = PAD + ((data.length - 1) / Math.max(1, data.length - 1)) * (W - 2 * PAD);
          const ly = valToY(data[data.length - 1][l.key] || 0, pMin, dRange, H, PAD);
          return <circle key={l.key} cx={lx} cy={ly} r="4" fill={l.color} stroke="white" strokeWidth="1.5" />;
        })}
      </svg>
      <div className="chart-range-row">
        <span>ms</span>
        <span style={{ fontSize: '0.6rem', color: C.slateL }}>← last {data.length} samples</span>
      </div>
    </div>
  );
};

// ─── Success Rate Chart ─────────────────────────────────────────────────────────
const SuccessRateChart = ({ data }) => {
  const W = 300, H = 110, PAD = 20;
  const pMin = 0, pMax = 100, dRange = 100;
  const latest = data.length > 0 ? data[data.length - 1]['suc'] : null;
  const color = latest === null || latest >= 99 ? C.emerald : latest >= 95 ? C.amber : C.rose;
  const pts = buildPoints(data, 'suc', pMin, dRange, W, H, PAD);

  return (
    <div className="chart-wrapper" style={{ borderTop: `3px solid ${color}` }}>
      <div className="chart-label">
        <span className="chart-label-text">Success Rate</span>
        <span className="chart-label-val" style={{ color }}>{latest !== null ? `${latest.toFixed(1)}%` : '—'}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="live-chart">
        {[0, 0.33, 0.66, 1].map(t => (
          <line key={t} x1={PAD} y1={PAD + (H - 2 * PAD) * t} x2={W - PAD} y2={PAD + (H - 2 * PAD) * t}
            stroke={C.slateXL} strokeWidth="1" />
        ))}
        <line x1={PAD} y1={valToY(95, pMin, dRange, H, PAD)} x2={W - PAD} y2={valToY(95, pMin, dRange, H, PAD)}
          stroke={C.amber} strokeWidth="1" strokeDasharray="4,3" opacity="0.6" />
        {data.length > 1 && <polyline fill={`${color}18`} stroke={color} strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round" points={pts} />}
        {data.length > 0 && (() => {
          const lx = PAD + ((data.length - 1) / Math.max(1, data.length - 1)) * (W - 2 * PAD);
          const ly = valToY(data[data.length - 1]['suc'] || 0, pMin, dRange, H, PAD);
          return <circle cx={lx} cy={ly} r="4" fill={color} stroke="white" strokeWidth="1.5" />;
        })()}
      </svg>
      <div className="chart-range-row"><span>0%</span><span>100%</span></div>
    </div>
  );
};
// ─── Burden Compare Chart ───────────────────────────────────────────────────────
const BurdenCompareChart = ({ telemetry }) => {
  const W = 300, H = 110, PAD = 20;
  const nodes = Object.entries(telemetry).sort(([a], [b]) => a.localeCompare(b));

  const scores = nodes.map(([id, stats]) => {
    const cpu = stats.cpu_percent || 0;
    const memPct = ((stats.memory_mb || 0) / 2048) * 100;
    const busy = (stats.active_requests || 0) * 50;
    const val = (cpu * 0.4) + (memPct * 0.1) + busy;
    return { id: id.replace(/.*inference-/i, '').replace(':8000', '').toUpperCase(), val };
  });

  const pMin = 0;
  const maxVal = Math.max(10, ...scores.map(s => s.val));
  const pMax = maxVal * 1.2;
  const dRange = Math.max(0.1, pMax - pMin);

  const strongest = [...scores].sort((a, b) => a.val - b.val)[0];

  return (
    <div className="chart-wrapper">
      <div className="chart-label">
        <span className="chart-label-text">Burden Score</span>
        <span className="chart-label-val" style={{ color: C.violet, fontSize: '0.8rem' }}>
          {strongest ? `${strongest.id} Strongest` : '—'}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="live-chart">
        {[0, 0.5, 1].map(t => (
          <line key={t} x1={PAD} y1={PAD + (H - 2 * PAD) * t} x2={W - PAD} y2={PAD + (H - 2 * PAD) * t}
            stroke={C.slateXL} strokeWidth="1" />
        ))}
        {scores.map((s, i) => {
          const barW = (W - 2 * PAD) / Math.max(1, scores.length) - 10;
          const x = PAD + 5 + i * (barW + 10);
          const barH = (s.val / dRange) * (H - 2 * PAD);
          const y = H - PAD - barH;
          const isStrongest = s.val === strongest?.val;
          return (
            <g key={s.id}>
              <rect x={x} y={y} width={barW} height={barH} fill={isStrongest ? C.emerald : C.violet} rx="4" />
              <text x={x + barW / 2} y={H - PAD + 12} fontSize="10" fill={C.slateL} textAnchor="middle">{s.id}</text>
              <text x={x + barW / 2} y={y - 4} fontSize="9" fill={C.slate} textAnchor="middle" fontWeight="bold">{s.val.toFixed(1)}</text>
            </g>
          );
        })}
      </svg>
      <div className="chart-range-row"><span>0</span><span>{pMax.toFixed(0)}</span></div>
    </div>
  );
};

// ─── Chart.js Research Components ──────────────────────────────────────────
const STRATEGY_NORMALIZE = {
  'ha': 'HA', 'hardware-aware': 'HA', 'hardware_aware': 'HA',
  'rr': 'RR', 'round-robin': 'RR', 'round_robin': 'RR',
  'lc': 'LC', 'least-connection': 'LC', 'least_connection': 'LC',
  'hash': 'HS', 'hashing': 'HS', 'hs': 'HS',
};
const normalizeStrategy = (s) => STRATEGY_NORMALIZE[s?.toLowerCase()] || s?.toUpperCase() || '?';
const normalizeLoad = (l) => {
  const low = l?.toLowerCase();
  return low === 'normal' ? 'Normal' : low === 'stress' ? 'Stress' : l;
};

const ResearchBenchmarkChart = ({ results, theme }) => {
  const textColor = theme === 'dark' ? '#9ca3af' : '#475569';
  const gridColor = theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';

  // Group results by normalized strategy, deduplicate, pick latest per strategy+load
  const STRATEGIES = ['HA', 'RR', 'LC', 'HS'];
  const lookup = {};
  results.forEach(r => {
    const key = `${normalizeStrategy(r.strategy)}_${normalizeLoad(r.load)}`;
    lookup[key] = r; // last one wins (dedup)
  });

  const getData = (strat, load, field) => lookup[`${strat}_${load}`]?.[field] ?? null;

  const hasData = results.length > 0;

  const data = {
    labels: STRATEGIES,
    datasets: [
      {
        label: 'Mean Latency — Normal',
        data: STRATEGIES.map(s => getData(s, 'Normal', 'avg_latency')),
        borderColor: C.indigo, backgroundColor: C.indigo + '15',
        pointBackgroundColor: C.indigo, pointBorderColor: '#fff', pointRadius: 6, pointHoverRadius: 9,
        tension: 0.3, fill: true, borderWidth: 2.5, borderDash: [],
      },
      {
        label: 'Mean Latency — Stress',
        data: STRATEGIES.map(s => getData(s, 'Stress', 'avg_latency')),
        borderColor: C.rose, backgroundColor: C.rose + '15',
        pointBackgroundColor: C.rose, pointBorderColor: '#fff', pointRadius: 6, pointHoverRadius: 9,
        tension: 0.3, fill: true, borderWidth: 2.5, borderDash: [],
      },
      {
        label: 'P95 Latency — Normal',
        data: STRATEGIES.map(s => getData(s, 'Normal', 'p95_latency')),
        borderColor: C.emerald, backgroundColor: 'transparent',
        pointBackgroundColor: C.emerald, pointBorderColor: '#fff', pointRadius: 5, pointHoverRadius: 8,
        tension: 0.3, fill: false, borderWidth: 2, borderDash: [6, 3],
      },
      {
        label: 'P95 Latency — Stress',
        data: STRATEGIES.map(s => getData(s, 'Stress', 'p95_latency')),
        borderColor: C.amber, backgroundColor: 'transparent',
        pointBackgroundColor: C.amber, pointBorderColor: '#fff', pointRadius: 5, pointHoverRadius: 8,
        tension: 0.3, fill: false, borderWidth: 2, borderDash: [6, 3],
      },
    ]
  };

  const options = {
    responsive: true, maintainAspectRatio: false,
    spanGaps: true,
    plugins: {
      legend: { position: 'top', labels: { color: textColor, font: { size: 11, weight: 'bold' }, usePointStyle: true, pointStyle: 'circle', padding: 16 } },
      tooltip: { backgroundColor: 'rgba(0,0,0,0.88)', padding: 14, cornerRadius: 10, titleFont: { weight: 'bold', size: 13 }, bodyFont: { size: 12 } }
    },
    scales: {
      y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } }, title: { display: true, text: 'Latency (ms)', color: textColor, font: { size: 11, weight: 'bold' } }, beginAtZero: true },
      x: { grid: { color: gridColor + '50' }, ticks: { color: textColor, font: { size: 12, weight: '800' } } }
    },
    interaction: { mode: 'index', intersect: false },
  };

  return (
    <div className="glass-card" style={{ marginTop: '2rem' }}>
      <div className="card-header">
        <div>
          <h3 className="card-title">🔬 Strategy Performance Comparison</h3>
          <p className="card-sub">{hasData ? `${results.length} benchmarks · 4 strategies × Normal/Stress` : 'Run research suite to populate'}</p>
        </div>
      </div>
      <div style={{ height: 380 }}><Line data={data} options={options} /></div>
    </div>
  );
};

const LatencyHistogram = ({ data, theme }) => {
  const textColor = theme === 'dark' ? '#9ca3af' : '#475569';
  const gridColor = theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';
  const NUM_BINS = 15;

  // Compute dynamic bin size based on actual data range
  let maxLatency = 200; // default when no data
  if (data && data.length > 0) {
    maxLatency = Math.max(...data.map(d => d.latency_ms || 0), 200);
  }
  const binSize = Math.ceil(maxLatency / NUM_BINS / 10) * 10; // round to nearest 10
  const bins = new Array(NUM_BINS).fill(0);
  const labels = new Array(NUM_BINS).fill(0).map((_, i) => {
    const val = i * binSize;
    return val >= 1000 ? `${(val / 1000).toFixed(1)}s` : `${val}ms`;
  });

  if (data && data.length > 0) {
    data.forEach(d => {
      const binIdx = Math.min(Math.floor((d.latency_ms || 0) / binSize), NUM_BINS - 1);
      bins[binIdx]++;
    });
  }

  return <Line data={{ labels, datasets: [{
    label: 'Requests', data: bins,
    borderColor: C.emerald, backgroundColor: C.emerald + '20',
    pointBackgroundColor: C.emerald, pointBorderColor: '#fff', pointRadius: 2, pointHoverRadius: 5,
    tension: 0.35, fill: true, borderWidth: 2,
  }] }} options={{
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 9 } }, beginAtZero: true,
        title: { display: true, text: '# Requests', color: textColor, font: { size: 8 } } },
      x: { grid: { display: false }, ticks: { color: textColor, font: { size: 7 }, maxRotation: 45 },
        title: { display: true, text: 'Response Time', color: textColor, font: { size: 8 } } }
    }
  }} />;
};

const SuccessRateDoughnut = ({ data }) => {
  const ok = data ? data.filter(d => d.status === 200).length : 0;
  const err = data ? data.length - ok : 0;
  return <Doughnut data={{ labels: ['Success', 'Errors'], datasets: [{ data: data && data.length > 0 ? [ok, err] : [1, 0], backgroundColor: [data && data.length > 0 ? C.emerald : 'rgba(0,0,0,0.05)', C.rose], borderWidth: 0 }] }} options={{
    responsive: true, maintainAspectRatio: false, cutout: '70%',
    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } }
  }} />;
};

// ─── Node Configurator Panel ────────────────────────────────────────────────────
const NodeConfigurator = () => {
  const [sysInfo, setSysInfo] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [nodeCount, setNodeCount] = useState(3);
  const [deployStatus, setDeployStatus] = useState({ running: false, logs: [], success: null });
  const [error, setError] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const deployLogRef = useRef(null);

  // Fetch system info once
  useEffect(() => {
    fetch('/api/cluster-config').then(r => r.json()).then(data => {
      setSysInfo(data);
      // Init nodes from current config
      if (data.current_nodes && data.current_nodes.length > 0) {
        setNodes(data.current_nodes.map(n => ({ cpu: n.cpu, memory_mb: n.memory_mb })));
        setNodeCount(data.current_nodes.length);
      }
    }).catch(() => { });
  }, []);

  // Poll deploy status when running
  useEffect(() => {
    if (!deployStatus.running) return;
    const id = setInterval(() => {
      fetch('/api/deploy-status').then(r => r.json()).then(d => {
        setDeployStatus(d);
        if (!d.running) clearInterval(id);
      });
    }, 1500);
    return () => clearInterval(id);
  }, [deployStatus.running]);

  useEffect(() => {
    if (deployLogRef.current) deployLogRef.current.scrollTop = deployLogRef.current.scrollHeight;
  }, [deployStatus.logs]);

  // When nodeCount changes, resize nodes array
  useEffect(() => {
    setNodes(prev => {
      const next = [...prev];
      while (next.length < nodeCount) next.push({ cpu: 1.0, memory_mb: 1024 });
      return next.slice(0, nodeCount);
    });
  }, [nodeCount]);

  const updateNode = (i, key, val) => {
    setNodes(prev => prev.map((n, idx) => idx === i ? { ...n, [key]: val } : n));
  };

  const totalCpu = nodes.reduce((a, n) => a + (n.cpu || 0), 0);
  const totalRam = nodes.reduce((a, n) => a + (n.memory_mb || 0), 0);
  const sysCpu = sysInfo?.system.total_cpu || 4;
  const sysRam = sysInfo?.system.total_ram_mb || 8192;
  const cpuPct = Math.min(100, (totalCpu / sysCpu) * 100);
  const ramPct = Math.min(100, (totalRam / sysRam) * 100);
  const cpuOk = totalCpu <= sysCpu;
  const ramOk = totalRam <= sysRam;

  const deploy = async () => {
    setError('');
    try {
      const res = await fetch('/api/deploy-cluster', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nodes }),
      });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || 'Deploy failed');
        return;
      }
      setDeployStatus({ running: true, logs: [], success: null });
    } catch (e) {
      setError(String(e));
    }
  };

  const cpuOptions = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0];
  const ramOptions = [256, 512, 1024, 1536, 2048, 3072, 4096];

  return (
    <div className="node-config-panel">
      <button className="node-config-toggle" onClick={() => setIsOpen(o => !o)}>
        <span>🖥️ Cluster Setup</span>
        <span style={{ transition: 'transform 0.2s', transform: isOpen ? 'rotate(180deg)' : 'none' }}>▼</span>
      </button>

      {isOpen && (
        <div className="node-config-body">
          {/* System budget */}
          {sysInfo && (
            <div className="budget-section">
              <p className="budget-title">System Resources</p>
              <div className="budget-row">
                <span>CPU Cores</span>
                <span style={{ color: cpuOk ? C.emerald : C.rose, fontWeight: 800 }}>
                  {totalCpu.toFixed(2)} / {sysCpu}
                </span>
              </div>
              <div className="budget-bar-bg">
                <div className="budget-bar" style={{ width: `${cpuPct}%`, background: cpuOk ? C.indigo : C.rose }} />
              </div>
              <div className="budget-row" style={{ marginTop: '0.6rem' }}>
                <span>Memory</span>
                <span style={{ color: ramOk ? C.emerald : C.rose, fontWeight: 800 }}>
                  {totalRam >= 1024 ? `${(totalRam / 1024).toFixed(1)} GB` : `${totalRam} MB`} / {(sysRam / 1024).toFixed(0)} GB
                </span>
              </div>
              <div className="budget-bar-bg">
                <div className="budget-bar" style={{ width: `${ramPct}%`, background: ramOk ? C.emerald : C.rose }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: '#64748b', marginTop: '0.4rem' }}>
                <span>Remaining CPU: <b style={{ color: cpuOk ? C.emerald : C.rose }}>{Math.max(0, sysCpu - totalCpu).toFixed(2)}</b></span>
                <span>Remaining RAM: <b style={{ color: ramOk ? C.emerald : C.rose }}>{Math.max(0, sysRam - totalRam) >= 1024 ? `${(Math.max(0, sysRam - totalRam) / 1024).toFixed(1)}GB` : `${Math.max(0, sysRam - totalRam)}MB`}</b></span>
              </div>
            </div>
          )}

          {/* Node count */}
          <div className="slider-group" style={{ marginTop: '0.75rem' }}>
            <div className="slider-label-row">
              <span>Number of Nodes</span>
              <span className="slider-val">{nodeCount}</span>
            </div>
            <input type="range" min="1" max="8" step="1" value={nodeCount}
              onChange={e => setNodeCount(parseInt(e.target.value))} />
          </div>

          {/* Per-node config */}
          <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {nodes.map((node, i) => (
              <div key={i} className="node-config-row">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ fontSize: '0.72rem', fontWeight: 800, color: '#c7d2fe' }}>Node {i + 1}</span>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <span style={{ fontSize: '0.6rem', color: C.amber, background: 'rgba(245,158,11,0.1)', padding: '1px 6px', borderRadius: 4 }}>
                      {node.cpu} CPU
                    </span>
                    <span style={{ fontSize: '0.6rem', color: C.sky, background: 'rgba(14,165,233,0.1)', padding: '1px 6px', borderRadius: 4 }}>
                      {node.memory_mb}MB
                    </span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.58rem', color: '#64748b', marginBottom: '0.2rem' }}>CPU Cores</div>
                    <select className="node-select" value={node.cpu}
                      onChange={e => updateNode(i, 'cpu', parseFloat(e.target.value))}>
                      {cpuOptions.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.58rem', color: '#64748b', marginBottom: '0.2rem' }}>Memory (MB)</div>
                    <select className="node-select" value={node.memory_mb}
                      onChange={e => updateNode(i, 'memory_mb', parseInt(e.target.value))}>
                      {ramOptions.map(v => <option key={v} value={v}>{v >= 1024 ? `${v / 1024}GB` : `${v}MB`}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {error && (
            <div style={{ background: 'rgba(244,63,94,0.12)', border: '1px solid rgba(244,63,94,0.3)', borderRadius: 8, padding: '0.6rem 0.75rem', fontSize: '0.7rem', color: '#fda4af', marginTop: '0.75rem' }}>
              ❌ {error}
            </div>
          )}

          <button className="btn btn-accent" onClick={deploy}
            disabled={!cpuOk || !ramOk || deployStatus.running}
            style={{ marginTop: '0.85rem', padding: '0.65rem' }}>
            {deployStatus.running ? '⏳ Deploying...' : `🚀 Deploy ${nodeCount} Node Cluster`}
          </button>

          {/* Deploy logs */}
          {deployStatus.logs.length > 0 && (
            <div ref={deployLogRef} style={{
              marginTop: '0.75rem', background: '#0d1117', color: '#4ade80',
              padding: '0.75rem', borderRadius: 8, fontSize: '0.65rem',
              fontFamily: 'JetBrains Mono, monospace', height: 140, overflowY: 'auto',
              lineHeight: 1.7
            }}>
              {deployStatus.logs.map((l, i) => <div key={i}>{l}</div>)}
              {deployStatus.success === true && <div style={{ color: '#4ade80', fontWeight: 700, marginTop: 4 }}>✅ Cluster is live!</div>}
              {deployStatus.success === false && <div style={{ color: '#f87171', fontWeight: 700, marginTop: 4 }}>❌ Deploy failed. Check logs.</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Main App ─────────────────────────────────────────────────────────────────
const App = () => {
  const [telemetry, setTelemetry] = useState({});
  const [strategy, setStrategy] = useState('hardware-aware');
  const [compareStrategies, setCompareStrategies] = useState(['Hardware-Aware', 'Least-Connection']);
  const [loadParams, setLoadParams] = useState({ concurrent: 2, total: 20, min_tokens: 10, max_tokens: 50 });
  const [benchmarkStatus, setBenchmarkStatus] = useState({ running: false, logs: [], strategy: '', live_data: [] });
  const [generating, setGenerating] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [plotTimestamp, setPlotTimestamp] = useState(Date.now());
  const [report, setReport] = useState('');
  const [reportStatus, setReportStatus] = useState({ running: false, progress: 0, current_graph: '', completed: [] });
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [startTime, setStartTime] = useState(Date.now());
  const [telemetryHistory, setTelemetryHistory] = useState([]);
  const [liveData, setLiveData] = useState([]);
  const [autoStatus, setAutoStatus] = useState({ running: false, phase: '', completed: 0, total: 8, log: [], finished: false, current_strategy: '', current_load: '', test_generation: 0 });
  const lastTestGen = useRef(0);
  const [detailedResults, setDetailedResults] = useState({});
  const [suiteResults, setSuiteResults] = useState([]);
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
  const [selectedStrategies, setSelectedStrategies] = useState(['hardware-aware', 'round-robin', 'least-connection', 'hashing']);
  const [selectedLoads, setSelectedLoads] = useState([
    { id: 'normal', name: 'Normal', concurrent: 2, total: 20, min_tokens: 10, max_tokens: 50, enabled: true },
    { id: 'stress', name: 'Stress', concurrent: 20, total: 100, min_tokens: 50, max_tokens: 400, enabled: true },
  ]);
  const [toast, setToast] = useState(null);
  const showToast = (message, type = 'info') => {
    setToast({ message, type, id: Date.now() });
    setTimeout(() => setToast(null), 4000);
  };

  const consoleRef = useRef(null);
  const autoLogRef = useRef(null);
  const loadParamsRef = useRef(loadParams);
  const liveDataRef = useRef([]);

  useEffect(() => { loadParamsRef.current = loadParams; }, [loadParams]);
  useEffect(() => { liveDataRef.current = liveData; }, [liveData]);

  // Theme persistence
  useEffect(() => {
    localStorage.setItem('theme', theme);
    document.body.className = `${theme}-theme`;
  }, [theme]);
  const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark');

  // Fetch detailed benchmark results for Chart.js research components
  const fetchDetailedResults = async (filename) => {
    try {
      const resp = await fetch(`/api/benchmark-detailed-results?file=${filename}`);
      const data = await resp.json();
      setDetailedResults(prev => ({ ...prev, [filename]: data }));
    } catch (e) { console.error(e); }
  };
  useEffect(() => {
    suiteResults.forEach(r => {
      if (!detailedResults[r.filename]) fetchDetailedResults(r.filename);
    });
  }, [suiteResults]);

  // Fetch suite results on mount (so charts aren't empty if previous results exist)
  useEffect(() => {
    fetch('/api/benchmark-results').then(r => r.json()).then(setSuiteResults).catch(() => {});
  }, []);

  useEffect(() => {
    if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [benchmarkStatus.logs]);
  useEffect(() => {
    if (autoLogRef.current) autoLogRef.current.scrollTop = autoLogRef.current.scrollHeight;
  }, [autoStatus.log]);

  // ── Auto-Benchmark Orchestrator Polling ─────────────────────────────────────
  useEffect(() => {
    if (!autoStatus.running) return;
    const id = setInterval(() => {
      fetch('/api/auto-benchmark-status').then(r => r.json()).then(data => {
        // Per-test reset: when test_generation increments, reset live sparklines
        if (data.test_generation && data.test_generation !== lastTestGen.current) {
          lastTestGen.current = data.test_generation;
          setTelemetryHistory([]);
          setLiveData([]);
        }
        setAutoStatus(data);
        if (!data.running) {
          clearInterval(id);
          if (data.finished) setPlotTimestamp(Date.now());
        }
      }).catch(() => { });
      // Also poll suite results for Chart.js research charts
      fetch('/api/benchmark-results').then(r => r.json()).then(setSuiteResults).catch(() => {});
    }, 1500);
    return () => clearInterval(id);
  }, [autoStatus.running]);

  const startAutoSuite = async () => {
    try {
      // Reset all results and live metrics for a clean slate
      setSuiteResults([]);
      setDetailedResults({});
      setTelemetryHistory([]);
      setLiveData([]);
      setBenchmarkStatus({ running: false, progress: 0, total: 0, logs: [] });
      const res = await fetch('/api/auto-benchmark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (res.ok) {
        setAutoStatus(prev => ({ ...prev, running: true, phase: 'Initializing...', completed: 0, log: [], finished: false }));
        setCompareStrategies(['Hardware-Aware', 'Round-Robin', 'Least-Connection', 'Hashing']);
        showToast('🔬 Research suite started — 8 benchmarks queued', 'success');
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(`⚠️ ${err.detail || 'Could not start suite'}`, 'warning');
      }
    } catch (e) {
      console.error(e);
      showToast('❌ Failed to start research suite — check API connection', 'error');
    }
  };

  // ── Telemetry ───────────────────────────────────────────────────────────────
  useEffect(() => {
    const pollInterval = benchmarkStatus.running ? 500 : 2000;
    const id = setInterval(() => {
      fetch('/api/telemetry').then(r => r.json()).then(data => {
        if (!data.stats) return;
        setTelemetry(data.stats);
        const nodes = Object.values(data.stats);
        const avgCpu = nodes.reduce((a, n) => a + (n.cpu_percent || 0), 0) / (nodes.length || 1);
        const avgRam = nodes.reduce((a, n) => a + (n.memory_mb || 0), 0) / (nodes.length || 1);
        const lData = liveDataRef.current;
        // Only compute latency/throughput stats when live benchmark data exists
        if (lData.length > 0) {
          const rec = lData.slice(-20);
          const latArr = rec.map(p => p.latency_ms);
          const sorted = [...latArr].sort((a, b) => a - b);
          let lat = latArr.reduce((a, b) => a + b, 0) / latArr.length;
          let p95 = sorted[Math.floor(sorted.length * 0.95)] || lat * 1.5;
          let p99 = sorted[Math.floor(sorted.length * 0.99)] || lat * 2.0;
          const windowElapsed = rec.length > 1 ? Math.max(0.1, rec[rec.length - 1].timestamp - rec[0].timestamp) : Math.max(0.1, (Date.now() - startTime) / 1000);
          const thr = rec.length / windowElapsed;
          const suc = rec.filter(p => p.status === 200).length / rec.length * 100;
          setTelemetryHistory(prev => [...prev.slice(-49), { cpu: avgCpu, ram: avgRam, lat, p95, p99, thr, suc }]);
        } else {
          // Idle mode: only track CPU/RAM, no fake latency data
          setTelemetryHistory(prev => [...prev.slice(-49), { cpu: avgCpu, ram: avgRam, lat: 0, p95: 0, p99: 0, thr: 0, suc: 100 }]);
        }
      }).catch(() => { });
    }, pollInterval);
    return () => clearInterval(id);
  }, [startTime, benchmarkStatus.running]);

  // ── Benchmark Status ────────────────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => {
      fetch('/api/benchmark-status').then(r => r.json()).then(data => {
        setBenchmarkStatus(data);
        if (data.live_data) setLiveData(data.live_data);
      }).catch(() => { });
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Report polling ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!isGeneratingReport) return;
    const id = setInterval(async () => {
      try {
        const data = await fetch('/api/report-status').then(r => r.json());
        setReportStatus(data);
        if (data.report && typeof data.report === 'string') setReport(data.report);
        if (!data.running) {
          setIsGeneratingReport(false);
          clearInterval(id);
          if (data.report) showToast('📊 Intelligence Report ready!', 'success');
        }
      } catch (e) { }
    }, 2000);
    return () => clearInterval(id);
  }, [isGeneratingReport]);

  const startBenchmark = () => {
    setLiveData([]); setStartTime(Date.now());
    showToast(`🚀 Benchmark started: ${strategy} · ${loadParams.concurrent} users · ${loadParams.total} requests`, 'success');
    fetch('/api/benchmark', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...loadParams, strategy }) }).catch(() => {
      showToast('❌ Failed to start benchmark', 'error');
    });
  };

  const generateReport = async () => {
    setIsGeneratingReport(true); setReport('');
    setReportStatus({ running: true, progress: 0, current_graph: 'Starting...', completed: [] });
    try { await fetch('/api/generate-report', { method: 'POST' }); } catch (e) { setIsGeneratingReport(false); }
  };

  const stopReport = async () => {
    try {
      await fetch('/api/cancel-report', { method: 'POST' });
      setIsGeneratingReport(false);
      showToast('🛑 Analysis stopped', 'warning');
    } catch (e) { }
  };

  const stopBenchmark = async () => {
    try {
      await fetch('/api/benchmark-stop', { method: 'POST' });
      showToast('🛑 Benchmark stopped', 'warning');
    } catch (e) {
      showToast('⚠️ Could not stop benchmark (endpoint may not exist)', 'error');
    }
  };

  const generatePlots = () => {
    setGenerating(true); setCountdown(5);
    const t = setInterval(() => setCountdown(prev => {
      if (prev <= 1) {
        clearInterval(t);
        fetch('/api/generate-plots', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ strategies: compareStrategies })
        }).then(() => { setPlotTimestamp(Date.now()); setGenerating(false); });
        return 0;
      }
      return prev - 1;
    }), 1000);
  };

  const toggleCompare = (s) => {
    setCompareStrategies(prev =>
      prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]
    );
  };

  const exportReport = () => {
    const el = document.createElement('a');
    el.href = URL.createObjectURL(new Blob([report], { type: 'text/markdown' }));
    el.download = `ucir_report_${Date.now()}.md`;
    document.body.appendChild(el); el.click();
  };

  // ── Report Renderer ─────────────────────────────────────────────────────────
  const renderReport = (text) => {
    if (!text) return null;
    return <div className="report-synthesis">{renderMarkdown(text)}</div>;
  };

  const renderMarkdown = (text) => {
    if (!text) return null;
    const lines = text.split('\n');
    const output = [];
    let inTable = false;
    let tableRows = [];

    // Pre-parse references like [img_0]: data:image/png;base64,...
    const refs = {};
    for (let i = 0; i < lines.length; i++) {
      const match = lines[i].match(/^\[(.*?)\]:\s*(.*?)$/);
      if (match) {
        refs[match[1]] = match[2];
      }
    }

    const flushTable = () => {
      if (tableRows.length > 0) {
        const headers = tableRows[0];
        const dataRows = tableRows.slice(2); // skip separator row
        output.push(
          <table key={`tbl-${output.length}`} className="report-table">
            <thead><tr>{headers.split('|').filter(c => c.trim()).map((c, j) =>
              <th key={j}>{c.trim()}</th>
            )}</tr></thead>
            <tbody>{dataRows.map((row, ri) =>
              <tr key={ri}>{row.split('|').filter(c => c.trim()).map((c, j) =>
                <td key={j}>{c.trim()}</td>
              )}</tr>
            )}</tbody>
          </table>
        );
        tableRows = [];
      }
      inTable = false;
    };

    const renderInline = (txt) => {
      // Handle **bold** and basic emoji-prefixed labels
      return txt.split(/(\*\*[^*]+\*\*)/).map((part, k) => {
        if (part.startsWith('**') && part.endsWith('**'))
          return <strong key={k}>{part.slice(2, -2)}</strong>;
        return part;
      });
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // Skip reference lines
      if (line.match(/^\[(.*?)\]:\s*(.*?)$/)) continue;

      // Table detection
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        if (!inTable) inTable = true;
        tableRows.push(line);
        // Check if next line is NOT a table row → flush
        if (i + 1 >= lines.length || !lines[i + 1].trim().startsWith('|')) {
          flushTable();
        }
        continue;
      }
      if (inTable) flushTable();

      // Headings
      if (line.startsWith('# ')) {
        output.push(<h1 key={i} className="report-h1">{line.substring(2)}</h1>);
      } else if (line.startsWith('### ')) {
        output.push(<h3 key={i} className="report-h3">{line.substring(4)}</h3>);
      } else if (line.startsWith('## ')) {
        const isAccent = ['🏁', '📌', '🗂️', '📊', '📈'].some(ic => line.includes(ic));
        output.push(<h2 key={i} className={isAccent ? 'report-h2-accent' : 'report-h2'}>{line.substring(3)}</h2>);
      } else if (line.startsWith('![')) {
        // Image parsing: ![alt](url) OR ![alt][ref]
        const inlineMatch = line.match(/^!\[(.*?)\]\((.*?)\)/);
        const refMatch = line.match(/^!\[(.*?)\]\[(.*?)\]/);
        
        if (inlineMatch) {
          const [, alt, url] = inlineMatch;
          output.push(
            <div key={i} className="report-plot-card">
              <img src={url} alt={alt} style={{ width: '100%', borderRadius: '12px', border: '1px solid var(--glass-border)', display: 'block' }}
                onError={e => { e.target.style.display = 'none'; }} />
            </div>
          );
        } else if (refMatch) {
          const [, alt, refId] = refMatch;
          const url = refs[refId];
          if (url) {
            output.push(
              <div key={i} className="report-plot-card">
                <img src={url} alt={alt} style={{ width: '100%', borderRadius: '12px', border: '1px solid var(--glass-border)', display: 'block' }}
                  onError={e => { e.target.style.display = 'none'; }} />
              </div>
            );
          } else {
            output.push(<p key={i} className="report-p">{renderInline(line)}</p>);
          }
        } else {
          output.push(<p key={i} className="report-p">{renderInline(line)}</p>);
        }
      } else if (line.startsWith('> ')) {
        output.push(<blockquote key={i} className="report-blockquote">{renderInline(line.substring(2))}</blockquote>);
      } else if (line.startsWith('- ')) {
        output.push(<p key={i} className="report-point">• {renderInline(line.substring(2))}</p>);
      } else if (line.trim() === '---') {
        output.push(<hr key={i} className="report-hr" />);
      } else if (line.trim() === '') {
        output.push(<div key={i} style={{ height: '0.4rem' }} />);
      } else if (['🔍', '📶', '⚖️', '⚠️', '💡', '🛠️', '🔧'].some(ic => line.startsWith(ic))) {
        output.push(<p key={i} className="report-point">{renderInline(line)}</p>);
      } else {
        output.push(<p key={i} className="report-p">{renderInline(line)}</p>);
      }
    }

    if (inTable) flushTable();
    return output;
  };

  // ── Derived stats ───────────────────────────────────────────────────────────
  const avgLatency = liveData.length > 0 ? liveData.reduce((a, p) => a + p.latency_ms, 0) / liveData.length : 0;
  const successRate = liveData.length > 0 ? liveData.filter(p => p.status === 200).length / liveData.length * 100 : null;
  const telVals = Object.values(telemetry);
  const avgCpu = telVals.length > 0 ? telVals.reduce((a, n) => a + (n.cpu_percent || 0), 0) / telVals.length : 0;
  const avgRam = telVals.length > 0 ? telVals.reduce((a, n) => a + (n.memory_mb || 0), 0) / telVals.length : 0;
  const srColor = successRate === null ? C.slateL : successRate >= 99 ? C.emerald : successRate >= 95 ? C.amber : C.rose;

  const strategyDetails = {
    'Hardware-Aware': { id: 'ha', label: 'HA' },
    'Round-Robin': { id: 'rr', label: 'RR' },
    'Least-Connection': { id: 'lc', label: 'LC' },
    'Hashing': { id: 'hash', label: 'Hash' }
  };
  const activePlots = [
    { id: 'latency_comparison', label: 'Latency Comparison' },
    { id: 'latency_distribution', label: 'Latency Distribution' },
    { id: 'success_rate', label: 'Success Rate' }
  ];
  compareStrategies.forEach(s => {
    const details = strategyDetails[s];
    if (details) {
      activePlots.push({ id: `latency_${details.id}_normal`, label: `${details.label} — Normal Load` });
      activePlots.push({ id: `latency_${details.id}_stress`, label: `${details.label} — Stress Load` });
    }
  });
  activePlots.push({ id: 'global_dashboard', label: 'Global Dashboard' });

  return (
    <div className="dashboard-root">

      {/* ── SIDEBAR ─────────────────────────────────────────────────────── */}
      <aside className="sidebar no-print">
        {/* Logo / branding */}
        <div className="sidebar-brand">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
            <div className="sidebar-logo">⚡</div>
            <div>
              <div className="sidebar-title">CLUSTER CONSOLE</div>
              <div className="sidebar-sub">Distributed Inference Engine</div>
            </div>
          </div>
          <button className="theme-toggle-btn" onClick={toggleTheme} style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '0.3rem 0.5rem', cursor: 'pointer', fontSize: '1rem' }}>{theme === 'dark' ? '☀️' : '🌙'}</button>
        </div>

        <div className="sidebar-body">

          {/* ── Node Configurator (collapsible) ── */}
          <NodeConfigurator />

          {/* ── Benchmark Config ── */}
          <section>
            <p className="section-label">Benchmark Config</p>
            <div className="mode-row">
              <button className={`btn ${loadParams.concurrent < 5 ? 'btn-active' : 'btn-ghost'}`}
                onClick={() => setLoadParams({ concurrent: 2, total: 20, min_tokens: 10, max_tokens: 50 })}>Normal</button>
              <button className={`btn ${loadParams.concurrent >= 10 ? 'btn-active' : 'btn-ghost'}`}
                onClick={() => setLoadParams({ concurrent: 20, total: 100, min_tokens: 50, max_tokens: 400 })}>Stress</button>
            </div>
            {[
              { key: 'concurrent', label: 'Number of Users', min: 1, max: 50, step: 1 },
              { key: 'total', label: 'Total Requests', min: 10, max: 500, step: 10 },
            ].map(({ key, label, min, max, step }) => (
              <div key={key} className="slider-group">
                <div className="slider-label-row">
                  <span>{label}</span>
                  <span className="slider-val">{loadParams[key]}</span>
                </div>
                <input type="range" min={min} max={max} step={step} value={loadParams[key]}
                  onChange={e => setLoadParams({ ...loadParams, [key]: parseInt(e.target.value) })} />
              </div>
            ))}
            
            <div className="slider-group" style={{ marginTop: '1rem' }}>
              <div className="slider-label-row" style={{ color: 'var(--accent)' }}>
                <span>Token Bounds (Minnows ↔ Whales)</span>
                <span className="slider-val" style={{ whiteSpace: 'nowrap' }}>[{loadParams.min_tokens}, {loadParams.max_tokens}]</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.8rem', marginTop: '0.5rem' }}>
                <div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.2rem' }}>Min Tokens</div>
                    <input type="range" min={1} max={loadParams.max_tokens - 1} step={5} value={loadParams.min_tokens}
                    onChange={e => setLoadParams({ ...loadParams, min_tokens: parseInt(e.target.value) })} />
                </div>
                <div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.2rem' }}>Max Tokens</div>
                    <input type="range" min={loadParams.min_tokens + 1} max={2000} step={50} value={loadParams.max_tokens}
                    onChange={e => setLoadParams({ ...loadParams, max_tokens: parseInt(e.target.value) })} />
                </div>
              </div>
            </div>
          </section>

          {/* ── Routing Strategy ── */}
          <section>
            <p className="section-label">Routing Strategy</p>
            {[
              { id: 'hardware-aware', emoji: '🔥', name: 'Hardware-Aware', desc: 'Routes to least-loaded node via telemetry.' },
              { id: 'round-robin', emoji: '🔄', name: 'Round Robin', desc: 'Cyclic request distribution.' },
              { id: 'least-connection', emoji: '⚖️', name: 'Least Connection', desc: 'Routes to node with fewest active requests.' },
              { id: 'hashing', emoji: '🔑', name: 'Hashing', desc: 'Deterministic routing by prompt content.' },
            ].map(s => (
              <div key={s.id} className={`strategy-card ${strategy === s.id ? 'strategy-active' : ''}`}
                onClick={() => setStrategy(s.id)}>
                <p className="strategy-name">{s.emoji} {s.name}
                  {strategy === s.id && <span className="strategy-badge">ACTIVE</span>}
                </p>
                <p className="strategy-desc">{s.desc}</p>
              </div>
            ))}
          </section>

          <button className="btn btn-accent" onClick={startBenchmark} disabled={benchmarkStatus.running || autoStatus.running}>
            {benchmarkStatus.running ? '⏳ Running...' : '🚀 Execute Production Test'}
          </button>

          {/* ── Full Research Suite ── */}
          <div style={{ borderTop: `1px solid var(--glass-border)`, paddingTop: '0.75rem', marginTop: '0.5rem' }}>
            <p className="section-label" style={{ marginBottom: '0.4rem' }}>🔬 Automated Research</p>
            <button className="btn" onClick={startAutoSuite}
              disabled={autoStatus.running || benchmarkStatus.running}
              style={{
                background: autoStatus.running ? 'rgba(139,92,246,0.15)' : 'linear-gradient(135deg, rgba(139,92,246,0.2), rgba(99,102,241,0.2))',
                border: `1px solid ${autoStatus.running ? C.violet : 'rgba(139,92,246,0.3)'}`,
                color: autoStatus.running ? C.violet : 'var(--accent-light)',
                fontWeight: 700,
              }}>
              {autoStatus.running ? `⏳ Running ${autoStatus.completed}/${autoStatus.total}...` : '🔬 Run Full Research Suite'}
            </button>
            {autoStatus.running && (
              <div style={{ fontSize: '0.62rem', color: 'var(--accent-light)', marginTop: '0.35rem', lineHeight: 1.6 }}>
                <div>Strategy: <b style={{ color: C.amber }}>{autoStatus.current_strategy}</b></div>
                <div>Load: <b>{autoStatus.current_load}</b></div>
                <div style={{ color: 'var(--text-muted)' }}>{autoStatus.phase}</div>
              </div>
            )}
            <p style={{ fontSize: '0.55rem', color: 'var(--text-muted)', marginTop: '0.35rem', lineHeight: 1.5 }}>
              Runs all 4 strategies × 2 loads (8 benchmarks), then auto-generates plots.
            </p>
          </div>

          <button className={`btn ${isGeneratingReport ? 'btn-accent' : 'btn-outline'}`}
            onClick={generateReport} disabled={isGeneratingReport}>
            {isGeneratingReport ? '🛡️ AI Analyzing...' : '📊 Update Intelligence Report'}
          </button>
          <button className="btn"
            style={{
              borderColor: (isGeneratingReport || benchmarkStatus.running || autoStatus.running) ? C.rose : 'var(--glass-border)',
              color: (isGeneratingReport || benchmarkStatus.running || autoStatus.running) ? C.rose : 'var(--text-muted)',
              background: (isGeneratingReport || benchmarkStatus.running || autoStatus.running) ? 'rgba(244,63,94,0.06)' : 'var(--glass)',
              cursor: (isGeneratingReport || benchmarkStatus.running || autoStatus.running) ? 'pointer' : 'not-allowed',
              marginTop: '0.5rem'
            }}
            onClick={() => {
              if (isGeneratingReport) stopReport();
              if (benchmarkStatus.running || autoStatus.running) stopBenchmark();
            }}
            disabled={!(isGeneratingReport || benchmarkStatus.running || autoStatus.running)}>
            🛑 Stop Analysis
          </button>
        </div>
      </aside>

      {/* ── MAIN ────────────────────────────────────────────────────────── */}
      <main className="main-view">

        {/* Beautiful page header */}
        <div className="page-hero">
          <div className="page-hero-left">
            <div className="page-hero-icon">🌐</div>
            <div>
              <h1 className="page-hero-title">Distributed Inference Dashboard</h1>
              <p className="page-hero-sub">Real-time analytics · Hardware-Aware routing · UCIR AI reporting</p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <div className="health-badge">
              <span className="health-dot"></span> HEALTH: STABLE
            </div>
            <div className="node-count-badge">
              {Object.keys(telemetry).length} Nodes Online
            </div>
          </div>
        </div>

        {/* Node telemetry grid */}
        <section className="node-grid">
          {Object.entries(telemetry).sort(([a], [b]) => a.localeCompare(b)).map(([id, stats]) => (
            <div key={id} className="node-card">
              <div className="node-header">
                <span className="node-id">{id.replace(/.*inference-/i, '').toUpperCase()}</span>
                <span className="node-dot" style={{ background: stats.healthy ? C.emerald : C.rose }}></span>
              </div>
              {(() => {
                const burdenScore = (stats.cpu_percent || 0) * 0.4 + ((stats.memory_mb || 0) / 1024 * 100) * 0.1 + (stats.active_requests || 0) * 50;
                return [
                  { label: 'CPU', value: `${(stats.cpu_percent || 0).toFixed(1)}%`, pct: stats.cpu_percent || 0, color: C.indigo },
                  { label: 'RAM', value: `${(stats.memory_mb || 0).toFixed(0)} MB`, pct: (stats.memory_mb / 1024) * 100, color: C.emerald },
                  { label: 'Burden', value: burdenScore.toFixed(1), pct: Math.min(100, (burdenScore / 250) * 100), color: C.rose },
                ].map(m => (
                  <div key={m.label} className="meter-group">
                    <div className="meter-label-row">
                      <span>{m.label}</span><span className="meter-val">{m.value}</span>
                    </div>
                    <div className="meter-bar-bg">
                      <div className="meter-bar" style={{ width: `${Math.min(100, m.pct)}%`, background: m.color }} />
                    </div>
                  </div>
                ));
              })()}
            </div>
          ))}
        </section>

        {/* ── Auto-Orchestrator Progress Panel ────────────────────────────── */}
        {(autoStatus.running || autoStatus.finished) && (
          <section className="glass-card" style={{ borderLeft: `3px solid ${autoStatus.running ? C.violet : C.emerald}` }}>
            <div className="card-header">
              <div>
                <h3 className="card-title">🔬 Research Suite {autoStatus.running ? 'In Progress' : 'Complete'}</h3>
                <p className="card-sub">
                  {autoStatus.running
                    ? `${autoStatus.phase} · ${autoStatus.completed}/${autoStatus.total} benchmarks`
                    : `✅ All ${autoStatus.total} benchmarks finished · Plots generated`}
                </p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                {autoStatus.current_strategy && autoStatus.running && (
                  <div style={{
                    background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)',
                    borderRadius: 6, padding: '0.25rem 0.65rem', fontSize: '0.7rem',
                    color: C.amber, fontWeight: 700
                  }}>
                    {autoStatus.current_strategy.toUpperCase()} · {autoStatus.current_load?.toUpperCase()}
                  </div>
                )}
                <span style={{ fontSize: '0.8rem', fontWeight: 800, color: autoStatus.running ? C.violet : C.emerald }}>
                  {autoStatus.completed}/{autoStatus.total}
                </span>
              </div>
            </div>

            {/* Progress bar */}
            <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 6, height: 8, marginBottom: '1rem', overflow: 'hidden' }}>
              <div style={{
                width: `${(autoStatus.completed / Math.max(1, autoStatus.total)) * 100}%`,
                height: '100%',
                background: autoStatus.running ? `linear-gradient(90deg, ${C.violet}, ${C.indigo})` : C.emerald,
                borderRadius: 6,
                transition: 'width 0.5s ease',
              }} />
            </div>

            {/* Log console */}
            <div ref={autoLogRef} style={{
              background: '#0d1117', borderRadius: 8, padding: '0.75rem',
              fontSize: '0.62rem', fontFamily: 'JetBrains Mono, monospace',
              color: '#8b949e', maxHeight: 200, overflowY: 'auto', lineHeight: 1.7,
            }}>
              {autoStatus.log?.map((l, i) => (
                <div key={i} style={{ color: l.includes('✅') ? '#4ade80' : l.includes('❌') ? '#f87171' : l.includes('🚀') ? '#a5b4fc' : '#8b949e' }}>{l}</div>
              ))}
              {autoStatus.log?.length === 0 && <span style={{ color: '#30363d' }}>Waiting for orchestrator events...</span>}
            </div>
          </section>
        )}

        {/* ── Analytics Preview ──────────────────────────────────────────── */}
        <section className="glass-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Performance Analytics Preview</h3>
              <p className="card-sub">Live trend analysis · updates every 2s (500ms during benchmarks)</p>
            </div>
            <div className="stat-pill" style={{ background: `${srColor}18`, borderColor: `${srColor}40`, color: srColor }}>
              Wave Success: <strong>{successRate === null ? '—' : `${successRate.toFixed(1)}%`}</strong>
            </div>
          </div>

          {/* Wide multi-line overlay chart */}
          <div style={{ marginBottom: '1.25rem' }}>
            <LatencyMultiChart data={telemetryHistory} />
          </div>

          {/* 6 individual sparklines */}
          <div className="chart-grid">
            <LineChart data={telemetryHistory} dataKey="lat" color={C.indigo} label="Mean Latency" unit="ms" isBadIfIncreasing />
            <LineChart data={telemetryHistory} dataKey="p95" color={C.amber} label="P95 Latency" unit="ms" isBadIfIncreasing />
            <LineChart data={telemetryHistory} dataKey="p99" color={C.rose} label="P99 Latency" unit="ms" isBadIfIncreasing />
            <LineChart data={telemetryHistory} dataKey="thr" color={C.emerald} label="Throughput" unit=" req/s" />
            <LineChart data={telemetryHistory} dataKey="cpu" color={C.violet} label="Global CPU" unit="%" isBadIfIncreasing />
            <LineChart data={telemetryHistory} dataKey="ram" color={C.sky} label="Global RAM" unit=" MB" />
            <SuccessRateChart data={telemetryHistory} />
            <BurdenCompareChart telemetry={telemetry} />
          </div>

          {/* KPI row */}
          <div className="kpi-grid">
            {[
              { label: 'Avg CPU', val: `${avgCpu.toFixed(1)}%`, color: C.indigo },
              { label: 'Avg RAM', val: `${avgRam.toFixed(0)} MB`, color: C.sky },
              { label: 'Success Rate', val: successRate === null ? '—' : `${successRate.toFixed(1)}%`, color: srColor },
              { label: 'Mean Response', val: liveData.length === 0 ? '—' : `${avgLatency.toFixed(0)}ms`, color: C.amber },
            ].map(s => (
              <div key={s.label} className="kpi-card">
                <p className="kpi-label">{s.label}</p>
                <p className="kpi-val" style={{ color: s.color }}>{s.val}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Chart.js Research Suite Results ─────────────────────────────── */}
        <ResearchBenchmarkChart results={suiteResults} theme={theme} />

        {/* ── Deep Research Insights (Chart.js) ──────────────────────────── */}
        <section className="gallery-section">
          <div className="section-header">
            <div>
              <h2 className="section-title">Deep Research Insights</h2>
              <p className="section-sub">Dynamic distribution analysis · 4 strategies × Normal/Stress</p>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '1.5rem' }}>
            {['HA', 'RR', 'LC', 'HS'].flatMap(strat =>
              ['Normal', 'Stress'].map(load => {
                const res = suiteResults.find(r => normalizeStrategy(r.strategy) === strat && normalizeLoad(r.load) === load);
                return (
                  <div key={`${strat}-${load}`} className="glass-card" style={{ padding: '1.25rem', opacity: res ? 1 : 0.45 }}>
                    <h4 style={{ fontSize: '0.85rem', marginBottom: '1rem', color: 'var(--text-main)' }}>{strat} ({load})</h4>
                    <div style={{ height: 160 }}>
                      <LatencyHistogram data={res ? detailedResults[res.filename] : []} theme={theme} />
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
                      <div style={{ height: 120 }}>
                        <SuccessRateDoughnut data={res ? detailedResults[res.filename] : null} />
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                        {res ? (
                          <>
                            <p><b>Mean:</b> {res.avg_latency.toFixed(1)}ms</p>
                            <p><b>P95:</b> {res.p95_latency.toFixed(1)}ms</p>
                            <p><b>Success:</b> {res.success_rate.toFixed(1)}%</p>
                          </>
                        ) : (
                          <p style={{ fontStyle: 'italic' }}>Awaiting data…</p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* ── Live Console ──────────────────────────────────────────────── */}
        <section className="glass-card no-print">
          <h3 className="console-title">Live Cluster Console</h3>
          <div ref={consoleRef} className="console-body">
            {benchmarkStatus.logs?.length > 0
              ? benchmarkStatus.logs.map((log, i) => <div key={i} className="console-line">{log}</div>)
              : <span className="console-idle">Waiting for benchmark events...</span>}
          </div>
        </section>

        {/* ── Gallery ───────────────────────────────────────────────────── */}
        <section className="no-print gallery-section">
          <div className="section-header">
            <div>
              <h2 className="section-title">Performance Comparison Gallery</h2>
              <p className="section-sub">Select strategies to compare (Click 'Update Analytics' to apply)</p>
              <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--text-dim)' }}>
                {['Hardware-Aware', 'Round-Robin', 'Least-Connection', 'Hashing'].map(s => (
                  <label key={s} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
                    <input type="checkbox" checked={compareStrategies.includes(s)}
                      onChange={() => toggleCompare(s)} style={{ cursor: 'pointer' }} />
                    {s}
                  </label>
                ))}
              </div>
            </div>
            <button className="btn btn-accent-sm" onClick={generatePlots}
              disabled={generating || benchmarkStatus.running}>
              {generating ? `Processing... (${countdown}s)` : '🔁 Update Analytics'}
            </button>
          </div>
          <div className="plot-grid">
            {activePlots.map(plot => (
              <div key={plot.id} className="plot-item">
                <p className="plot-label">
                  <span className="plot-dot"></span>{plot.label}
                </p>
                <img src={`/plots/group22_${plot.id}.png?t=${plotTimestamp}`} alt={plot.label}
                  onError={e => {
                    e.target.style.display = 'none';
                    const p = e.target.parentNode;
                    if (!p.querySelector('.plot-ph')) {
                      const el = document.createElement('div');
                      el.className = 'plot-ph';
                      el.innerHTML = '📊 Run benchmark →<br/>Update Analytics to generate';
                      p.appendChild(el);
                    }
                  }} />
              </div>
            ))}
          </div>
        </section>

        {/* ── Intelligence Report ───────────────────────────────────────── */}
        <section className={`glass-card report-section ${isGeneratingReport || report ? '' : 'no-print'}`} id="intel-report">
          <div className="card-header" style={{ borderBottom: '1px solid #f1f5f9', paddingBottom: '1rem', marginBottom: '1.5rem' }}>
            <div>
              <h2 className="card-title" style={{ fontSize: '1.15rem' }}>📊 Intelligence Report (UCIR)</h2>
              <p className="card-sub">Unified Cluster Intelligence Report · 8 Plots + Final Synthesis · Powered by Ollama</p>
            </div>
            {(report || isGeneratingReport) && (
              <div style={{ display: 'flex', gap: '0.5rem' }} className="no-print">
                <button className="btn btn-ghost-sm" onClick={() => window.print()}>🖨️ Print</button>
                <button className="btn btn-ghost-sm" onClick={exportReport}>📄 Export MD</button>
              </div>
            )}
          </div>

          {isGeneratingReport && (
            <div className="report-progress">
              <div className="report-progress-header">
                <span>🛡️ UCIR: <strong>{reportStatus.current_graph || '...'}</strong></span>
                <span>{reportStatus.progress}% · {reportStatus.completed.length}/{reportStatus.total_steps || 9} complete</span>
              </div>
              <div className="report-progress-bar-bg">
                <div className="report-progress-bar" style={{ width: `${reportStatus.progress}%` }} />
              </div>

              <div className="report-chips">
                {reportStatus.completed.map(g => <span key={g} className="chip chip-green">✓ {g}</span>)}
                {reportStatus.running && <span className="chip chip-blue">⟳ {reportStatus.current_graph}</span>}
              </div>
            </div>
          )}

          <div className="report-content" id="report-view">
            {report
              ? <div className="markdown-body">{renderReport(report)}</div>
              : (
                <div className="report-empty">
                  <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🤖</div>
                  <p style={{ fontWeight: 600, color: '#475569' }}>Run a benchmark then click <strong>"📊 Update Intelligence Report"</strong></p>
                  <p style={{ fontSize: '0.8rem', color: C.slateL, marginTop: '0.5rem' }}>AI analyzes all 8 plots and generates a final strategic synthesis.</p>
                </div>
              )
            }
          </div>
        </section>

      </main>

      {/* ── Toast Notifications ──────────────────────────────────────── */}
      {toast && (
        <div key={toast.id} style={{
          position: 'fixed', top: '1.5rem', right: '1.5rem', zIndex: 9999,
          padding: '0.85rem 1.5rem', borderRadius: 14,
          background: toast.type === 'success' ? 'rgba(16,185,129,0.95)' : toast.type === 'warning' ? 'rgba(245,158,11,0.95)' : toast.type === 'error' ? 'rgba(244,63,94,0.95)' : 'rgba(99,102,241,0.95)',
          color: '#fff', fontWeight: 700, fontSize: '0.8rem',
          boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
          animation: 'fadeIn 0.3s ease-out',
          backdropFilter: 'blur(12px)',
          maxWidth: 420,
        }}>
          {toast.message}
        </div>
      )}
    </div>
  );
};

export default App;
