/**
 * Milestone 6 — Purchase Suggestion Modal
 * ========================================
 * Controlled Action Layer — ADVISORY ONLY.
 *
 * Hard rules:
 *   - Label: "Prepare Purchase Suggestion" (never "order" / "buy" / "submit")
 *   - No pre-filled inputs (quantities are helper text only)
 *   - Mandatory acknowledgment checkbox gates the confirm button
 *   - Final action = "Save Suggestion" OR "Copy Details" — no execution
 *   - Emits structured tracking events to /api/procurement/events
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  ClipboardCopy, FileText, Info, Lightbulb, Save, Shield, Sparkles, TrendingUp, AlertTriangle,
} from 'lucide-react';
import { ActionPill, ConfidenceBadge, RiskBadge, DeltaRow, fmtPrice } from './ProcurementUI';

function formatClipboard(d, hint) {
  const lines = [
    `Purchase Suggestion (ADVISORY ONLY)`,
    `--------------------------------------`,
    `Product: ${d.canonical_name}`,
    `Recommendation: ${d.recommendation_type.replace('_', ' ').toUpperCase()}`,
    `Current: ${d.current_vendor || '—'} · ${fmtPrice(d.current_price_per_unit, d.canonical_unit)}`,
  ];
  if (d.best_alternative_vendor) {
    lines.push(`Recommended vendor: ${d.best_alternative_vendor} · ${fmtPrice(d.best_alternative_price_per_unit, d.canonical_unit)} (${d.best_alternative_observations} obs)`);
  }
  if (d.target_price_per_unit) lines.push(`Target: ${fmtPrice(d.target_price_per_unit, d.canonical_unit)}`);
  if (d.historical_average_price_per_unit) lines.push(`Recent avg: ${fmtPrice(d.historical_average_price_per_unit, d.canonical_unit)}`);
  lines.push(`Confidence: ${d.confidence_level?.toUpperCase()} (${d.decision_confidence}) · Risk: ${d.risk_level?.toUpperCase()}`);
  lines.push('');
  lines.push(`Reason: ${d.reason_summary}`);
  if (d.evidence?.length) {
    lines.push('');
    lines.push('Evidence:');
    d.evidence.forEach((e) => lines.push(`  • ${e}`));
  }
  if (d.uncertainty?.length) {
    lines.push('');
    lines.push('Uncertainty:');
    d.uncertainty.forEach((u) => lines.push(`  • ${u}`));
  }
  if (hint?.helper_text) {
    lines.push('');
    lines.push(`Quantity hint: ${hint.helper_text}  (${hint.disclaimer})`);
  }
  lines.push('');
  lines.push('This recommendation is based on historical data and may not reflect contract terms,');
  lines.push('product quality differences, or real-time pricing.');
  return lines.join('\n');
}

export function PurchaseSuggestionModal({ api, decision, onClose, onSaved }) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [hint, setHint] = useState(null);
  const [hintLoading, setHintLoading] = useState(false);

  // Track whether we already logged suggestion_opened / draft_viewed
  const openedLogged = useRef(false);
  const viewedLogged = useRef(false);

  const logEvent = useCallback(async (event_type, metadata) => {
    if (!decision) return;
    try {
      await api.post('/procurement/events', {
        canonical_product_id: decision.canonical_product_id,
        recommendation_type: decision.recommendation_type,
        event_type,
        metadata: metadata || null,
      });
    } catch {
      // Silent — tracking should never block the UI
    }
  }, [api, decision]);

  // On open: fetch hint + log events
  useEffect(() => {
    if (!decision) {
      openedLogged.current = false;
      viewedLogged.current = false;
      setAcknowledged(false);
      setSaved(false);
      setHint(null);
      return;
    }
    if (!openedLogged.current) {
      openedLogged.current = true;
      logEvent('suggestion_opened');
    }
    setHintLoading(true);
    api.get(`/procurement/quantity-hint/${decision.canonical_product_id}`, {
      params: { canonical_unit: decision.canonical_unit },
    })
      .then((r) => {
        setHint(r.data);
        if (!viewedLogged.current) {
          viewedLogged.current = true;
          logEvent('draft_viewed');
        }
      })
      .catch(() => {
        setHint({
          helper_text: 'No recent quantity data available for this product.',
          disclaimer: 'Suggestion only — not a recommended order quantity.',
          lookback: 0,
        });
      })
      .finally(() => setHintLoading(false));
  }, [decision, api, logEvent]);

  const onAcknowledgeToggle = (next) => {
    setAcknowledged(!!next);
    if (next) logEvent('acknowledgment_checked');
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(formatClipboard(decision, hint));
      toast.success('Details copied to clipboard');
    } catch {
      toast.error('Could not copy to clipboard');
    }
  };

  const handleSave = async () => {
    if (!acknowledged || !decision) return;
    setSaving(true);
    try {
      await api.post('/procurement/suggestions', {
        canonical_product_id: decision.canonical_product_id,
        canonical_unit: decision.canonical_unit,
        recommendation_type: decision.recommendation_type,
        recommended_vendor: decision.best_alternative_vendor || decision.current_vendor || '',
        reference_price_per_unit:
          decision.target_price_per_unit ??
          decision.historical_average_price_per_unit ??
          decision.best_alternative_price_per_unit ??
          null,
        current_price_per_unit: decision.current_price_per_unit ?? null,
        decision_confidence: decision.decision_confidence ?? null,
        confidence_level: decision.confidence_level ?? null,
        risk_level: decision.risk_level ?? null,
        reason_summary: decision.reason_summary || '',
        evidence: decision.evidence || [],
        uncertainty: decision.uncertainty || [],
        acknowledgment_confirmed: true,
        snapshot: {
          historical_average_price_per_unit: decision.historical_average_price_per_unit,
          target_price_per_unit: decision.target_price_per_unit,
          best_alternative_price_per_unit: decision.best_alternative_price_per_unit,
          price_delta_vs_avg_pct: decision.price_delta_vs_avg_pct,
          price_delta_vs_target_pct: decision.price_delta_vs_target_pct,
          price_delta_vs_alternative_pct: decision.price_delta_vs_alternative_pct,
          observation_count: decision.observation_count,
          quantity_hint: hint,
        },
      });
      setSaved(true);
      toast.success('Suggestion saved for your review');
      onSaved?.();
    } catch {
      toast.error('Could not save suggestion');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    logEvent('action_canceled');
    onClose?.();
  };

  if (!decision) return null;

  const referencePriceRows = [
    { label: 'Recent avg', value: decision.historical_average_price_per_unit },
    { label: 'Target', value: decision.target_price_per_unit },
    { label: 'Best alternative', value: decision.best_alternative_price_per_unit, vendor: decision.best_alternative_vendor },
  ];

  return (
    <Dialog open={!!decision} onOpenChange={(v) => !v && handleCancel()}>
      <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto" data-testid="purchase-suggestion-modal">
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-2 text-base">
            <Sparkles className="w-4 h-4 text-teal-600" />
            Prepare Purchase Suggestion
            <Badge variant="outline" className="ml-1 text-[9px] border-amber-300 bg-amber-50 text-amber-700">ADVISORY ONLY</Badge>
          </DialogTitle>
          <DialogDescription className="text-[11px] text-slate-500">
            This tool helps you review a decision and save a draft for later.
            It does not place orders, submit anything to vendors, or send any communication.
          </DialogDescription>
        </DialogHeader>

        {saved ? (
          // ── Post-confirmation state ────────────────────────────────
          <div className="py-6 space-y-4 text-center" data-testid="suggestion-saved-state">
            <div className="w-12 h-12 rounded-full bg-emerald-100 flex items-center justify-center mx-auto">
              <Save className="w-6 h-6 text-emerald-700" />
            </div>
            <div>
              <h3 className="font-heading text-base font-bold text-navy-900">Suggestion saved for your review</h3>
              <p className="text-[11px] text-slate-500 mt-1 max-w-md mx-auto">
                Your draft is stored under your saved suggestions. Nothing has been sent or executed.
              </p>
            </div>
            <div className="flex items-center justify-center gap-2 flex-wrap">
              <Button variant="outline" size="sm" onClick={handleCopy} className="gap-1.5" data-testid="copy-details-btn-saved">
                <ClipboardCopy className="w-3.5 h-3.5" /> Copy details
              </Button>
              <Button size="sm" onClick={onClose} className="bg-teal-600 hover:bg-teal-700" data-testid="close-saved-btn">Done</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* ── A. Recommendation Summary ─────────────────────── */}
            <section data-testid="suggestion-section-summary">
              <SectionHeader letter="A" label="Recommendation Summary" icon={FileText} />
              <div className="bg-slate-50 border border-slate-100 rounded-lg p-3.5 space-y-2.5">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Product</p>
                    <p className="text-sm font-heading font-bold text-navy-900">{decision.canonical_name}</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <ActionPill type={decision.recommendation_type} />
                    <RiskBadge level={decision.risk_level} />
                    <ConfidenceBadge level={decision.confidence_level} score={decision.decision_confidence} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  <div className="bg-white border border-slate-200 rounded-lg px-3 py-2">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Current</p>
                    <p className="text-sm font-bold text-navy-900 tabular-nums">{fmtPrice(decision.current_price_per_unit, decision.canonical_unit)}</p>
                    <p className="text-[10px] text-slate-500 truncate">{decision.current_vendor || '—'}</p>
                  </div>
                  <div className="bg-white border border-emerald-200 rounded-lg px-3 py-2">
                    <p className="text-[10px] uppercase tracking-wider text-emerald-600 font-bold">Recommended vendor</p>
                    <p className="text-sm font-bold text-navy-900 truncate">{decision.best_alternative_vendor || decision.current_vendor || '—'}</p>
                    <p className="text-[10px] text-slate-500 tabular-nums">{fmtPrice(decision.best_alternative_price_per_unit ?? decision.current_price_per_unit, decision.canonical_unit)}</p>
                  </div>
                </div>
                {/* Reference price context */}
                <div className="grid grid-cols-3 gap-2">
                  {referencePriceRows.map((r) => (
                    <div key={r.label} className="bg-white border border-slate-200 rounded-lg px-2.5 py-1.5">
                      <p className="text-[9px] uppercase tracking-wider text-slate-400 font-bold">{r.label}</p>
                      <p className="text-xs font-semibold text-navy-900 tabular-nums mt-0.5">
                        {r.value ? fmtPrice(r.value, decision.canonical_unit) : <span className="text-slate-400 font-normal">not set</span>}
                      </p>
                      {r.vendor && <p className="text-[9px] text-slate-400 truncate">{r.vendor}</p>}
                    </div>
                  ))}
                </div>
                <DeltaRow decision={decision} />
                <p className="text-[11px] text-slate-600 italic">{decision.reason_summary}</p>
              </div>
            </section>

            {/* ── B. Suggested Quantities (advisory only) ──────── */}
            <section data-testid="suggestion-section-quantities">
              <SectionHeader letter="B" label="Suggested Quantities (Advisory Only)" icon={Lightbulb} />
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3.5">
                {hintLoading ? (
                  <Skeleton className="h-6 w-48" />
                ) : (
                  <>
                    <p className="text-sm text-navy-900 font-semibold" data-testid="qty-helper-text">{hint?.helper_text || 'No recent quantity data available.'}</p>
                    {hint?.quantities?.length > 0 && (
                      <p className="text-[11px] text-slate-600 mt-1">
                        Recent quantities: {hint.quantities.map((q) => `${q} ${hint.canonical_unit}`).join(' · ')}
                      </p>
                    )}
                    <p className="text-[11px] text-amber-800 font-bold mt-2 uppercase tracking-wider" data-testid="qty-disclaimer">
                      {hint?.disclaimer || 'Suggestion only — not a recommended order quantity.'}
                    </p>
                    <p className="text-[11px] text-slate-600 mt-1 italic">
                      No input field is provided — this is context, not a prescription.
                    </p>
                  </>
                )}
              </div>
            </section>

            {/* ── C. Decision Context ──────────────────────────── */}
            <section data-testid="suggestion-section-context">
              <SectionHeader letter="C" label="Decision Context" icon={TrendingUp} />
              <div className="space-y-2.5">
                {(decision.evidence?.length > 0) && (
                  <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 mb-1.5">Evidence</p>
                    <ul className="text-[11px] text-slate-700 space-y-1 pl-4 list-disc marker:text-emerald-500">
                      {decision.evidence.map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  </div>
                )}
                {(decision.uncertainty?.length > 0) && (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700 mb-1.5 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> Uncertainty
                    </p>
                    <ul className="text-[11px] text-slate-700 space-y-1 pl-4 list-disc marker:text-amber-500">
                      {decision.uncertainty.map((u, i) => <li key={i}>{u}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            </section>

            {/* ── Hard gate: mandatory acknowledgment ──────────── */}
            <section data-testid="suggestion-section-acknowledgment">
              <div className="border-2 border-dashed border-red-200 bg-red-50/40 rounded-lg p-3.5">
                <div className="flex items-start gap-2 mb-3">
                  <Shield className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                  <p className="text-[11px] text-red-900 leading-relaxed" data-testid="suggestion-disclaimer">
                    This recommendation is based on historical data and may not reflect contract terms,
                    product quality differences, or real-time pricing.
                  </p>
                </div>
                <label className="flex items-start gap-2 cursor-pointer select-none" data-testid="acknowledgment-label">
                  <Checkbox
                    checked={acknowledged}
                    onCheckedChange={onAcknowledgeToggle}
                    className="mt-0.5 data-[state=checked]:bg-red-600 data-[state=checked]:border-red-600"
                    data-testid="acknowledgment-checkbox"
                  />
                  <span className="text-[12px] text-navy-900 font-semibold">
                    I understand the limitations of this recommendation
                  </span>
                </label>
              </div>
            </section>
          </div>
        )}

        {!saved && (
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={handleCopy} className="mr-auto gap-1.5 text-slate-600" data-testid="copy-details-btn">
              <ClipboardCopy className="w-3.5 h-3.5" /> Copy details
            </Button>
            <Button variant="outline" onClick={handleCancel} disabled={saving} data-testid="suggestion-cancel-btn">Cancel</Button>
            <Button
              onClick={handleSave}
              disabled={!acknowledged || saving}
              className="bg-teal-600 hover:bg-teal-700 gap-1.5 disabled:opacity-40"
              data-testid="save-suggestion-btn"
            >
              <Save className="w-3.5 h-3.5" />
              {saving ? 'Saving…' : 'Save Suggestion'}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SectionHeader({ letter, label, icon: Icon }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="w-5 h-5 rounded-full bg-teal-600 text-white text-[11px] font-bold flex items-center justify-center">{letter}</span>
      <Icon className="w-3.5 h-3.5 text-teal-600" />
      <h3 className="text-[13px] font-heading font-bold text-navy-900">{label}</h3>
    </div>
  );
}

// Small Info chip used elsewhere
export function AdvisoryInfo({ children }) {
  return (
    <div className="flex items-start gap-2 text-[11px] text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
      <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-slate-400" />
      <span>{children}</span>
    </div>
  );
}
