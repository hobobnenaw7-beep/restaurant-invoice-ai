import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  Scale, Search, TrendingDown, Package, Users, ChevronDown, ChevronRight,
  Info, Link2, Trash2, Check, Lightbulb, UserCheck, AlertTriangle, ShieldCheck, ArrowRight
} from 'lucide-react';

function fmtPrice(n) { return `$${Number(n || 0).toFixed(4)}`; }
function fmtCase(n) { return `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

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

// ======================== SPREAD SEVERITY ========================
function spreadColor(pct) {
  if (pct >= 15) return { bg: 'bg-red-100', text: 'text-red-700', label: 'High spread' };
  if (pct >= 8) return { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Moderate spread' };
  if (pct > 0) return { bg: 'bg-emerald-100', text: 'text-emerald-700', label: 'Low spread' };
  return { bg: 'bg-slate-100', text: 'text-slate-500', label: '' };
}

// ======================== COMPARISON GROUP ========================
function ComparisonGroup({ group, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  const { item_key, comparison_unit, entries, best_price, worst_price, spread_pct, vendor_count, is_multi_vendor, match_source, raw_names_in_group } = group;
  const isConfirmed = match_source === 'user_confirmed';
  const bestEntry = entries[0];
  const worstEntry = entries.length > 1 ? entries[entries.length - 1] : null;
  const sc = spreadColor(spread_pct);

  return (
    <div className={`border rounded-xl overflow-hidden ${isConfirmed ? 'border-indigo-200' : 'border-slate-100'}`} data-testid={`comparison-group-${item_key}`}>
      {/* Header row */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-slate-50/70 transition-colors text-left"
        data-testid={`group-toggle-${item_key}`}
      >
        {open ? <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-heading font-bold text-navy-900">{item_key}</span>
          {isConfirmed && raw_names_in_group && raw_names_in_group.length > 1 && (
            <span className="ml-2 text-[10px] text-indigo-500">({raw_names_in_group.length} linked names)</span>
          )}
        </div>
        {isConfirmed && (
          <Badge className="text-[9px] bg-indigo-100 text-indigo-700 flex-shrink-0 gap-1" data-testid={`match-source-${item_key}`}>
            <UserCheck className="w-3 h-3" /> Confirmed
          </Badge>
        )}
        <Badge variant="outline" className="text-[10px] font-mono border-teal-200 text-teal-700 bg-teal-50 flex-shrink-0">
          $/{comparison_unit}
        </Badge>
        {is_multi_vendor && (
          <Badge className="text-[10px] bg-amber-100 text-amber-700 flex-shrink-0">
            {vendor_count} vendors
          </Badge>
        )}
        {spread_pct > 0 && (
          <Badge className={`text-[10px] ${sc.bg} ${sc.text} flex-shrink-0`} data-testid={`spread-badge-${item_key}`}>
            {spread_pct}% spread
          </Badge>
        )}
        <span className="text-xs font-mono font-semibold text-navy-700 flex-shrink-0">
          Best: {fmtPrice(best_price)}/{comparison_unit}
        </span>
      </button>

      {open && (
        <div className="border-t border-slate-100">
          {/* Decision banner — only for multi-vendor groups */}
          {is_multi_vendor && worstEntry && (
            <div className="px-4 py-3 bg-emerald-50 border-b border-emerald-100 flex items-center gap-3" data-testid={`decision-banner-${item_key}`}>
              <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center flex-shrink-0">
                <ShieldCheck className="w-4 h-4 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-emerald-900" data-testid={`decision-text-${item_key}`}>
                  Buy from {bestEntry.vendor}
                  {spread_pct > 0 && (
                    <span className="font-normal text-emerald-700"> — save {spread_pct}% vs {worstEntry.vendor}</span>
                  )}
                </p>
                <p className="text-[11px] text-emerald-600 mt-0.5">
                  {fmtPrice(best_price)}/{comparison_unit} vs {fmtPrice(worst_price)}/{comparison_unit}
                  <span className="text-emerald-500 ml-1">
                    ({fmtPrice(worst_price - best_price)}/{comparison_unit} cheaper per pound)
                  </span>
                </p>
              </div>
            </div>
          )}

          {/* Linked names banner */}
          {isConfirmed && raw_names_in_group && raw_names_in_group.length > 1 && (
            <div className="px-4 py-2 bg-indigo-50/50 text-[11px] text-indigo-600 flex items-center gap-2 border-b border-indigo-100/50">
              <Link2 className="w-3.5 h-3.5" />
              <span>Linked names: {raw_names_in_group.join(' + ')}</span>
            </div>
          )}

          {/* Table */}
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
                  <th className="text-center px-4 py-2.5 w-24">Signal</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => {
                  const isBest = is_multi_vendor && e.normalized_price_per_lb === best_price;
                  const isWorst = is_multi_vendor && entries.length > 1 && e.normalized_price_per_lb === worst_price;
                  const rowBg = isBest ? 'bg-emerald-50/60' : isWorst ? 'bg-red-50/40' : 'hover:bg-slate-50/50';
                  return (
                    <tr key={i} className={`border-t border-slate-50 transition-colors ${rowBg}`} data-testid={`entry-row-${item_key}-${i}`}>
                      <td className="px-4 py-2.5 font-medium text-navy-900 whitespace-nowrap">
                        {e.vendor}
                      </td>
                      <td className="px-4 py-2.5 text-slate-600">{e.raw_name}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{e.pack_size_raw}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-700">{fmtCase(e.unit_price)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-500">
                        {e.total_case_weight} {e.pack_unit}
                      </td>
                      <td className={`px-4 py-2.5 text-right font-mono font-bold ${isBest ? 'text-emerald-700' : isWorst ? 'text-red-600' : 'text-navy-900'}`}>
                        {fmtPrice(e.normalized_price_per_lb)}
                      </td>
                      <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{e.invoice_date}</td>
                      <td className="px-4 py-2.5 text-center">
                        {isBest && (
                          <Badge className="text-[9px] bg-emerald-600 text-white gap-1" data-testid={`best-deal-badge-${item_key}`}>
                            <ShieldCheck className="w-3 h-3" /> Best Deal
                          </Badge>
                        )}
                        {isWorst && (
                          <Badge className="text-[9px] bg-red-100 text-red-700 border border-red-200 gap-1" data-testid={`high-price-badge-${item_key}`}>
                            <AlertTriangle className="w-3 h-3" /> High Price
                          </Badge>
                        )}
                      </td>
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

// ======================== SUGGESTION CARD ========================
function SuggestionCard({ suggestion, onLink, linking }) {
  const { name_a, name_b, vendors_a, vendors_b, similarity, shared_words } = suggestion;
  const [canonName, setCanonName] = useState(name_a);

  return (
    <div className="border border-slate-100 rounded-xl p-4 hover:border-indigo-200 transition-colors" data-testid={`suggestion-${name_a}-${name_b}`}>
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Lightbulb className="w-4 h-4 text-amber-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <Badge className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200">
              {Math.round(similarity * 100)}% match
            </Badge>
            <span className="text-[10px] text-slate-400">
              shared: {shared_words.join(', ')}
            </span>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-navy-900">{name_a}</p>
              <p className="text-[10px] text-slate-400">{vendors_a.join(', ')}</p>
            </div>
            <Link2 className="w-4 h-4 text-slate-300 flex-shrink-0 rotate-90 sm:rotate-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-navy-900">{name_b}</p>
              <p className="text-[10px] text-slate-400">{vendors_b.join(', ')}</p>
            </div>
          </div>
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-2">
            <div className="flex-1 min-w-0">
              <label className="text-[10px] text-slate-500 font-medium block mb-1">Display name for comparison</label>
              <Input
                className="h-8 text-sm"
                value={canonName}
                onChange={(e) => setCanonName(e.target.value)}
                data-testid={`canon-name-input-${name_a}`}
              />
            </div>
            <Button
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700 text-white h-8 px-4 text-xs gap-1.5"
              onClick={() => onLink(canonName, [name_a, name_b])}
              disabled={linking || !canonName.trim()}
              data-testid={`link-btn-${name_a}-${name_b}`}
            >
              <Check className="w-3.5 h-3.5" /> Confirm Link
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ======================== MAPPING CARD ========================
function MappingCard({ mapping, onDelete, deleting }) {
  return (
    <div className="border border-indigo-100 rounded-xl p-4 bg-indigo-50/30" data-testid={`mapping-${mapping.id}`}>
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0 mt-0.5">
          <UserCheck className="w-4 h-4 text-indigo-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <p className="text-sm font-bold text-navy-900">{mapping.canonical_name}</p>
            <Badge className="text-[9px] bg-indigo-100 text-indigo-700">Confirmed</Badge>
          </div>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {mapping.mapped_names.map((name, i) => (
              <span key={i} className="text-[11px] font-mono bg-white border border-indigo-200 rounded-md px-2 py-0.5 text-indigo-700">
                {name}
              </span>
            ))}
          </div>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="text-red-400 hover:text-red-600 hover:bg-red-50 h-8 w-8 p-0"
          onClick={() => onDelete(mapping.id)}
          disabled={deleting}
          data-testid={`delete-mapping-${mapping.id}`}
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}

// ======================== ITEM MATCHING PANEL ========================
function ItemMatchingPanel({ api, onMappingChange }) {
  const [suggestions, setSuggestions] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [linking, setLinking] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [sugRes, mapRes] = await Promise.all([
        api.get('/item-mappings/suggestions'),
        api.get('/item-mappings'),
      ]);
      setSuggestions(sugRes.data.suggestions || []);
      setMappings(mapRes.data.mappings || []);
    } catch {
      toast.error('Failed to load matching data');
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  const handleLink = async (canonName, names) => {
    setLinking(true);
    try {
      await api.post('/item-mappings', { canonical_name: canonName, mapped_names: names });
      toast.success('Items linked successfully');
      await load();
      onMappingChange();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create mapping');
    } finally {
      setLinking(false);
    }
  };

  const handleDelete = async (mid) => {
    setDeleting(true);
    try {
      await api.delete(`/item-mappings/${mid}`);
      toast.success('Mapping removed');
      await load();
      onMappingChange();
    } catch {
      toast.error('Failed to delete mapping');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <div className="space-y-3"><Skeleton className="h-24 rounded-xl" /><Skeleton className="h-24 rounded-xl" /></div>;
  }

  return (
    <div className="space-y-6" data-testid="item-matching-panel">
      {/* Current Mappings */}
      {mappings.length > 0 && (
        <div>
          <h3 className="text-sm font-heading font-bold text-navy-900 mb-3 flex items-center gap-2">
            <UserCheck className="w-4 h-4 text-indigo-600" />
            Confirmed Mappings
            <Badge variant="secondary" className="text-[10px]">{mappings.length}</Badge>
          </h3>
          <div className="space-y-2.5" data-testid="confirmed-mappings-list">
            {mappings.map(m => (
              <MappingCard key={m.id} mapping={m} onDelete={handleDelete} deleting={deleting} />
            ))}
          </div>
        </div>
      )}

      {/* Suggestions */}
      <div>
        <h3 className="text-sm font-heading font-bold text-navy-900 mb-3 flex items-center gap-2">
          <Lightbulb className="w-4 h-4 text-amber-500" />
          Suggested Matches
          <Badge variant="secondary" className="text-[10px]">{suggestions.length}</Badge>
        </h3>
        {suggestions.length === 0 ? (
          <div className="text-center py-8 text-sm text-slate-400 border border-dashed border-slate-200 rounded-xl" data-testid="no-suggestions">
            No suggestions available. All similar items are either already linked or have identical names.
          </div>
        ) : (
          <div className="space-y-2.5" data-testid="suggestions-list">
            {suggestions.map((s) => (
              <SuggestionCard key={`${s.name_a}|${s.name_b}`} suggestion={s} onLink={handleLink} linking={linking} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ======================== DECISIONS SUMMARY ========================
function DecisionsSummary({ comparisons }) {
  const decisions = useMemo(() => {
    return comparisons
      .filter(g => g.is_multi_vendor && g.spread_pct > 0)
      .sort((a, b) => b.spread_pct - a.spread_pct)
      .map(g => {
        const best = g.entries[0];
        const worst = g.entries[g.entries.length - 1];
        return { item: g.item_key, bestVendor: best.vendor, worstVendor: worst.vendor, spread: g.spread_pct, bestPrice: g.best_price, unit: g.comparison_unit };
      });
  }, [comparisons]);

  if (decisions.length === 0) return null;

  return (
    <Card className="border border-emerald-200 shadow-sm bg-emerald-50/30" data-testid="decisions-summary">
      <CardContent className="py-4 px-5">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck className="w-5 h-5 text-emerald-600" />
          <h3 className="text-sm font-heading font-bold text-emerald-900">
            {decisions.length} Quick Decision{decisions.length !== 1 ? 's' : ''}
          </h3>
          <span className="text-[10px] text-emerald-600">items with multi-vendor pricing</span>
        </div>
        <div className="space-y-1.5">
          {decisions.map(d => (
            <div key={d.item} className="flex items-center gap-2 text-sm" data-testid={`quick-decision-${d.item}`}>
              <ArrowRight className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
              <span className="text-slate-700">
                <span className="font-semibold text-navy-900">{d.item}</span>
                <span className="text-slate-400 mx-1">—</span>
                Buy from <span className="font-semibold text-emerald-700">{d.bestVendor}</span>
                <span className="text-slate-400 mx-1">to save</span>
                <span className={`font-bold ${d.spread >= 15 ? 'text-red-600' : d.spread >= 8 ? 'text-amber-600' : 'text-emerald-600'}`}>{d.spread}%</span>
                <span className="text-slate-400 mx-1">vs</span>
                <span className="text-slate-500">{d.worstVendor}</span>
                <span className="text-[11px] font-mono text-slate-400 ml-1">({fmtPrice(d.bestPrice)}/{d.unit})</span>
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ======================== MAIN PAGE ========================
export default function VendorComparisonPage() {
  const { api } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [showMatching, setShowMatching] = useState(false);

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
    if (filter === 'confirmed') groups = groups.filter(g => g.match_source === 'user_confirmed');
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      groups = groups.filter(g =>
        g.item_key.toLowerCase().includes(q) ||
        g.entries.some(e => e.vendor.toLowerCase().includes(q) || e.raw_name.toLowerCase().includes(q))
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
  const confirmedCount = stats.user_confirmed_groups || 0;

  return (
    <div className="max-w-[1400px] space-y-6" data-testid="vendor-comparison-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">
            Vendor Price Comparison
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Normalized $/LB comparison — exact match + user-confirmed links
          </p>
        </div>
        <Button
          variant={showMatching ? 'default' : 'outline'}
          className={`gap-2 text-xs h-9 ${showMatching ? 'bg-indigo-600 hover:bg-indigo-700 text-white' : 'border-indigo-200 text-indigo-700 hover:bg-indigo-50'}`}
          onClick={() => setShowMatching(v => !v)}
          data-testid="toggle-matching-btn"
        >
          <Link2 className="w-4 h-4" />
          {showMatching ? 'Hide Item Matching' : 'Manage Item Matches'}
          {confirmedCount > 0 && !showMatching && (
            <Badge className="text-[9px] bg-indigo-100 text-indigo-700 ml-1">{confirmedCount}</Badge>
          )}
        </Button>
      </div>

      {/* Item Matching Panel */}
      {showMatching && (
        <Card className="border border-indigo-200 shadow-sm" data-testid="matching-panel-card">
          <CardHeader className="pb-3">
            <CardTitle className="font-heading text-base font-bold flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
                <Link2 className="w-4 h-4 text-indigo-600" />
              </div>
              Item Matching
            </CardTitle>
            <p className="text-[11px] text-slate-400 mt-1">
              Review suggestions and manually confirm which items are the same product across vendors.
              Only confirmed links are used in comparisons — never automatic.
            </p>
          </CardHeader>
          <CardContent>
            <ItemMatchingPanel api={api} onMappingChange={load} />
          </CardContent>
        </Card>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Package} iconBg="bg-teal-600" label="Qualifying Items" value={stats.total_qualifying_items || 0} sub="parsed with valid $/LB" testId="stat-qualifying" />
        <StatCard icon={Scale} iconBg="bg-indigo-600" label="Item Groups" value={stats.total_groups || 0} sub="distinct items compared" testId="stat-groups" />
        <StatCard icon={Users} iconBg="bg-amber-600" label="Multi-Vendor" value={stats.multi_vendor_groups || 0} sub="items with 2+ vendors" testId="stat-multi-vendor" />
        <StatCard icon={TrendingDown} iconBg="bg-emerald-600" label="Vendors" value={stats.vendors_represented || 0} sub="in qualifying data" testId="stat-vendors" />
      </div>

      {/* Quick Decisions Summary */}
      <DecisionsSummary comparisons={data?.comparisons || []} />

      {/* Info banner */}
      <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-slate-50 border border-slate-100" data-testid="comparison-info-banner">
        <Info className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
        <div className="text-[11px] text-slate-500 leading-relaxed">
          <span className="font-semibold text-slate-600">How this works:</span> Items are grouped by exact name match by default.
          Use <button onClick={() => setShowMatching(true)} className="font-semibold text-indigo-600 hover:underline">Item Matching</button> to
          manually link similar items across vendors.
          Only <span className="font-mono font-semibold text-teal-700">$/LB</span> from parsed pack sizes is compared — never raw case prices.
        </div>
      </div>

      {!hasData ? (
        <Card className="border border-slate-100 shadow-sm" data-testid="comparison-empty">
          <CardContent className="flex flex-col items-center py-16 text-center">
            <Scale className="w-12 h-12 text-slate-200 mb-4" />
            <h3 className="text-base font-heading font-bold text-navy-900 mb-1">No comparison data yet</h3>
            <p className="text-sm text-slate-400 max-w-md">
              Add purchase records with pack sizes (e.g., "4/10 LB") from the Expenses page.
              Only items with parsed weights in LB or OZ appear here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Filters */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input className="pl-9 h-9 text-sm" placeholder="Search item or vendor..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="comparison-search" />
            </div>
            <div className="flex gap-1.5">
              {[
                { key: 'all', label: 'All Items' },
                { key: 'multi', label: 'Multi-Vendor' },
                { key: 'single', label: 'Single Vendor' },
                { key: 'confirmed', label: 'Confirmed Links' },
              ].map(f => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                    filter === f.key ? 'bg-navy-900 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
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
              <div className="text-center py-12 text-sm text-slate-400">No items match your search or filter</div>
            ) : (
              filtered.map((group, i) => (
                <ComparisonGroup key={`${group.item_key}-${group.match_source}`} group={group} defaultOpen={i < 3} />
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
