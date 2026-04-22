/**
 * Milestone 7 — Saved Suggestions Inbox (Feedback Loop)
 * ======================================================
 * /procurement/inbox — list of saved advisory suggestions with outcome actions.
 *
 * Strict rules:
 *   - No purchasing actions, no vendor communication.
 *   - Only updates user outcomes for engine calibration.
 *   - Once a suggestion is acted_on / not_pursued, it leaves the unresolved queue.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import {
  CheckCircle2, XCircle, Inbox, Search, RefreshCw, ArrowRight, Clock, FileText, Sparkles, ChevronRight,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  ActionPill, ConfidenceBadge, RiskBadge, fmtPrice,
} from '@/components/procurement/ProcurementUI';

const STATUS_CFG = {
  saved_for_review: { label: 'Saved for review', bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', dot: 'bg-amber-500' },
  acted_on:         { label: 'Acted on',         bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500' },
  not_pursued:      { label: 'Not pursued',      bg: 'bg-slate-100', text: 'text-slate-600', border: 'border-slate-200', dot: 'bg-slate-400' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.saved_for_review;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wider ${cfg.bg} ${cfg.text} ${cfg.border}`} data-testid={`status-badge-${status}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

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
  const days = Math.floor(h / 24);
  return `${days}d ago`;
}

// ── Row ────────────────────────────────────────────────────────────────
function SuggestionRow({ s, onActOn, onNotPursued }) {
  const unresolved = s.status === 'saved_for_review';
  return (
    <div
      className={`border rounded-xl p-4 bg-white hover:border-slate-300 transition-colors ${
        unresolved ? 'border-amber-200' : 'border-slate-100'
      }`}
      data-testid={`inbox-row-${s.id}`}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h3 className="font-heading text-sm font-bold text-navy-900 truncate">
              {s.canonical_name || 'Unknown product'}
            </h3>
            <Badge variant="outline" className="text-[9px] font-mono border-teal-200 text-teal-700 bg-teal-50">
              $/{s.canonical_unit}
            </Badge>
            <StatusBadge status={s.status || 'saved_for_review'} />
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-600 flex-wrap mb-2">
            <span className="truncate">{s.current_vendor || 'Unknown vendor'}</span>
            <ArrowRight className="w-3 h-3 text-slate-400 flex-shrink-0" />
            <span className="font-semibold text-navy-900 truncate">{s.recommended_vendor || '—'}</span>
            {s.current_price_per_unit && (
              <span className="tabular-nums text-slate-400 ml-1">
                ({fmtPrice(s.current_price_per_unit, s.canonical_unit)}
                {s.reference_price_per_unit && <> → {fmtPrice(s.reference_price_per_unit, s.canonical_unit)}</>})
              </span>
            )}
          </div>
          {s.reason_summary && (
            <p className="text-[11px] text-slate-500 italic line-clamp-2">{s.reason_summary}</p>
          )}
          {s.outcome_note && (
            <div className="mt-2 bg-slate-50 border-l-2 border-slate-300 pl-2 py-1">
              <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold mb-0.5">Rejection note</p>
              <p className="text-[11px] text-slate-600 italic">"{s.outcome_note}"</p>
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
          <ActionPill type={s.recommendation_type} />
          <div className="flex items-center gap-1">
            <RiskBadge level={s.risk_level} />
            <ConfidenceBadge level={s.confidence_level} score={s.decision_confidence} />
          </div>
        </div>
      </div>

      <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-3 text-[10px] text-slate-400">
          <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3" /> saved {relTime(s.created_at)}</span>
          {s.outcome_at && (
            <span className="inline-flex items-center gap-1">
              {s.status === 'acted_on' ? <CheckCircle2 className="w-3 h-3 text-emerald-500" /> : <XCircle className="w-3 h-3 text-slate-400" />}
              resolved {relTime(s.outcome_at)} {s.outcome_by_user_name && `by ${s.outcome_by_user_name}`}
            </span>
          )}
        </div>
        {unresolved && (
          <div className="flex items-center gap-1.5">
            <Button
              size="sm" variant="outline"
              className="h-7 px-2.5 text-[10px] gap-1 border-slate-300 hover:border-slate-400 text-slate-600"
              onClick={() => onNotPursued(s)}
              data-testid={`inbox-not-pursued-btn-${s.id}`}
            >
              <XCircle className="w-3 h-3" /> Not Pursued
            </Button>
            <Button
              size="sm"
              className="h-7 px-3 text-[10px] gap-1 bg-emerald-600 hover:bg-emerald-700"
              onClick={() => onActOn(s)}
              data-testid={`inbox-acted-on-btn-${s.id}`}
            >
              <CheckCircle2 className="w-3 h-3" /> Marked as Acted On
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Not Pursued reason modal ──────────────────────────────────────────
function NotPursuedModal({ suggestion, onClose, onSubmit, submitting }) {
  const [note, setNote] = useState('');
  useEffect(() => { if (!suggestion) setNote(''); }, [suggestion]);
  if (!suggestion) return null;
  return (
    <Dialog open={!!suggestion} onOpenChange={onClose}>
      <DialogContent className="max-w-md" data-testid="not-pursued-modal">
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-2 text-base">
            <XCircle className="w-4 h-4 text-slate-500" />
            Mark as not pursued
          </DialogTitle>
          <DialogDescription className="text-[11px] text-slate-500">
            Optional: briefly note why this suggestion wasn't pursued. This feedback helps
            calibrate the engine over time. No purchasing or vendor action is taken.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <div className="bg-slate-50 border border-slate-100 rounded-lg px-3 py-2">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Suggestion</p>
            <p className="text-sm font-semibold text-navy-900">{suggestion.canonical_name}</p>
            <p className="text-[11px] text-slate-500">{suggestion.current_vendor} → {suggestion.recommended_vendor}</p>
          </div>
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. contract already signed, quality concerns, minimum order not met…"
            className="text-xs min-h-[90px]"
            data-testid="not-pursued-note-input"
          />
          <p className="text-[10px] text-slate-400">Optional — you can leave this blank.</p>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={submitting} data-testid="not-pursued-cancel-btn">Cancel</Button>
          <Button
            onClick={() => onSubmit(note)}
            disabled={submitting}
            className="bg-slate-700 hover:bg-slate-800 gap-1.5"
            data-testid="not-pursued-confirm-btn"
          >
            {submitting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
            Confirm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Page ───────────────────────────────────────────────────────────────
export default function ProcurementInboxPage() {
  const { api } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ items: [], breakdown: {} });
  const [search, setSearch] = useState('');
  const [tab, setTab] = useState('saved_for_review'); // saved_for_review | acted_on | not_pursued
  const [npFor, setNpFor] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/procurement/suggestions');
      setData(res.data || { items: [], breakdown: {} });
    } catch {
      toast.error('Failed to load saved suggestions');
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    let items = data.items || [];
    items = items.filter((i) => (i.status || 'saved_for_review') === tab);
    if (search) {
      const q = search.toLowerCase();
      items = items.filter((i) =>
        (i.canonical_name || '').toLowerCase().includes(q) ||
        (i.current_vendor || '').toLowerCase().includes(q) ||
        (i.recommended_vendor || '').toLowerCase().includes(q)
      );
    }
    return items;
  }, [data, tab, search]);

  const patchOutcome = async (suggestion, outcome_type, outcome_note = '') => {
    setSubmitting(true);
    try {
      await api.patch(`/procurement/suggestions/${suggestion.id}/outcome`, {
        outcome_type,
        outcome_note,
      });
      const label = outcome_type === 'acted_on' ? 'Marked as acted on' : 'Marked as not pursued';
      toast.success(label);
      setNpFor(null);
      await load();
    } catch {
      toast.error('Could not update outcome');
    } finally {
      setSubmitting(false);
    }
  };

  const onActOn = (s) => patchOutcome(s, 'acted_on');

  const bd = data.breakdown || {};

  return (
    <div className="space-y-6" data-testid="procurement-inbox-page">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 text-[11px] text-slate-500" data-testid="history-breadcrumb">
        <Link to="/procurement" className="hover:text-navy-900 transition-colors">Procurement</Link>
        <ChevronRight className="w-3 h-3 text-slate-300" />
        <span className="font-semibold text-navy-900">Saved History</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-heading text-2xl font-extrabold text-navy-900 tracking-tight flex items-center gap-2">
            <Inbox className="w-5 h-5 text-teal-600" />
            Saved History
          </h1>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">
            Insights you saved and the outcomes you recorded. This is a reference /
            audit view — the live action screen is <Link to="/procurement" className="text-teal-700 hover:underline font-semibold">Procurement</Link>.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="gap-1.5" data-testid="inbox-refresh-btn">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-lg" role="tablist">
          {[
            { k: 'saved_for_review', l: 'Saved for review', icon: FileText },
            { k: 'acted_on', l: 'Acted on', icon: CheckCircle2 },
            { k: 'not_pursued', l: 'Not pursued', icon: XCircle },
          ].map(({ k, l, icon: Icon }) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`flex items-center gap-1.5 text-[11px] font-semibold px-3 py-1.5 rounded-md transition-colors ${
                tab === k ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-navy-700'
              }`}
              data-testid={`inbox-tab-${k}`}
            >
              <Icon className="w-3.5 h-3.5" />
              {l}
              <span className={`ml-1 px-1.5 rounded-full text-[9px] font-bold ${tab === k ? 'bg-teal-100 text-teal-700' : 'bg-slate-200 text-slate-500'}`}>
                {bd[k] || 0}
              </span>
            </button>
          ))}
        </div>
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search product or vendor…"
            className="pl-9 h-9 text-sm"
            data-testid="inbox-search"
          />
        </div>
      </div>

      {/* List */}
      <div className="space-y-3">
        {loading ? (
          <div className="space-y-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}</div>
        ) : filtered.length === 0 ? (
          <Card className="border border-slate-100 shadow-sm">
            <CardContent className="py-14 text-center" data-testid="inbox-empty">
              <Sparkles className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <h3 className="font-heading text-sm font-bold text-navy-900">No suggestions in this tab</h3>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                {tab === 'saved_for_review'
                  ? 'When you save a draft from Procurement Decisions, it will show up here.'
                  : tab === 'acted_on'
                    ? 'Drafts you mark as acted on will be listed here for calibration.'
                    : 'Drafts you choose not to pursue will be listed here with any rejection notes.'}
              </p>
            </CardContent>
          </Card>
        ) : (
          filtered.map((s) => (
            <SuggestionRow
              key={s.id}
              s={s}
              onActOn={onActOn}
              onNotPursued={setNpFor}
            />
          ))
        )}
      </div>

      <NotPursuedModal
        suggestion={npFor}
        onClose={() => setNpFor(null)}
        onSubmit={(note) => patchOutcome(npFor, 'not_pursued', note)}
        submitting={submitting}
      />
    </div>
  );
}
