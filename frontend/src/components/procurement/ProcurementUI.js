/**
 * Milestone 5 — Shared Procurement UI components
 * ================================================
 * Exports small, pure presentational pieces used by both the inline summary
 * panel (inside Price Intelligence) and the dedicated Procurement page.
 */
import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import {
  ShieldCheck, ShieldAlert, Shield, AlertTriangle,
  RefreshCw, Target, DollarSign, ArrowRightLeft, Eye, MessageSquare,
  TrendingUp, TrendingDown, Sparkles,
} from 'lucide-react';

// ── helpers ────────────────────────────────────────────────────────────
export const fmtPrice = (n, unit = '') =>
  n === null || n === undefined ? '—' : `$${Number(n).toFixed(2)}${unit ? `/${unit}` : ''}`;
export const fmtPct = (n) => (n === null || n === undefined ? '—' : `${Number(n).toFixed(1)}%`);

// ── Recommendation type config ─────────────────────────────────────────
export const REC_CFG = {
  switch_vendor: {
    label: 'Switch Vendor',
    icon: ArrowRightLeft,
    bg: 'bg-emerald-600', bgSoft: 'bg-emerald-50',
    text: 'text-white', textSoft: 'text-emerald-700',
    border: 'border-emerald-200',
  },
  renegotiate: {
    label: 'Renegotiate',
    icon: MessageSquare,
    bg: 'bg-amber-500', bgSoft: 'bg-amber-50',
    text: 'text-white', textSoft: 'text-amber-700',
    border: 'border-amber-200',
  },
  monitor_only: {
    label: 'Monitor',
    icon: Eye,
    bg: 'bg-slate-400', bgSoft: 'bg-slate-50',
    text: 'text-white', textSoft: 'text-slate-600',
    border: 'border-slate-200',
  },
  no_action: {
    label: 'No Action',
    icon: ShieldCheck,
    bg: 'bg-teal-600', bgSoft: 'bg-teal-50',
    text: 'text-white', textSoft: 'text-teal-700',
    border: 'border-teal-200',
  },
};

