import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine } from 'recharts';
import { toast } from 'sonner';
import {
  TrendingUp, TrendingDown, Minus, AlertTriangle, Activity, Search, RefreshCw,
  ArrowRight, Package, BarChart3, Layers, Tag
} from 'lucide-react';

// ── helpers ───────────────────────────────────────────────────────────
const fmtPrice = (n, unit = '') => `$${Number(n || 0).toFixed(2)}${unit ? `/${unit}` : ''}`;
const fmtPct = (n) => `${Number(n || 0).toFixed(1)}%`;
const shortDate = (d) => (d || '').slice(0, 10);

function TrendArrow({ trend }) {
  if (trend === 'up') return <TrendingUp className="w-3.5 h-3.5 text-red-500" />;
  if (trend === 'down') return <TrendingDown className="w-3.5 h-3.5 text-emerald-500" />;
  if (trend === 'stable') return <Minus className="w-3.5 h-3.5 text-slate-400" />;
  return <Activity className="w-3.5 h-3.5 text-slate-300" />;
}

function TrendBadge({ trend }) {
  const cfg = {
    up: { bg: 'bg-red-50', text: 'text-red-600', label: 'UP' },
    down: { bg: 'bg-emerald-50', text: 'text-emerald-600', label: 'DOWN' },
    stable: { bg: 'bg-slate-100', text: 'text-slate-500', label: 'STABLE' },
    insufficient_data: { bg: 'bg-slate-50', text: 'text-slate-400', label: 'NEW' },
  };
  const c = cfg[trend?.trend] || cfg.insufficient_data;
  const pct = trend?.change_pct;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${c.bg} ${c.text}`} data-testid={`trend-badge-${trend?.trend}`}>
      <TrendArrow trend={trend?.trend} />
      {c.label}
      {pct !== null && pct !== undefined && trend?.trend !== 'insufficient_data' && (
        <span className="tabular-nums">{pct > 0 ? '+' : ''}{fmtPct(pct)}</span>
      )}
    </span>
  );
}

function AlertBadge({ alert }) {
  if (!alert) return null;
  const sev = alert.severity === 'high' ? 'bg-red-100 text-red-700 border-red-200' : 'bg-amber-100 text-amber-700 border-amber-200';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold ${sev}`} data-testid={`alert-badge-${alert.canonical_product_id}`}>
      <AlertTriangle className="w-3 h-3" />
      +{fmtPct(alert.change_pct)} vs avg
    </span>
  );
}

