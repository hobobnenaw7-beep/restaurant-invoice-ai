/**
 * Procurement Command Center — 3-panel consolidated UI.
 * ======================================================
 * LEFT:   Market View     (reuses GET /api/price-intelligence/products)
 * CENTER: Decision Engine (reuses GET /api/procurement/recommendations?only_actionable=true)
 *                          filtered to confidence>=0.8 AND obs>=3, max 7 cards.
 * RIGHT:  Suggestions     (reuses GET /api/procurement/suggestions + low-confidence
 *                          recs from the same recommendations endpoint as "to review")
 *
 * Strict rules:
 *   - ZERO new backend endpoints. Only composes existing APIs.
 *   - Save Insight = opens PurchaseSuggestionModal (user must still acknowledge risk).
 *   - Dismiss = session-local hide (does not mutate any server state).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  TrendingUp, TrendingDown, ArrowRight, Sparkles, Inbox,
  RefreshCw, AlertTriangle, BarChart3, LineChart, Eye,
  Info, Clock, ChevronRight,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  ActionPill, ConfidenceBadge, RiskBadge, fmtPrice, fmtPct, REC_CFG,
} from '@/components/procurement/ProcurementUI';
import { PurchaseSuggestionModal } from '@/components/procurement/PurchaseSuggestionModal';

// ─── Gate: center-panel visibility rule (spec) ─────────────────────
// Show ONLY high confidence (>=0.8) AND >=3 observations, max 7 cards.
const DECISION_MIN_CONFIDENCE = 0.8;
const DECISION_MIN_OBS = 3;
const DECISION_MAX_CARDS = 7;

function relTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  const diff = Date.now() - d.getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ══════════════════════════════════════════════════════════════════
// LEFT PANEL — Market View
// ══════════════════════════════════════════════════════════════════
function MiniSpark({ points }) {
  // Extremely compact SVG sparkline. `points` is array of numbers.
  if (!points || points.length < 2) return <span className="text-[10px] text-slate-300">—</span>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const w = 64, h = 18;
  const step = w / (points.length - 1);
  const coords = points.map((p, i) => `${(i * step).toFixed(1)},${(h - ((p - min) / range) * h).toFixed(1)}`).join(' ');
  const up = points[points.length - 1] > points[0];
  return (
    <svg width={w} height={h} className="flex-shrink-0">
      <polyline
        points={coords}
        fill="none"
        stroke={up ? '#ef4444' : '#10b981'}
        strokeWidth="1.5"
      />
    </svg>
  );
}

function MarketRow({ p }) {
  const last = p.stats?.latest_price;
  const avg = p.stats?.avg_price;
  const trend = p.trend?.trend;
  const hasAlert = p.alert && p.alert.severity;
  const points = (p.trend?.series || []).map(s => Number(s.avg_price || s.price || 0)).filter(Boolean);

  return (
    <div className="flex items-center gap-2.5 py-2 px-2 hover:bg-slate-50/70 rounded-md transition-colors border-b border-slate-50 last:border-0" data-testid={`market-row-${p.canonical_product_id}`}>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-semibold text-navy-900 truncate">{p.canonical_name}</p>
        <p className="text-[10px] text-slate-500 truncate">
          {fmtPrice(last, p.canonical_unit)} <span className="text-slate-300">·</span> avg {fmtPrice(avg)} <span className="text-slate-300">·</span> {p.observation_count || 0} obs
        </p>
      </div>
      <MiniSpark points={points} />
      {trend === 'up' && <TrendingUp className="w-3 h-3 text-red-500 flex-shrink-0" />}
      {trend === 'down' && <TrendingDown className="w-3 h-3 text-emerald-500 flex-shrink-0" />}
      {hasAlert && (
        <Badge className={`text-[9px] font-bold uppercase px-1.5 h-4 ${
          hasAlert === 'high' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
        }`}>
          {hasAlert}
        </Badge>
      )}
    </div>
  );
}

function MarketPanel({ products, loading }) {
  const anomalies = useMemo(() => (products || []).filter(p => p.alert && p.alert.severity), [products]);
  const movers = useMemo(() => {
    return [...(products || [])]
      .filter(p => p.trend?.trend && p.trend.trend !== 'insufficient_data')
      .sort((a, b) => {
        const ra = Math.abs(a.trend?.change_pct || 0);
        const rb = Math.abs(b.trend?.change_pct || 0);
        return rb - ra;
      }).slice(0, 8);
  }, [products]);

  return (
    <div className="bg-white rounded-xl border border-slate-200 flex flex-col h-full" data-testid="panel-market">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-teal-600" />
          <h2 className="text-[13px] font-bold text-navy-900">Market View</h2>
        </div>
        <span className="text-[10px] text-slate-400">{(products || []).length} tracked</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {loading ? (
          [1,2,3,4].map(i => <Skeleton key={i} className="h-10 w-full rounded-md" />)
        ) : (
          <>
            <div>
              <p className="text-[9px] uppercase tracking-wider text-slate-400 font-bold px-2 mb-1">Anomalies · alerts</p>
              {anomalies.length === 0
                ? <p className="text-[11px] text-slate-400 italic px-2 py-2">No active alerts.</p>
                : anomalies.slice(0, 5).map(p => <MarketRow key={`a-${p.canonical_product_id}`} p={p} />)}
            </div>
            <div>
              <p className="text-[9px] uppercase tracking-wider text-slate-400 font-bold px-2 mb-1">Top movers</p>
              {movers.length === 0
                ? <p className="text-[11px] text-slate-400 italic px-2 py-2">No significant trends.</p>
                : movers.map(p => <MarketRow key={`m-${p.canonical_product_id}`} p={p} />)}
            </div>
          </>
        )}
      </div>
      <div className="px-4 py-2 border-t border-slate-100 text-[10px] text-slate-500">
        Compact summary · sourced from <span className="font-semibold">price_history</span>.
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// CENTER PANEL — Decision Engine
// ══════════════════════════════════════════════════════════════════
function DecisionCard({ d, onAccept, onDismiss, onViewDetails }) {
  const cfg = REC_CFG[d.recommendation_type] || REC_CFG.monitor_only;
  const deltaPct = d.price_delta_vs_alternative_pct || d.price_delta_vs_avg_pct || 0;
  const deltaDollar = (() => {
    if (d.best_alternative_price_per_unit != null && d.current_price_per_unit != null) {
      return d.current_price_per_unit - d.best_alternative_price_per_unit;
    }
    return null;
  })();
  return (
    <div
      className={`border rounded-xl p-3.5 ${cfg.border} ${cfg.bgSoft} space-y-2`}
      data-testid={`decision-card-${d.canonical_product_id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-heading text-[13px] font-bold text-navy-900 truncate">{d.canonical_name}</h3>
            <Badge variant="outline" className="text-[9px] font-mono border-teal-200 text-teal-700 bg-teal-50">$/{d.canonical_unit}</Badge>
          </div>
          <p className="text-[11px] text-slate-600 mt-0.5 line-clamp-1">
            <span className="font-medium">{d.current_vendor || 'Unknown'}</span>
            <ArrowRight className="inline w-3 h-3 mx-1 text-slate-400" />
            <span className="font-semibold text-navy-900">{d.best_alternative_vendor || d.recommended_vendor || '—'}</span>
          </p>
        </div>
        <ActionPill type={d.recommendation_type} />
      </div>

      {/* Price summary: latest vs target (spec) */}
      <div className="flex items-center gap-3 text-[11px] flex-wrap">
        <span className="text-slate-500">latest <span className="font-bold text-navy-900 tabular-nums">{fmtPrice(d.current_price_per_unit, d.canonical_unit)}</span></span>
        {d.target_price_per_unit != null && (
          <span className="text-slate-500">· target <span className="font-semibold text-slate-700 tabular-nums">{fmtPrice(d.target_price_per_unit)}</span></span>
        )}
        {deltaDollar != null && (
          <span className={`font-bold tabular-nums ${deltaDollar > 0 ? 'text-emerald-600' : 'text-slate-500'}`}>
            Δ {deltaDollar > 0 ? '-' : ''}{fmtPrice(Math.abs(deltaDollar))} ({fmtPct(Math.abs(deltaPct))})
          </span>
        )}
      </div>

      {/* 1-line reason */}
      <p className="text-[11px] text-slate-600 leading-snug line-clamp-2 italic">{d.reason_summary}</p>

      <div className="flex items-center gap-1 flex-wrap">
        <RiskBadge level={d.risk_level} />
        <ConfidenceBadge level={d.confidence_level} score={d.decision_confidence} />
        <span className="text-[10px] text-slate-400 ml-1">{d.observation_count} obs</span>
      </div>

      <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-200/70">
        <button
          onClick={() => onViewDetails(d)}
          className="text-[11px] font-semibold text-teal-700 hover:text-teal-800 inline-flex items-center gap-1"
          data-testid={`decision-view-details-${d.canonical_product_id}`}
        >
          <Eye className="w-3 h-3" /> View details
        </button>
        <div className="flex items-center gap-1.5">
          <Button
            size="sm" variant="outline"
            className="h-7 px-2.5 text-[10px] gap-1 border-slate-300 text-slate-600"
            onClick={() => onDismiss(d)}
            data-testid={`decision-review-later-${d.canonical_product_id}`}
          >
            <Clock className="w-3 h-3" /> Review Later
          </Button>
          <Button
            size="sm"
            className="h-7 px-3 text-[10px] gap-1 bg-teal-600 hover:bg-teal-700"
            onClick={() => onAccept(d)}
            data-testid={`decision-save-insight-${d.canonical_product_id}`}
          >
            <Sparkles className="w-3 h-3" /> Save Insight
          </Button>
        </div>
      </div>
    </div>
  );
}

