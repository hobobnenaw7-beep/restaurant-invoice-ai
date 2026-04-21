/**
 * Milestone 5 — Procurement Decisions Page
 * =========================================
 * Dedicated tab with full list of decisions, filters, and detail cards.
 * Consumes GET /api/procurement/recommendations (all types).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ArrowRightLeft, MessageSquare, Eye, ShieldCheck, Search, RefreshCw,
  Scale, Sparkles, Package,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  FullDecisionCard, TargetPriceModal, REC_CFG,
} from '@/components/procurement/ProcurementUI';
import { PurchaseSuggestionModal } from '@/components/procurement/PurchaseSuggestionModal';

function Kpi({ label, value, icon: Icon, iconBg, sub, testId, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`text-left w-full rounded-xl border transition-all ${active ? 'border-teal-400 shadow-md bg-white' : 'border-slate-100 bg-white hover:border-slate-200'}`}
      data-testid={testId}
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <div className={`w-9 h-9 rounded-xl ${iconBg} flex items-center justify-center flex-shrink-0`}>
          <Icon className="w-4 h-4 text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">{label}</p>
          <p className="text-lg font-heading font-extrabold text-navy-900 leading-tight">{value}</p>
          {sub && <p className="text-[10px] text-slate-400 mt-0.5 truncate">{sub}</p>}
        </div>
      </div>
    </button>
  );
}

export default function ProcurementDecisionsPage() {
  const { api } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ items: [], breakdown: {} });
  const [search, setSearch] = useState('');
  const [actionFilter, setActionFilter] = useState('all');       // all | switch_vendor | renegotiate | monitor_only | no_action
  const [confidenceFilter, setConfidenceFilter] = useState('all'); // all | high | medium | low
  const [riskFilter, setRiskFilter] = useState('all');           // all | low | medium | high
  const [targetFor, setTargetFor] = useState(null);
  const [suggestFor, setSuggestFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/procurement/recommendations');
      setData(res.data || { items: [], breakdown: {} });
    } catch {
      toast.error('Failed to load procurement decisions');
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    let items = data.items || [];
    if (search) {
      const q = search.toLowerCase();
      items = items.filter((i) =>
        (i.canonical_name || '').toLowerCase().includes(q) ||
        (i.current_vendor || '').toLowerCase().includes(q) ||
        (i.best_alternative_vendor || '').toLowerCase().includes(q)
      );
    }
    if (actionFilter !== 'all') items = items.filter((i) => i.recommendation_type === actionFilter);
    if (confidenceFilter !== 'all') items = items.filter((i) => i.confidence_level === confidenceFilter);
    if (riskFilter !== 'all') items = items.filter((i) => i.risk_level === riskFilter);
    return items;
  }, [data, search, actionFilter, confidenceFilter, riskFilter]);

  const bd = data.breakdown || {};
  const totalActionable = (bd.switch_vendor || 0) + (bd.renegotiate || 0);

  return (
    <div className="space-y-6" data-testid="procurement-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-heading text-2xl font-extrabold text-navy-900 tracking-tight flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-teal-600" />
            Procurement Decisions
          </h1>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">
            Decision-support recommendations with evidence, uncertainty, and risk. High-confidence items are actionable; low-confidence items are monitored only.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="gap-1.5" data-testid="proc-refresh-btn">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* KPI filter strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi label="Total" value={data.items?.length || 0} icon={Package} iconBg="bg-slate-600"
             testId="kpi-total" sub={`${totalActionable} actionable`}
             active={actionFilter === 'all'} onClick={() => setActionFilter('all')} />
        <Kpi label="Switch Vendor" value={bd.switch_vendor || 0} icon={ArrowRightLeft} iconBg="bg-emerald-600"
             testId="kpi-switch" sub="high likelihood savings"
             active={actionFilter === 'switch_vendor'} onClick={() => setActionFilter('switch_vendor')} />
        <Kpi label="Renegotiate" value={bd.renegotiate || 0} icon={MessageSquare} iconBg="bg-amber-500"
             testId="kpi-renegotiate" sub="above recent typical"
             active={actionFilter === 'renegotiate'} onClick={() => setActionFilter('renegotiate')} />
        <Kpi label="No Action" value={bd.no_action || 0} icon={ShieldCheck} iconBg="bg-teal-600"
             testId="kpi-noaction" sub="within tolerance"
             active={actionFilter === 'no_action'} onClick={() => setActionFilter('no_action')} />
        <Kpi label="Monitor Only" value={bd.monitor_only || 0} icon={Eye} iconBg="bg-slate-400"
             testId="kpi-monitor" sub="insufficient evidence"
             active={actionFilter === 'monitor_only'} onClick={() => setActionFilter('monitor_only')} />
      </div>

      {/* Filters row */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search product, vendor, alt vendor…"
            className="pl-9 h-9 text-sm"
            data-testid="proc-search"
          />
        </div>
        <FilterGroup
          label="Confidence"
          value={confidenceFilter}
          onChange={setConfidenceFilter}
          options={[
            { k: 'all', l: 'All' },
            { k: 'high', l: 'High' },
            { k: 'medium', l: 'Medium' },
            { k: 'low', l: 'Low' },
          ]}
          testIdPrefix="proc-conf"
        />
        <FilterGroup
          label="Risk"
          value={riskFilter}
          onChange={setRiskFilter}
          options={[
            { k: 'all', l: 'All' },
            { k: 'low', l: 'Low' },
            { k: 'medium', l: 'Medium' },
            { k: 'high', l: 'High' },
          ]}
          testIdPrefix="proc-risk"
        />
      </div>

      {/* List */}
      <div className="space-y-3">
        {loading ? (
          <div className="space-y-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-40 w-full rounded-xl" />)}</div>
        ) : filtered.length === 0 ? (
          <Card className="border border-slate-100 shadow-sm">
            <CardContent className="py-14 text-center" data-testid="proc-empty">
              <Scale className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <h3 className="font-heading text-sm font-bold text-navy-900">No decisions match these filters</h3>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                Adjust the filters above, or upload more invoices so the engine can accumulate evidence.
              </p>
            </CardContent>
          </Card>
        ) : (
          filtered.map((d) => (
            <FullDecisionCard
              key={`${d.canonical_product_id}-${d.canonical_unit}`}
              decision={d}
              onSetTarget={setTargetFor}
              onPrepareSuggestion={setSuggestFor}
              defaultExpanded={d.recommendation_type === 'switch_vendor' || d.recommendation_type === 'renegotiate'}
            />
          ))
        )}
      </div>

      <TargetPriceModal
        api={api}
        decision={targetFor}
        onClose={() => setTargetFor(null)}
        onSaved={load}
      />
      <PurchaseSuggestionModal
        api={api}
        decision={suggestFor}
        onClose={() => setSuggestFor(null)}
      />
    </div>
  );
}

function FilterGroup({ label, value, onChange, options, testIdPrefix }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-slate-400 uppercase tracking-wider font-bold">{label}</span>
      <div className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-lg">
        {options.map((o) => (
          <button
            key={o.k}
            onClick={() => onChange(o.k)}
            className={`text-[11px] font-semibold px-2.5 py-1 rounded-md transition-colors ${
              value === o.k ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-navy-700'
            }`}
            data-testid={`${testIdPrefix}-${o.k}`}
          >
            {o.l}
          </button>
        ))}
      </div>
    </div>
  );
}
