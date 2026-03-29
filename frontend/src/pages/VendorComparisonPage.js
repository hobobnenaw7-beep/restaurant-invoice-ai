import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  Scale, Search, TrendingDown, Package, Users, ChevronDown, ChevronRight, Info
} from 'lucide-react';

function fmtPrice(n) {
  return `$${Number(n || 0).toFixed(4)}`;
}
function fmtCase(n) {
  return `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function StatCard({ icon: Icon, iconBg, label, value, sub, testId }) {
  return (
    <Card className="border border-slate-100 shadow-sm" data-testid={testId}>
      <CardContent className="flex items-center gap-4 py-5 px-5">
        <div className={`w-11 h-11 rounded-xl ${iconBg} flex items-center justify-center flex-shrink-0`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-[11px] text-slate-400 font-medium uppercase tracking-wide">{label}</p>
          <p className="text-xl font-heading font-extrabold text-navy-900 leading-tight">{value}</p>
          {sub && <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function ComparisonGroup({ group, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  const { item_key, comparison_unit, entries, best_price, spread_pct, vendor_count, is_multi_vendor } = group;

  return (
    <div className="border border-slate-100 rounded-xl overflow-hidden" data-testid={`comparison-group-${item_key}`}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-slate-50/70 transition-colors text-left"
        data-testid={`group-toggle-${item_key}`}
      >
        {open ? <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-heading font-bold text-navy-900">{item_key}</span>
        </div>
        <Badge variant="outline" className="text-[10px] font-mono border-teal-200 text-teal-700 bg-teal-50 flex-shrink-0">
          $/{comparison_unit}
        </Badge>
        {is_multi_vendor && (
          <Badge className="text-[10px] bg-amber-100 text-amber-700 flex-shrink-0">
            {vendor_count} vendors
          </Badge>
        )}
        {spread_pct > 0 && (
          <Badge className="text-[10px] bg-emerald-100 text-emerald-700 flex-shrink-0">
            {spread_pct}% spread
          </Badge>
        )}
        <span className="text-xs font-mono font-semibold text-navy-700 flex-shrink-0">
          Best: {fmtPrice(best_price)}/{comparison_unit}
        </span>
      </button>

      {open && (
        <div className="border-t border-slate-100">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50/80 text-[11px] uppercase tracking-wide text-slate-500 font-semibold">
                  <th className="text-left px-4 py-2.5">Vendor</th>
                  <th className="text-left px-4 py-2.5">Raw Item Name</th>
                  <th className="text-left px-4 py-2.5">Pack Size</th>
                  <th className="text-right px-4 py-2.5">Case Price</th>
                  <th className="text-right px-4 py-2.5">Case Weight</th>
                  <th className="text-right px-4 py-2.5">$/LB</th>
                  <th className="text-left px-4 py-2.5">Invoice Date</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => {
                  const isBest = e.normalized_price_per_lb === best_price;
                  return (
                    <tr
                      key={i}
                      className={`border-t border-slate-50 transition-colors ${isBest ? 'bg-emerald-50/50' : 'hover:bg-slate-50/50'}`}
                      data-testid={`entry-row-${item_key}-${i}`}
                    >
                      <td className="px-4 py-2.5 font-medium text-navy-900 whitespace-nowrap">
                        {e.vendor}
                        {isBest && entries.length > 1 && (
                          <Badge className="ml-2 text-[9px] bg-emerald-600 text-white">BEST</Badge>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-slate-600">{e.raw_name}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{e.pack_size_raw}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-700">{fmtCase(e.unit_price)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-500">
                        {e.total_case_weight} {e.pack_unit}
                      </td>
                      <td className={`px-4 py-2.5 text-right font-mono font-bold ${isBest && entries.length > 1 ? 'text-emerald-700' : 'text-navy-900'}`}>
                        {fmtPrice(e.normalized_price_per_lb)}
                      </td>
                      <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{e.invoice_date}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function VendorComparisonPage() {
  const { api } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // 'all' | 'multi' | 'single'

  const load = useCallback(async () => {
    try {
      const res = await api.get('/vendor-comparison/normalized');
      setData(res.data);
    } catch {
      toast.error('Failed to load vendor comparison data');
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let groups = data.comparisons || [];
    if (filter === 'multi') groups = groups.filter(g => g.is_multi_vendor);
    if (filter === 'single') groups = groups.filter(g => !g.is_multi_vendor);
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      groups = groups.filter(g =>
        g.item_key.toLowerCase().includes(q) ||
        g.entries.some(e => e.vendor.toLowerCase().includes(q))
      );
    }
    return groups;
  }, [data, filter, search]);

  if (loading) {
    return (
      <div className="max-w-[1400px] space-y-6" data-testid="vendor-comparison-loading">
        <Skeleton className="h-8 w-72" />
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  const stats = data?.stats || {};
  const hasData = (data?.comparisons || []).length > 0;

  return (
    <div className="max-w-[1400px] space-y-6" data-testid="vendor-comparison-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">
          Vendor Price Comparison
        </h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Normalized $/LB comparison using strictly parsed pack sizes only
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Package}
          iconBg="bg-teal-600"
          label="Qualifying Items"
          value={stats.total_qualifying_items || 0}
          sub="parsed with valid $/LB"
          testId="stat-qualifying"
        />
        <StatCard
          icon={Scale}
          iconBg="bg-indigo-600"
          label="Item Groups"
          value={stats.total_groups || 0}
          sub="distinct items compared"
          testId="stat-groups"
        />
        <StatCard
          icon={Users}
          iconBg="bg-amber-600"
          label="Multi-Vendor Items"
          value={stats.multi_vendor_groups || 0}
          sub="items with 2+ vendors to compare"
          testId="stat-multi-vendor"
        />
        <StatCard
          icon={TrendingDown}
          iconBg="bg-emerald-600"
          label="Vendors Represented"
          value={stats.vendors_represented || 0}
          sub="in qualifying data"
          testId="stat-vendors"
        />
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-slate-50 border border-slate-100" data-testid="comparison-info-banner">
        <Info className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
        <div className="text-[11px] text-slate-500 leading-relaxed">
          <span className="font-semibold text-slate-600">How this works:</span> Only items with successfully parsed pack sizes and LB/OZ units are included.
          Case prices are normalized to <span className="font-mono font-semibold text-teal-700">$/LB</span> for
          apples-to-apples comparison. Items are grouped by exact name match only — no fuzzy merging.
        </div>
      </div>

      {!hasData ? (
        <Card className="border border-slate-100 shadow-sm" data-testid="comparison-empty">
          <CardContent className="flex flex-col items-center py-16 text-center">
            <Scale className="w-12 h-12 text-slate-200 mb-4" />
            <h3 className="text-base font-heading font-bold text-navy-900 mb-1">No comparison data yet</h3>
            <p className="text-sm text-slate-400 max-w-md">
              Add purchase records with pack sizes (e.g., "4/10 LB") from the Expenses page.
              Only items with successfully parsed weights in LB or OZ will appear here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Filters */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                className="pl-9 h-9 text-sm"
                placeholder="Search item or vendor..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                data-testid="comparison-search"
              />
            </div>
            <div className="flex gap-1.5">
              {[
                { key: 'all', label: 'All Items' },
                { key: 'multi', label: 'Multi-Vendor' },
                { key: 'single', label: 'Single Vendor' },
              ].map(f => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                    filter === f.key
                      ? 'bg-navy-900 text-white'
                      : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                  }`}
                  data-testid={`filter-${f.key}`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <Badge variant="outline" className="text-[10px] text-slate-400 ml-auto">
              {filtered.length} group{filtered.length !== 1 ? 's' : ''}
            </Badge>
          </div>

          {/* Comparison groups */}
          <div className="space-y-3" data-testid="comparison-groups-list">
            {filtered.length === 0 ? (
              <div className="text-center py-12 text-sm text-slate-400">
                No items match your search or filter
              </div>
            ) : (
              filtered.map((group, i) => (
                <ComparisonGroup
                  key={group.item_key}
                  group={group}
                  defaultOpen={i < 3}
                />
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