function DecisionEnginePanel({ decisions, loading, onAccept, onDismiss, onViewDetails, onRefresh }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 flex flex-col h-full" data-testid="panel-decisions">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-teal-600" />
          <h2 className="text-[13px] font-bold text-navy-900">Decision Engine</h2>
          <Badge className="bg-teal-100 text-teal-700 text-[9px] font-bold">{decisions.length}</Badge>
        </div>
        <button
          onClick={onRefresh}
          className="text-slate-400 hover:text-slate-600 transition-colors"
          data-testid="decisions-refresh-btn"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      <div className="px-4 py-2 bg-teal-50/40 border-b border-teal-100 text-[10px] text-teal-800 flex items-start gap-1.5">
        <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
        <span>Only high-confidence items (score ≥ 0.80, ≥ 3 observations) — top {DECISION_MAX_CARDS}. <strong>Save Insight</strong> opens the acknowledgment modal. <strong>Review Later</strong> is session-only — advisory only, no purchase is executed.</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading ? (
          [1,2,3].map(i => <Skeleton key={i} className="h-28 w-full rounded-xl" />)
        ) : decisions.length === 0 ? (
          <div className="text-center py-10" data-testid="decisions-empty">
            <Sparkles className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-sm font-semibold text-navy-900">No high-confidence decisions right now</p>
            <p className="text-xs text-slate-400 mt-1">Upload more invoices to accumulate evidence.</p>
          </div>
        ) : (
          decisions.map(d => (
            <DecisionCard
              key={`${d.canonical_product_id}-${d.canonical_unit}`}
              d={d}
              onAccept={onAccept}
              onDismiss={onDismiss}
              onViewDetails={onViewDetails}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── Decision details modal (reuses existing decision payload) ─────
function DecisionDetailsModal({ decision, onClose }) {
  if (!decision) return null;
  return (
    <Dialog open={!!decision} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl" data-testid="decision-details-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-heading">
            <LineChart className="w-4 h-4 text-teal-600" /> {decision.canonical_name}
          </DialogTitle>
          <DialogDescription className="text-[11px] text-slate-500">{decision.reason_summary}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-50 border border-slate-100 rounded-lg p-2.5">
              <p className="text-[9px] uppercase tracking-wider text-slate-400 font-bold">Current</p>
              <p className="text-sm font-bold text-navy-900 tabular-nums">{fmtPrice(decision.current_price_per_unit, decision.canonical_unit)}</p>
              <p className="text-[10px] text-slate-500">{decision.current_vendor || '—'}</p>
            </div>
            <div className="bg-slate-50 border border-slate-100 rounded-lg p-2.5">
              <p className="text-[9px] uppercase tracking-wider text-slate-400 font-bold">Best alternative</p>
              <p className="text-sm font-bold text-emerald-700 tabular-nums">
                {decision.best_alternative_price_per_unit != null ? fmtPrice(decision.best_alternative_price_per_unit, decision.canonical_unit) : '—'}
              </p>
              <p className="text-[10px] text-slate-500">{decision.best_alternative_vendor || '—'} ({decision.best_alternative_observations || 0} obs)</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-white border border-slate-100 rounded-lg p-2">
              <p className="text-[9px] uppercase text-slate-400">vs avg</p>
              <p className="text-sm font-bold tabular-nums">{fmtPct(decision.price_delta_vs_avg_pct)}</p>
            </div>
            <div className="bg-white border border-slate-100 rounded-lg p-2">
              <p className="text-[9px] uppercase text-slate-400">vs target</p>
              <p className="text-sm font-bold tabular-nums">{fmtPct(decision.price_delta_vs_target_pct)}</p>
            </div>
            <div className="bg-white border border-slate-100 rounded-lg p-2">
              <p className="text-[9px] uppercase text-slate-400">vs alt</p>
              <p className="text-sm font-bold tabular-nums">{fmtPct(decision.price_delta_vs_alternative_pct)}</p>
            </div>
          </div>

          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold mb-1 flex items-center gap-1">
              <TrendingUp className="w-3 h-3" /> Evidence ({decision.evidence?.length || 0})
            </p>
            <ul className="text-[11px] text-slate-600 space-y-1 pl-4 list-disc marker:text-emerald-500">
              {(decision.evidence || []).map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>

          {decision.uncertainty?.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold mb-1 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Uncertainty ({decision.uncertainty.length})
              </p>
              <ul className="text-[11px] text-slate-600 space-y-1 pl-4 list-disc marker:text-amber-500">
                {decision.uncertainty.map((u, i) => <li key={i}>{u}</li>)}
              </ul>
            </div>
          )}

          <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
            <ActionPill type={decision.recommendation_type} />
            <RiskBadge level={decision.risk_level} />
            <ConfidenceBadge level={decision.confidence_level} score={decision.decision_confidence} />
            <span className="text-[10px] text-slate-400">· {decision.observation_count} good observations</span>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="decision-details-close">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ══════════════════════════════════════════════════════════════════
// RIGHT PANEL — Triage (Needs Review / Low Confidence / Missing Data)
// ══════════════════════════════════════════════════════════════════
function ReviewRow({ d, onPromote, category }) {
  const labels = { needs_review: 'needs review', low_confidence: 'low conf', missing_data: 'missing data' };
  const cls = {
    needs_review:   'border-amber-200 bg-amber-50/40',
    low_confidence: 'border-slate-200 bg-slate-50/40',
    missing_data:   'border-slate-200 bg-white',
  }[category] || 'border-slate-200 bg-white';
  const badgeCls = {
    needs_review:   'bg-amber-100 text-amber-700',
    low_confidence: 'bg-slate-200 text-slate-700',
    missing_data:   'bg-slate-100 text-slate-500',
  }[category] || 'bg-slate-100 text-slate-600';

  return (
    <div className={`border rounded-lg p-2.5 space-y-1.5 ${cls}`} data-testid={`right-review-row-${d.canonical_product_id}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-semibold text-navy-900 truncate">{d.canonical_name}</p>
          <p className="text-[10px] text-slate-500 truncate">
            {d.current_vendor || '—'}{d.best_alternative_vendor && <> · alt {d.best_alternative_vendor}</>}
          </p>
        </div>
        <Badge className={`text-[9px] font-bold uppercase h-4 ${badgeCls}`}>{labels[category] || 'review'}</Badge>
      </div>
      <p className="text-[10px] text-slate-500 line-clamp-2 italic">{d.reason_summary}</p>
      <div className="flex items-center justify-between pt-1 border-t border-slate-100">
        <span className="text-[9px] text-slate-400">{d.observation_count || 0} obs</span>
        <Button
          size="sm" variant="ghost"
          className="h-6 px-2 text-[10px] gap-1 text-teal-700 hover:bg-teal-50"
          onClick={() => onPromote(d)}
          data-testid={`right-promote-btn-${d.canonical_product_id}`}
        >
          <ChevronRight className="w-3 h-3" /> Promote
        </Button>
      </div>
    </div>
  );
}

// Mutually-exclusive triage: missing_data wins over low_confidence wins over needs_review.
function triageBucket(d) {
  const obs = d.observation_count || 0;
  const conf = (d.confidence_level || '').toLowerCase();
  if (d.recommendation_type === 'monitor_only' || obs < DECISION_MIN_OBS || !conf) return 'missing_data';
  if (conf === 'low') return 'low_confidence';
  return 'needs_review'; // medium-confidence or otherwise-kept-out-of-center
}

function SuggestionsPanel({ reviewDecisions, loading, onPromote, onRefresh }) {
  const [tab, setTab] = useState('needs_review');
  const grouped = useMemo(() => {
    const out = { needs_review: [], low_confidence: [], missing_data: [] };
    (reviewDecisions || []).forEach(d => { out[triageBucket(d)].push(d); });
    return out;
  }, [reviewDecisions]);
  const items = grouped[tab] || [];

  return (
    <div className="bg-white rounded-xl border border-slate-200 flex flex-col h-full" data-testid="panel-suggestions">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Inbox className="w-4 h-4 text-teal-600" />
          <h2 className="text-[13px] font-bold text-navy-900">Triage</h2>
        </div>
        <button
          onClick={onRefresh}
          className="text-slate-400 hover:text-slate-600 transition-colors"
          data-testid="suggestions-refresh-btn"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-1 p-0.5 mx-3 mt-3 bg-slate-100 rounded-lg" role="tablist">
        {[
          { k: 'needs_review',   label: 'Needs Review' },
          { k: 'low_confidence', label: 'Low Conf.' },
          { k: 'missing_data',   label: 'Missing Data' },
        ].map(t => (
          <button
            key={t.k}
            onClick={() => setTab(t.k)}
            className={`text-[10px] font-semibold px-1.5 py-1 rounded-md transition-colors ${tab === t.k ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500'}`}
            data-testid={`right-tab-${t.k.replace(/_/g, '-')}`}
          >
            {t.label} ({grouped[t.k].length})
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading ? (
          [1,2,3].map(i => <Skeleton key={i} className="h-16 w-full rounded-lg" />)
        ) : items.length === 0 ? (
          <div className="text-center py-10" data-testid={`right-empty-${tab.replace(/_/g, '-')}`}>
            <Inbox className="w-7 h-7 text-slate-300 mx-auto mb-2" />
            <p className="text-xs text-slate-400">
              {tab === 'needs_review'   && 'Nothing currently needs review.'}
              {tab === 'low_confidence' && 'No low-confidence items right now.'}
              {tab === 'missing_data'   && 'All tracked items have enough data.'}
            </p>
          </div>
        ) : (
          items.map(d => <ReviewRow key={d.canonical_product_id} d={d} onPromote={onPromote} category={tab} />)
        )}
      </div>

      <div className="px-4 py-2 border-t border-slate-100 text-[10px] text-slate-500 flex items-center justify-between">
        <span>Live triage · advisory only</span>
        <Link to="/procurement/history" className="text-teal-700 hover:underline font-semibold" data-testid="right-history-link">
          Saved history →
        </Link>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// PAGE
// ══════════════════════════════════════════════════════════════════
export default function ProcurementCommandCenterPage() {
  const { api } = useAuth();
  const [loadingMarket, setLoadingMarket] = useState(true);
  const [loadingRecs, setLoadingRecs] = useState(true);
  const [loadingSuggestions, setLoadingSuggestions] = useState(true);
  const [products, setProducts] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [dismissed, setDismissed] = useState(() => new Set()); // session-only
  const [preparing, setPreparing] = useState(null);  // PurchaseSuggestionModal
  const [detailsFor, setDetailsFor] = useState(null); // DecisionDetailsModal

  // ─ Load Market ────────────────────────────────────────────────
  const loadMarket = useCallback(async () => {
    setLoadingMarket(true);
    try {
      const r = await api.get('/price-intelligence/products');
      setProducts(r.data?.items || r.data || []);
    } catch { toast.error('Failed to load market view'); }
    finally { setLoadingMarket(false); }
  }, [api]);

  // ─ Load Recommendations (all; we'll filter locally for two panels) ─
  const loadRecs = useCallback(async () => {
    setLoadingRecs(true);
    try {
      const r = await api.get('/procurement/recommendations');
      setRecommendations(r.data?.items || []);
    } catch { toast.error('Failed to load decisions'); }
    finally { setLoadingRecs(false); }
  }, [api]);

  // ─ Saved count (small metric; live history lives at /procurement/history) ─
  const loadSavedCount = useCallback(async () => {
    setLoadingSuggestions(true);
    try {
      const r = await api.get('/procurement/suggestions?status=saved_for_review');
      setSuggestions(r.data?.items || []);
    } catch { /* silent */ }
    finally { setLoadingSuggestions(false); }
  }, [api]);

  useEffect(() => { loadMarket(); loadRecs(); loadSavedCount(); }, [loadMarket, loadRecs, loadSavedCount]);

  // ─ Center panel: filter + cap ────────────────────────────────
  const centerDecisions = useMemo(() => {
    return (recommendations || [])
      .filter(d => !dismissed.has(d.canonical_product_id))
      .filter(d => ['switch_vendor', 'renegotiate'].includes(d.recommendation_type))
      .filter(d => (d.decision_confidence || 0) >= DECISION_MIN_CONFIDENCE)
      .filter(d => (d.observation_count || 0) >= DECISION_MIN_OBS)
      .slice(0, DECISION_MAX_CARDS);
  }, [recommendations, dismissed]);

  // ─ Right panel: everything NOT in center — triaged by SuggestionsPanel ──
  const reviewDecisions = useMemo(() => {
    return (recommendations || [])
      .filter(d => !centerDecisions.find(c => c.canonical_product_id === d.canonical_product_id))
      .slice(0, 20);
  }, [recommendations, centerDecisions]);

  // ─ Handlers ──────────────────────────────────────────────────
  const handleAccept = (d) => setPreparing(d);
  const handleDismiss = (d) => {
    setDismissed(prev => new Set(prev).add(d.canonical_product_id));
    toast.info('Saved for later review (session only)');
  };
  const handlePromote = (d) => setPreparing(d);
  const handleViewDetails = (d) => setDetailsFor(d);

  const refreshAll = () => { loadMarket(); loadRecs(); loadSavedCount(); };

  // ─ Panel focus from URL ?panel=market|decisions|suggestions ────
  const [searchParams] = useSearchParams();
  const panelParam = searchParams.get('panel');
  const focus = ['market', 'decisions', 'suggestions'].includes(panelParam) ? panelParam : null;
  const marketRef = useRef(null);
  const decisionsRef = useRef(null);
  const suggestionsRef = useRef(null);
  useEffect(() => {
    if (!focus) return;
    const el = { market: marketRef, decisions: decisionsRef, suggestions: suggestionsRef }[focus]?.current;
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [focus]);
  const focusRing = (key) => focus === key
    ? 'ring-2 ring-teal-400/70 ring-offset-2 ring-offset-slate-50 rounded-xl transition-shadow'
    : '';

  return (
    <div className="space-y-4" data-testid="procurement-command-center">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-heading text-2xl font-extrabold text-navy-900 tracking-tight flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-teal-600" />
            Procurement
          </h1>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">
            Market signals, high-confidence insights, and live triage — what needs action right now.
            Advisory only: no purchases are executed from this page.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            to="/procurement/history"
            className="text-[11px] font-semibold text-teal-700 hover:text-teal-800 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-teal-200 hover:bg-teal-50 transition-colors"
            data-testid="cc-history-link"
          >
            Saved history
            {suggestions.length > 0 && (
              <span className="ml-1 bg-teal-600 text-white text-[9px] font-bold px-1.5 py-[1px] rounded-full">{suggestions.length}</span>
            )}
            <ChevronRight className="w-3 h-3" />
          </Link>
          <Button variant="outline" size="sm" onClick={refreshAll} className="gap-1.5" data-testid="cc-refresh-btn">
            <RefreshCw className={`w-3.5 h-3.5 ${(loadingMarket || loadingRecs || loadingSuggestions) ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* 3-panel grid. Mobile: stacked. Desktop: 3 columns. */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[calc(100vh-210px)] min-h-[520px]">
        <div ref={marketRef} className={`lg:col-span-3 ${focusRing('market')}`} data-testid="panel-market-wrap" data-panel-focus={focus === 'market' ? 'true' : 'false'}>
          <MarketPanel products={products} loading={loadingMarket} />
        </div>
        <div ref={decisionsRef} className={`lg:col-span-6 ${focusRing('decisions')}`} data-testid="panel-decisions-wrap" data-panel-focus={focus === 'decisions' ? 'true' : 'false'}>
          <DecisionEnginePanel
            decisions={centerDecisions}
            loading={loadingRecs}
            onAccept={handleAccept}
            onDismiss={handleDismiss}
            onViewDetails={handleViewDetails}
            onRefresh={loadRecs}
          />
        </div>
        <div ref={suggestionsRef} className={`lg:col-span-3 ${focusRing('suggestions')}`} data-testid="panel-suggestions-wrap" data-panel-focus={focus === 'suggestions' ? 'true' : 'false'}>
          <SuggestionsPanel
            reviewDecisions={reviewDecisions}
            loading={loadingRecs}
            onPromote={handlePromote}
            onRefresh={loadRecs}
          />
        </div>
      </div>

      {/* Utility link to Orders page */}
      <div className="text-[11px] text-slate-400 flex items-center gap-1 justify-end">
        Looking to place an order? <Link to="/orders" className="text-teal-700 hover:underline font-semibold ml-1" data-testid="cc-orders-link">Go to Orders →</Link>
      </div>

      {/* Modals (reused from existing components) */}
      <PurchaseSuggestionModal api={api} decision={preparing} onClose={() => { setPreparing(null); loadSavedCount(); }} />
      <DecisionDetailsModal decision={detailsFor} onClose={() => setDetailsFor(null)} />
    </div>
  );
}
