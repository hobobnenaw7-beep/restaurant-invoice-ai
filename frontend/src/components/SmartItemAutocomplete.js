/**
 * SmartItemAutocomplete (Milestone 19)
 * ======================================
 * System-driven suggestions. Sources approved canonical items, declared
 * variants, and saved aliases ONLY. Never raw invoice text, never
 * suggested/pending items.
 *
 * Behavior:
 *   • As the user types, fetches `/api/items/autocomplete?q=...`.
 *   • User can select a suggestion → fires `onSelect({label, canonical_item_id, variant_key})`.
 *   • User can also free-type: calls `onChange(text)` — downstream code
 *     marks the line as suggested/unlinked per guardrail.
 *
 * Advisory only: no auto-select, no auto-merge, no hidden actions.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { Input } from '@/components/ui/input';
import { Loader2, Sparkles, Tag, Package } from 'lucide-react';

const SOURCE_ICON = {
  canonical: Package,
  variant: Tag,
  alias: Sparkles,
};

export default function SmartItemAutocomplete({
  api,
  value,
  onChange,
  onSelect,
  placeholder = 'Start typing item name…',
  inputClassName = '',
  testId = 'smart-item-autocomplete',
  autoFocus = false,
  disabled = false,
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const debounceRef = useRef(null);
  const wrapRef = useRef(null);

  const fetchSuggestions = useCallback(async (q) => {
    if (!q || q.trim().length < 2) {
      setSuggestions([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const r = await api.get('/items/autocomplete', { params: { q, limit: 12 } });
      setSuggestions(r.data?.suggestions || []);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, [api]);

  // Debounced fetch on every value change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(value), 180);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [value, fetchSuggestions]);

  // Close when clicking outside
  useEffect(() => {
    const handler = (e) => {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleKey = (e) => {
    if (!open || !suggestions.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(i => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      pick(suggestions[activeIndex]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const pick = (s) => {
    if (!s) return;
    onChange?.(s.label);
    onSelect?.({
      label: s.label,
      canonical_item_id: s.canonical_item_id,
      variant_key: s.variant_key,
      source: s.source,
    });
    setOpen(false);
    setActiveIndex(-1);
  };

  const showPanel = open && (loading || suggestions.length > 0);

  return (
    <div ref={wrapRef} className="relative" data-testid={testId}>
      <Input
        value={value || ''}
        onChange={(e) => { onChange?.(e.target.value); setOpen(true); setActiveIndex(-1); }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKey}
        placeholder={placeholder}
        className={inputClassName}
        disabled={disabled}
        autoFocus={autoFocus}
        data-testid={`${testId}-input`}
        autoComplete="off"
      />
      {showPanel && (
        <div
          className="absolute z-50 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-64 overflow-y-auto"
          data-testid={`${testId}-panel`}
        >
          {loading && (
            <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate-500">
              <Loader2 className="w-3 h-3 animate-spin" /> Searching approved items…
            </div>
          )}
          {!loading && suggestions.length === 0 && (
            <div className="px-3 py-2 text-xs text-slate-400" data-testid={`${testId}-empty`}>
              No approved matches. Typing will save this as a new suggestion.
            </div>
          )}
          {!loading && suggestions.map((s, i) => {
            const Icon = SOURCE_ICON[s.source] || Package;
            const active = i === activeIndex;
            return (
              <button
                type="button"
                key={`${s.canonical_item_id}-${s.variant_key || ''}-${i}`}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => pick(s)}
                className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs border-b border-slate-50 last:border-0 transition-colors ${active ? 'bg-teal-50' : 'hover:bg-slate-50'}`}
                data-testid={`${testId}-option-${i}`}
                data-source={s.source}
                data-canonical-id={s.canonical_item_id}
                data-variant-key={s.variant_key || ''}
              >
                <Icon className={`w-3 h-3 flex-shrink-0 ${s.source === 'variant' ? 'text-indigo-500' : s.source === 'alias' ? 'text-amber-500' : 'text-teal-600'}`} />
                <span className="flex-1 font-medium text-slate-800 truncate">{s.label}</span>
                <span className="text-[9px] uppercase tracking-wider text-slate-400">{s.source}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