export const CONF_CFG = {
  high:   { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500', icon: ShieldCheck, label: 'HIGH' },
  medium: { bg: 'bg-amber-100',   text: 'text-amber-700',   border: 'border-amber-200',   dot: 'bg-amber-500',   icon: ShieldAlert, label: 'MEDIUM' },
  low:    { bg: 'bg-red-100',     text: 'text-red-700',     border: 'border-red-200',     dot: 'bg-red-500',     icon: Shield,      label: 'LOW' },
};

export const RISK_CFG = {
  low:    { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', label: 'LOW RISK' },
  medium: { bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200',   label: 'MEDIUM RISK' },
  high:   { bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',     label: 'HIGH RISK' },
};

// ── Action Pill ────────────────────────────────────────────────────────
export function ActionPill({ type }) {
  const cfg = REC_CFG[type] || REC_CFG.monitor_only;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${cfg.bg} ${cfg.text}`} data-testid={`action-pill-${type}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

// ── Confidence Badge ───────────────────────────────────────────────────
export function ConfidenceBadge({ level, score }) {
  if (!level) return null;
  const cfg = CONF_CFG[level] || CONF_CFG.low;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold ${cfg.bg} ${cfg.text} ${cfg.border}`} data-testid={`conf-badge-${level}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      <Icon className="w-3 h-3" />
      {cfg.label}{score !== undefined && ` · ${Number(score).toFixed(2)}`}
    </span>
  );
}

// ── Risk Badge ─────────────────────────────────────────────────────────
export function RiskBadge({ level }) {
  if (!level) return null;
  const cfg = RISK_CFG[level] || RISK_CFG.medium;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold ${cfg.bg} ${cfg.text} ${cfg.border}`} data-testid={`risk-badge-${level}`}>
      {cfg.label}
    </span>
  );
}

// ── Price-context chips (delta vs avg / target / alt) ──────────────────
export function DeltaRow({ decision }) {
  const rows = [
    { label: 'vs Avg',   value: decision.price_delta_vs_avg_pct, ref: decision.historical_average_price_per_unit, refLabel: 'avg' },
    { label: 'vs Target', value: decision.price_delta_vs_target_pct, ref: decision.target_price_per_unit, refLabel: 'target' },
    { label: 'vs Alt',    value: decision.price_delta_vs_alternative_pct, ref: decision.best_alternative_price_per_unit, refLabel: decision.best_alternative_vendor },
  ];
  const u = decision.canonical_unit || 'unit';
  return (
    <div className="grid grid-cols-3 gap-2">
      {rows.map((r) => {
        const isUp = r.value !== null && r.value !== undefined && r.value > 0;
        const isDown = r.value !== null && r.value !== undefined && r.value < 0;
        return (
          <div key={r.label} className="bg-slate-50 border border-slate-100 rounded-lg px-2.5 py-1.5" data-testid={`delta-${r.label.toLowerCase().replace(' ','-')}`}>
            <p className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">{r.label}</p>
            <p className={`text-sm tabular-nums font-bold ${isUp ? 'text-red-600' : isDown ? 'text-emerald-600' : 'text-slate-500'}`}>
              {r.value === null || r.value === undefined ? '—' : `${r.value > 0 ? '+' : ''}${fmtPct(r.value)}`}
            </p>
            <p className="text-[10px] text-slate-400 truncate">
              {r.ref === null || r.ref === undefined ? 'not set' : `${r.refLabel || '—'} ${fmtPrice(r.ref, u)}`}
            </p>
          </div>
        );
      })}
    </div>
  );
}

// ── Compact inline card (for summary panel) ───────────────────────────
export function InlineDecisionCard({ decision, onOpen, onPrepareSuggestion }) {
  const cfg = REC_CFG[decision.recommendation_type] || REC_CFG.monitor_only;
  return (
    <div
      className={`border rounded-xl p-3.5 hover:shadow-md transition-shadow cursor-pointer ${cfg.border} ${cfg.bgSoft}`}
      onClick={() => onOpen?.(decision)}
      data-testid={`inline-card-${decision.canonical_product_id}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0 flex-1">
          <p className="font-heading text-sm font-bold text-navy-900 truncate">{decision.canonical_name}</p>
          <p className="text-[11px] text-slate-500 mt-0.5 truncate">
            {decision.current_vendor || 'Unknown vendor'} · <span className="tabular-nums font-semibold text-navy-700">{fmtPrice(decision.current_price_per_unit, decision.canonical_unit)}</span>
          </p>
        </div>
        <ActionPill type={decision.recommendation_type} />
      </div>
      <p className="text-[11px] text-slate-600 leading-relaxed line-clamp-2">{decision.reason_summary}</p>
      <div className="flex items-center gap-1.5 mt-2.5 flex-wrap">
        <RiskBadge level={decision.risk_level} />
        <ConfidenceBadge level={decision.confidence_level} score={decision.decision_confidence} />
        {decision.best_alternative_vendor && decision.recommendation_type === 'switch_vendor' && (
          <Badge variant="outline" className="text-[9px] border-emerald-300 bg-white text-emerald-700">
            → {decision.best_alternative_vendor}
          </Badge>
        )}
        {onPrepareSuggestion && (
          <Button
            size="sm"
            className="h-6 px-2 text-[10px] ml-auto gap-1 bg-teal-600 hover:bg-teal-700"
            onClick={(e) => { e.stopPropagation(); onPrepareSuggestion(decision); }}
            data-testid={`inline-prepare-btn-${decision.canonical_product_id}`}
          >
            <Sparkles className="w-3 h-3" /> Prepare Suggestion
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Full decision card (expanded, for detail view) ─────────────────────
export function FullDecisionCard({ decision, onSetTarget, onPrepareSuggestion, defaultExpanded = false }) {
  const [showEvidence, setShowEvidence] = useState(defaultExpanded);
  const [showUncertainty, setShowUncertainty] = useState(false);
  const cfg = REC_CFG[decision.recommendation_type] || REC_CFG.monitor_only;
  return (
    <div className={`border rounded-xl p-4 ${cfg.border} ${cfg.bgSoft}`} data-testid={`full-card-${decision.canonical_product_id}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h3 className="font-heading text-base font-extrabold text-navy-900">{decision.canonical_name}</h3>
            <Badge variant="outline" className="text-[10px] font-mono border-teal-200 text-teal-700 bg-teal-50">
              $/{decision.canonical_unit}
            </Badge>
            {decision.category && <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">{decision.category}</span>}
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">{decision.reason_summary}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <ActionPill type={decision.recommendation_type} />
          <div className="flex items-center gap-1">
            <RiskBadge level={decision.risk_level} />
            <ConfidenceBadge level={decision.confidence_level} score={decision.decision_confidence} />
          </div>
        </div>
      </div>

      {/* Price context */}
      <div className="mt-3.5 grid grid-cols-1 md:grid-cols-4 gap-2.5">
        <div className="bg-white border border-slate-200 rounded-lg px-3 py-2" data-testid="fc-current">
          <p className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">Current</p>
          <p className="text-sm font-bold text-navy-900 tabular-nums mt-0.5">{fmtPrice(decision.current_price_per_unit, decision.canonical_unit)}</p>
          <p className="text-[10px] text-slate-500 truncate mt-0.5">{decision.current_vendor || '—'}</p>
        </div>
        <div className="md:col-span-3">
          <DeltaRow decision={decision} />
        </div>
      </div>

      {/* Alternative vendor highlight */}
      {decision.best_alternative_vendor && (
        <div className="mt-2.5 flex items-center justify-between gap-3 bg-white border border-slate-200 rounded-lg px-3 py-2">
          <div className="flex items-center gap-2 min-w-0">
            <ArrowRightLeft className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
            <span className="text-[11px] text-slate-500">Best alternative:</span>
            <span className="text-xs font-semibold text-navy-900 truncate">{decision.best_alternative_vendor}</span>
          </div>
          <span className="text-xs tabular-nums font-bold text-emerald-700 flex-shrink-0">
            {fmtPrice(decision.best_alternative_price_per_unit, decision.canonical_unit)} <span className="text-[10px] font-normal text-slate-400">· {decision.best_alternative_observations} obs</span>
          </span>
        </div>
      )}

      {/* Evidence toggle */}
      <div className="mt-3 space-y-1.5">
        <button
          className="flex items-center gap-1.5 text-[11px] font-semibold text-navy-700 hover:text-teal-700"
          onClick={() => setShowEvidence((v) => !v)}
          data-testid={`fc-evidence-toggle-${decision.canonical_product_id}`}
        >
          <TrendingUp className="w-3 h-3" />
          {showEvidence ? 'Hide' : 'Show'} evidence ({decision.evidence?.length || 0})
        </button>
        {showEvidence && (
          <ul className="text-[11px] text-slate-600 space-y-1 pl-4 list-disc marker:text-emerald-500">
            {(decision.evidence || []).map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        )}

        {(decision.uncertainty?.length > 0) && (
          <>
            <button
              className="flex items-center gap-1.5 text-[11px] font-semibold text-navy-700 hover:text-amber-700"
              onClick={() => setShowUncertainty((v) => !v)}
              data-testid={`fc-uncertainty-toggle-${decision.canonical_product_id}`}
            >
              <AlertTriangle className="w-3 h-3" />
              {showUncertainty ? 'Hide' : 'Show'} uncertainty ({decision.uncertainty.length})
            </button>
            {showUncertainty && (
              <ul className="text-[11px] text-slate-600 space-y-1 pl-4 list-disc marker:text-amber-500">
                {decision.uncertainty.map((u, i) => <li key={i}>{u}</li>)}
              </ul>
            )}
          </>
        )}
      </div>

      {/* Footer actions */}
      <div className="mt-3.5 pt-3 border-t border-slate-200/70 flex items-center justify-between gap-2 flex-wrap">
        <div className="text-[10px] text-slate-400 space-x-3">
          <span>{decision.observation_count} good observations</span>
          {decision.trend?.trend === 'up' && <span className="text-red-500"><TrendingUp className="inline w-3 h-3" /> Trending up</span>}
          {decision.trend?.trend === 'down' && <span className="text-emerald-500"><TrendingDown className="inline w-3 h-3" /> Trending down</span>}
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm" variant="ghost"
            className="h-7 px-2.5 text-[10px] gap-1.5 text-slate-600"
            onClick={() => onSetTarget?.(decision)}
            data-testid={`fc-target-btn-${decision.canonical_product_id}`}
          >
            <Target className="w-3 h-3" />
            {decision.target_price_per_unit ? `Target: ${fmtPrice(decision.target_price_per_unit)}` : 'Set target'}
          </Button>
          {(decision.recommendation_type === 'switch_vendor' || decision.recommendation_type === 'renegotiate') && decision.confidence_level === 'high' && (
            <Button
              size="sm"
              className="h-7 px-3 text-[10px] gap-1.5 bg-teal-600 hover:bg-teal-700"
              onClick={() => onPrepareSuggestion?.(decision)}
              data-testid={`fc-prepare-suggestion-btn-${decision.canonical_product_id}`}
            >
              <Sparkles className="w-3 h-3" />
              Prepare Purchase Suggestion
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Target Price Modal ────────────────────────────────────────────────
export function TargetPriceModal({ api, decision, onClose, onSaved }) {
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (decision?.target_price_per_unit) setValue(String(decision.target_price_per_unit));
    else setValue('');
  }, [decision]);

  if (!decision) return null;

  const save = async () => {
    const n = value === '' ? null : Number(value);
    if (value !== '' && (isNaN(n) || n <= 0)) {
      toast.error('Target price must be a positive number');
      return;
    }
    setSaving(true);
    try {
      await api.patch(`/procurement/targets/${decision.canonical_product_id}`, {
        target_price_per_unit: n,
        canonical_unit: decision.canonical_unit,
      });
      toast.success(n === null ? 'Target price cleared' : `Target set to $${n.toFixed(2)}/${decision.canonical_unit}`);
      onSaved?.();
      onClose?.();
    } catch {
      toast.error('Could not save target price');
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    setValue('');
    setSaving(true);
    try {
      await api.patch(`/procurement/targets/${decision.canonical_product_id}`, {
        target_price_per_unit: null,
        canonical_unit: decision.canonical_unit,
      });
      toast.success('Target price cleared');
      onSaved?.();
      onClose?.();
    } catch {
      toast.error('Could not clear target price');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={!!decision} onOpenChange={onClose}>
      <DialogContent className="max-w-md" data-testid="target-price-modal">
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-2 text-base">
            <Target className="w-4 h-4 text-teal-600" />
            Set target price
          </DialogTitle>
          <DialogDescription className="text-[11px] text-slate-500">
            Per-unit target used to compute price_delta_vs_target_pct. Leave blank to fall back to the historical average comparison only.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="bg-slate-50 border border-slate-100 rounded-lg px-3 py-2.5">
            <p className="text-[10px] text-slate-400 uppercase tracking-wider font-bold">Product</p>
            <p className="text-sm font-bold text-navy-900">{decision.canonical_name}</p>
            <p className="text-[11px] text-slate-500 mt-1">
              Current: <span className="tabular-nums font-semibold">{fmtPrice(decision.current_price_per_unit, decision.canonical_unit)}</span>
              {decision.historical_average_price_per_unit && <> · Recent avg: <span className="tabular-nums">{fmtPrice(decision.historical_average_price_per_unit, decision.canonical_unit)}</span></>}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11px] font-semibold text-navy-700">Target price per {decision.canonical_unit}</Label>
            <div className="relative">
              <DollarSign className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                type="number"
                step="0.01"
                min="0.01"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="e.g. 3.50"
                className="pl-8 tabular-nums"
                data-testid="target-price-input"
              />
            </div>
            <p className="text-[10px] text-slate-400">
              Used to compute <span className="font-semibold">price_delta_vs_target_pct</span>. Leave blank to fall back to historical average comparison only.
            </p>
          </div>
        </div>
        <DialogFooter className="gap-2">
          {decision.target_price_per_unit && (
            <Button variant="ghost" onClick={clear} disabled={saving} className="text-red-600 hover:text-red-700" data-testid="target-clear-btn">
              Clear target
            </Button>
          )}
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={saving} className="bg-teal-600 hover:bg-teal-700 gap-1.5" data-testid="target-save-btn">
            {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
