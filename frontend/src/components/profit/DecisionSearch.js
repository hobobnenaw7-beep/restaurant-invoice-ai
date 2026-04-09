import { useState, useCallback } from 'react';
import { Search, ArrowRight, TrendingUp, TrendingDown, Minus, ShieldCheck, AlertTriangle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';

export default function DecisionSearch({ api }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = useCallback(async (e) => {
    e?.preventDefault();
    if (!query.trim() || query.trim().length < 2) return;
    setLoading(true);
    try {
      const res = await api.get(`/profit/search?q=${encodeURIComponent(query.trim())}`);
      setResults(res.data);
    } catch (err) {
      console.error('Search error:', err);
    } finally {
      setLoading(false);
    }
  }, [api, query]);

  return (
    <Card className="border-slate-700/50 bg-slate-900/50" data-testid="decision-search">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-slate-200 flex items-center gap-2">
          <Search className="w-4 h-4 text-emerald-400" />
          Where Should I Buy?
        </CardTitle>
        <p className="text-xs text-slate-500">Search any product for vendor comparison, price trends & recommendations</p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSearch} className="flex gap-2 mb-4">
          <Input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search products... (e.g., chicken, okra, lemonade)"
            className="bg-slate-800/50 border-slate-600/50 text-slate-200 placeholder:text-slate-500"
            data-testid="decision-search-input"
          />
          <button
            type="submit"
            disabled={loading || query.trim().length < 2}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-md text-sm font-medium disabled:opacity-40 transition-colors flex items-center gap-1.5"
            data-testid="decision-search-button"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Search
          </button>
        </form>

        {results && results.results?.length === 0 && (
          <div className="text-sm text-slate-500 text-center py-6" data-testid="search-no-results">
            No results for "{results.query}". Only trusted & confirmed data is searched.
          </div>
        )}

        {results?.results?.map((r, idx) => (
          <SearchResult key={idx} result={r} />
        ))}
      </CardContent>
    </Card>
  );
}

function SearchResult({ result }) {
  const action = result.suggested_action || {};
  const actionColor = {
    high: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    medium: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    low: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
  }[action.confidence] || 'bg-slate-500/20 text-slate-300 border-slate-500/30';

  return (
    <div className="border border-slate-700/40 rounded-lg p-4 mb-3 bg-slate-800/30" data-testid="search-result">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-sm font-semibold text-slate-200">{result.product}</div>
          {result.item_code && <span className="text-xs text-slate-500">Code: {result.item_code}</span>}
        </div>
        <div className={`px-3 py-1.5 rounded-md border text-xs font-medium ${actionColor}`} data-testid="suggested-action">
          <div className="font-semibold">{action.action}</div>
        </div>
      </div>

      {action.reason && (
        <div className="text-xs text-slate-400 mb-3 flex items-start gap-1.5">
          <ArrowRight className="w-3 h-3 mt-0.5 text-emerald-400 flex-shrink-0" />
          {action.reason}
        </div>
      )}

      {/* Vendor comparison table */}
      <div className="space-y-1.5">
        {result.vendors?.map((v, i) => (
          <div
            key={i}
            className={`flex items-center justify-between px-3 py-2 rounded text-xs ${
              i === 0 ? 'bg-emerald-950/30 border border-emerald-500/20' : 'bg-slate-800/50'
            }`}
            data-testid={`vendor-row-${i}`}
          >
            <div className="flex items-center gap-2">
              {i === 0 && <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-400 px-1.5">Cheapest</Badge>}
              <span className="text-slate-300 font-medium">{v.vendor}</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-slate-200 font-semibold">${v.latest_price}</span>
              <TrendIndicator pct={v.trend_pct} />
              <StabilityBadge label={v.stability} />
              <span className="text-slate-500">{v.purchase_count}x</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrendIndicator({ pct }) {
  if (pct === null || pct === undefined) return <span className="text-slate-600 w-12 text-right">—</span>;
  if (pct > 1) return <span className="text-red-400 flex items-center gap-0.5 w-12 justify-end"><TrendingUp className="w-3 h-3" />+{pct}%</span>;
  if (pct < -1) return <span className="text-emerald-400 flex items-center gap-0.5 w-12 justify-end"><TrendingDown className="w-3 h-3" />{pct}%</span>;
  return <span className="text-slate-500 flex items-center gap-0.5 w-12 justify-end"><Minus className="w-3 h-3" />0%</span>;
}

function StabilityBadge({ label }) {
  const styles = {
    Stable: 'text-emerald-400 border-emerald-500/30',
    Moderate: 'text-amber-400 border-amber-500/30',
    Volatile: 'text-red-400 border-red-500/30',
  };
  return (
    <Badge variant="outline" className={`text-[10px] px-1.5 ${styles[label] || 'text-slate-500 border-slate-600'}`}>
      {label === 'Stable' && <ShieldCheck className="w-2.5 h-2.5 mr-0.5" />}
      {label === 'Volatile' && <AlertTriangle className="w-2.5 h-2.5 mr-0.5" />}
      {label || '?'}
    </Badge>
  );
}