// ── Hero KPI tile ─────────────────────────────────────────────────────
function Kpi({ label, value, icon: Icon, iconBg, sub, testId }) {
  return (
    <Card className="border border-slate-100 shadow-sm" data-testid={testId}>
      <CardContent className="flex items-center gap-4 py-4 px-4">
        <div className={`w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center flex-shrink-0`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">{label}</p>
          <p className="text-lg font-heading font-extrabold text-navy-900 leading-tight truncate">{value}</p>
          {sub && <p className="text-[11px] text-slate-400 mt-0.5 truncate">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Detail Modal ──────────────────────────────────────────────────────
function PriceDetailModal({ api, item, onClose }) {
  const [history, setHistory] = useState(null);
  const [vendorData, setVendorData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!item) return;
    setLoading(true);
    const qs = `canonical_unit=${encodeURIComponent(item.canonical_unit || '')}`;
    Promise.all([
      api.get(`/price-intelligence/products/${item.canonical_product_id}/history?${qs}`),
      api.get(`/price-intelligence/products/${item.canonical_product_id}/vendors?${qs}`),
    ])
      .then(([h, v]) => { setHistory(h.data); setVendorData(v.data); })
      .catch(() => toast.error('Failed to load price detail'))
      .finally(() => setLoading(false));
  }, [item, api]);

  const chartData = useMemo(() => {
    if (!history?.observations) return [];
    return history.observations.map((o) => ({
      date: shortDate(o.observed_at || o.invoice_date),
      price: Number(o.price_per_unit) || 0,
      vendor: o.vendor_name || 'Unknown',
    }));
  }, [history]);

  if (!item) return null;

  const stats = history?.stats || {};
  const trend = history?.trend || {};
  const alert = history?.alert;

  return (
    <Dialog open={!!item} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="pi-detail-modal">
        <DialogHeader>
          <DialogTitle className="font-heading text-base flex items-center gap-2 flex-wrap">
            <Package className="w-4 h-4 text-teal-600" />
            <span className="text-navy-900">{item.canonical_name}</span>
            <Badge variant="outline" className="text-[10px] font-mono border-teal-200 text-teal-700 bg-teal-50">
              $/{item.canonical_unit}
            </Badge>
            <TrendBadge trend={trend} />
            {alert && <AlertBadge alert={alert} />}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="space-y-3 py-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}</div>
        ) : (
          <div className="space-y-5">
            {/* Stats row */}
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-slate-50 rounded-lg p-3 text-center" data-testid="stat-avg">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Avg</p>
                <p className="text-lg font-bold text-navy-900 tabular-nums mt-0.5">{fmtPrice(stats.avg)}</p>
              </div>
              <div className="bg-emerald-50 rounded-lg p-3 text-center" data-testid="stat-min">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Min</p>
                <p className="text-lg font-bold text-emerald-600 tabular-nums mt-0.5">{fmtPrice(stats.min)}</p>
              </div>
              <div className="bg-red-50 rounded-lg p-3 text-center" data-testid="stat-max">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Max</p>
                <p className="text-lg font-bold text-red-500 tabular-nums mt-0.5">{fmtPrice(stats.max)}</p>
              </div>
              <div className="bg-teal-50 rounded-lg p-3 text-center" data-testid="stat-latest">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Latest</p>
                <p className="text-lg font-bold text-teal-700 tabular-nums mt-0.5">{fmtPrice(stats.latest)}</p>
                <p className="text-[9px] text-slate-400 mt-0.5 truncate">{shortDate(stats.latest_date) || '—'}</p>
              </div>
            </div>

            {alert && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-start gap-3" data-testid="pi-alert-banner">
                <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="w-4 h-4 text-red-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-bold text-red-800">Price spike detected</p>
                  <p className="text-[11px] text-red-700 mt-0.5">
                    Latest price <span className="font-bold tabular-nums">{fmtPrice(alert.latest_price)}</span> is{' '}
                    <span className="font-bold">+{fmtPct(alert.change_pct)}</span> above the moving average of{' '}
                    <span className="tabular-nums">{fmtPrice(alert.moving_average)}</span>{' '}
                    ({alert.observations} observations · last at {alert.latest_vendor}).
                  </p>
                </div>
              </div>
            )}

            {/* Chart */}
            {chartData.length > 0 && (
              <div className="h-52 w-full">
                <ResponsiveContainer>
                  <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
                    <CartesianGrid stroke="#f1f5f9" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(v) => `$${v.toFixed(2)}`} />
                    <Tooltip formatter={(v) => fmtPrice(v)} contentStyle={{ fontSize: 11 }} />
                    {stats.avg && <ReferenceLine y={stats.avg} stroke="#14b8a6" strokeDasharray="4 4" label={{ value: 'Avg', fill: '#14b8a6', fontSize: 10, position: 'right' }} />}
                    <Line type="monotone" dataKey="price" stroke="#0f766e" strokeWidth={2} dot={{ r: 3, fill: '#0f766e' }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Vendor comparison */}
            <div>
              <h3 className="text-xs font-heading font-bold text-navy-900 mb-2 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-teal-600" />
                Vendor comparison
                {vendorData?.savings_pct > 0 && (
                  <Badge className="bg-emerald-100 text-emerald-700 text-[9px] ml-2">
                    Save up to {fmtPct(vendorData.savings_pct)}
                  </Badge>
                )}
              </h3>
              <Table data-testid="pi-vendor-table">
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-[10px]">Vendor</TableHead>
                    <TableHead className="text-[10px] text-right">Latest</TableHead>
                    <TableHead className="text-[10px] text-right">Avg</TableHead>
                    <TableHead className="text-[10px] text-right">Min</TableHead>
                    <TableHead className="text-[10px] text-right">Max</TableHead>
                    <TableHead className="text-[10px] text-right">Obs</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(vendorData?.vendors || []).map((v, i) => {
                    const isBest = v.vendor === vendorData.best_vendor;
                    const isWorst = v.vendor === vendorData.worst_vendor && vendorData.best_vendor !== vendorData.worst_vendor;
                    return (
                      <TableRow key={v.vendor} data-testid={`pi-vendor-row-${i}`} className={isBest ? 'bg-emerald-50/40' : ''}>
                        <TableCell className="text-xs font-semibold text-navy-900">
                          {v.vendor}
                          {isBest && <Badge className="ml-2 bg-emerald-600 text-white text-[9px]">BEST</Badge>}
                          {isWorst && <Badge className="ml-2 bg-red-500 text-white text-[9px]">HIGHEST</Badge>}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-xs">{fmtPrice(v.latest_price)}</TableCell>
                        <TableCell className="text-right tabular-nums text-xs">{fmtPrice(v.avg_price)}</TableCell>
                        <TableCell className="text-right tabular-nums text-xs text-emerald-700">{fmtPrice(v.min_price)}</TableCell>
                        <TableCell className="text-right tabular-nums text-xs text-red-600">{fmtPrice(v.max_price)}</TableCell>
                        <TableCell className="text-right text-xs text-slate-500">{v.observations}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            {/* History */}
            <div>
              <h3 className="text-xs font-heading font-bold text-navy-900 mb-2 flex items-center gap-1.5">
                <BarChart3 className="w-3.5 h-3.5 text-teal-600" />
                Price history ({history?.observations?.length || 0} observations)
              </h3>
              <div className="max-h-64 overflow-y-auto border border-slate-100 rounded-lg">
                <Table data-testid="pi-history-table">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-[10px]">Date</TableHead>
                      <TableHead className="text-[10px]">Vendor</TableHead>
                      <TableHead className="text-[10px]">Raw name</TableHead>
                      <TableHead className="text-[10px] text-right">Price</TableHead>
                      <TableHead className="text-[10px] text-right">Qty</TableHead>
                      <TableHead className="text-[10px]">Confidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(history?.observations || []).slice().reverse().map((o) => (
                      <TableRow key={o.id} data-testid={`pi-history-row-${o.id}`}>
                        <TableCell className="text-[11px] tabular-nums text-slate-600">{shortDate(o.invoice_date) || shortDate(o.observed_at)}</TableCell>
                        <TableCell className="text-[11px] text-navy-900">{o.vendor_name}</TableCell>
                        <TableCell className="text-[11px] text-slate-500 truncate max-w-[220px]">{o.raw_name}</TableCell>
                        <TableCell className="text-right tabular-nums text-[11px] font-semibold">{fmtPrice(o.price_per_unit)}</TableCell>
                        <TableCell className="text-right tabular-nums text-[11px] text-slate-500">{Number(o.quantity || 0).toFixed(1)}</TableCell>
                        <TableCell className="text-[10px] text-slate-400">
                          id:{o.identity_match_type}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────
export default function PriceIntelligencePage() {
  const { api } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ items: [] });
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // all | alerts | trending_up | trending_down
  const [selected, setSelected] = useState(null);
  const [backfilling, setBackfilling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/price-intelligence/products');
      setData(res.data || { items: [] });
    } catch {
      toast.error('Failed to load price intelligence');
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  const runBackfill = async () => {
    setBackfilling(true);
    try {
      const res = await api.post('/price-intelligence/backfill');
      toast.success(`Backfill complete: ${res.data.observations_inserted} observations ingested`);
      await load();
    } catch {
      toast.error('Backfill failed');
    } finally {
      setBackfilling(false);
    }
  };

  const filtered = useMemo(() => {
    let items = data.items || [];
    if (search) {
      const q = search.toLowerCase();
      items = items.filter((i) => (i.canonical_name || '').toLowerCase().includes(q));
    }
    if (filter === 'alerts') items = items.filter((i) => i.alert);
    if (filter === 'trending_up') items = items.filter((i) => i.trend?.trend === 'up');
    if (filter === 'trending_down') items = items.filter((i) => i.trend?.trend === 'down');
    return items;
  }, [data, search, filter]);

  const kpis = useMemo(() => {
    const items = data.items || [];
    const alertCount = items.filter((i) => i.alert).length;
    const upCount = items.filter((i) => i.trend?.trend === 'up').length;
    const downCount = items.filter((i) => i.trend?.trend === 'down').length;
    const totalObs = items.reduce((s, i) => s + (i.stats?.observations || 0), 0);
    return { total: items.length, alertCount, upCount, downCount, totalObs };
  }, [data]);

  return (
    <div className="space-y-6" data-testid="price-intelligence-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-heading text-2xl font-extrabold text-navy-900 tracking-tight">Price Intelligence</h1>
          <p className="text-sm text-slate-500 mt-1">
            Unit-safe price benchmarks, trend direction, and smart alerts across every canonical product.
          </p>
        </div>
        <Button
          onClick={runBackfill}
          variant="outline"
          size="sm"
          disabled={backfilling}
          data-testid="pi-backfill-btn"
          className="gap-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${backfilling ? 'animate-spin' : ''}`} />
          {backfilling ? 'Backfilling…' : 'Backfill from history'}
        </Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Tracked products" value={kpis.total} icon={Tag} iconBg="bg-teal-600" sub={`${kpis.totalObs} observations`} testId="kpi-products" />
        <Kpi label="Active alerts" value={kpis.alertCount} icon={AlertTriangle} iconBg="bg-red-500" sub=">10% above avg" testId="kpi-alerts" />
        <Kpi label="Trending up" value={kpis.upCount} icon={TrendingUp} iconBg="bg-amber-500" testId="kpi-up" />
        <Kpi label="Trending down" value={kpis.downCount} icon={TrendingDown} iconBg="bg-emerald-600" testId="kpi-down" />
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search canonical products…"
            className="pl-9 h-9 text-sm"
            data-testid="pi-search-input"
          />
        </div>
        <div className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-lg" role="tablist">
          {['all', 'alerts', 'trending_up', 'trending_down'].map((k) => (
            <button
              key={k}
              className={`text-[11px] font-semibold px-2.5 py-1 rounded-md transition-colors ${
                filter === k ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-navy-700'
              }`}
              onClick={() => setFilter(k)}
              data-testid={`pi-filter-${k}`}
            >
              {k === 'all' ? 'All' : k === 'alerts' ? `Alerts${kpis.alertCount ? ` (${kpis.alertCount})` : ''}` : k === 'trending_up' ? 'Up' : 'Down'}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <Card className="border border-slate-100 shadow-sm">
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-3">{[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}</div>
          ) : filtered.length === 0 ? (
            <div className="py-14 text-center" data-testid="pi-empty">
              <BarChart3 className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <h3 className="font-heading text-sm font-bold text-navy-900">No tracked products yet</h3>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                Upload invoices through the extraction pipeline, or click <span className="font-semibold">Backfill from history</span> to ingest existing purchases with canonical pricing.
              </p>
            </div>
          ) : (
            <Table data-testid="pi-products-table">
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[10px]">Product</TableHead>
                  <TableHead className="text-[10px]">Unit</TableHead>
                  <TableHead className="text-[10px] text-right">Latest</TableHead>
                  <TableHead className="text-[10px] text-right">Avg</TableHead>
                  <TableHead className="text-[10px] text-right">Min</TableHead>
                  <TableHead className="text-[10px] text-right">Max</TableHead>
                  <TableHead className="text-[10px]">Trend</TableHead>
                  <TableHead className="text-[10px]">Vendors</TableHead>
                  <TableHead className="text-[10px] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((row) => (
                  <TableRow key={`${row.canonical_product_id}-${row.canonical_unit}`} data-testid={`pi-row-${row.canonical_product_id}`} className="hover:bg-slate-50/50">
                    <TableCell className="max-w-[280px]">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-bold text-navy-900 truncate">{row.canonical_name}</span>
                        {row.alert && <AlertBadge alert={row.alert} />}
                      </div>
                      {row.category && <p className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">{row.category}</p>}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] font-mono border-teal-200 text-teal-700 bg-teal-50">
                        $/{row.canonical_unit}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-xs font-semibold">{fmtPrice(row.stats?.latest)}</TableCell>
                    <TableCell className="text-right tabular-nums text-xs text-slate-600">{fmtPrice(row.stats?.avg)}</TableCell>
                    <TableCell className="text-right tabular-nums text-xs text-emerald-700">{fmtPrice(row.stats?.min)}</TableCell>
                    <TableCell className="text-right tabular-nums text-xs text-red-600">{fmtPrice(row.stats?.max)}</TableCell>
                    <TableCell><TrendBadge trend={row.trend} /></TableCell>
                    <TableCell className="text-xs text-slate-500">{row.vendor_count} · {(row.vendors || []).slice(0, 2).join(', ')}{(row.vendors || []).length > 2 ? '…' : ''}</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px]" onClick={() => setSelected(row)} data-testid={`pi-details-btn-${row.canonical_product_id}`}>
                        Details <ArrowRight className="w-3 h-3 ml-1" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <PriceDetailModal api={api} item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
