import { useState, useEffect, useMemo, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { dataEvents } from '@/lib/dataEvents';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { Search, Plus, Edit, Trash2, Loader2, Tag, X, Package, TrendingUp, ArrowUp, ArrowDown, Minus, Scale, Award, Snowflake, Sun, Thermometer, Sparkles, CheckCircle2, XCircle, GitMerge, AlertTriangle } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import { ConfirmDeleteDialog } from '@/components/ConfirmDeleteDialog';

function fmt(n) { return n != null ? `$${Number(n).toFixed(2)}` : '$0.00'; }

// ── Smart Duplicate Hint helpers ──
// Token-based Jaccard similarity between two names, after light normalization.
// Advisory only — never triggers server actions.
function _tokens(s) {
  if (!s) return [];
  return String(s)
    .toUpperCase()
    .replace(/[^A-Z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length >= 2);
}

function _jaccard(a, b) {
  const A = new Set(_tokens(a));
  const B = new Set(_tokens(b));
  if (A.size === 0 || B.size === 0) return 0;
  let inter = 0;
  for (const x of A) if (B.has(x)) inter++;
  const union = A.size + B.size - inter;
  return union > 0 ? inter / union : 0;
}

const DUPLICATE_HINT_THRESHOLD = 0.70;

// Returns {item, score} of the closest approved canonical item, or null.
function findClosestApproved(suggestedName, approvedItems) {
  if (!suggestedName) return null;
  let best = null;
  for (const it of approvedItems) {
    if (!it || it.is_suggested || it.is_archived) continue;
    const candidates = [it.name, ...((it.aliases || []).map(a => a.alias_name || a.alias))].filter(Boolean);
    let localBest = 0;
    for (const c of candidates) {
      const s = _jaccard(suggestedName, c);
      if (s > localBest) localBest = s;
    }
    if (localBest >= DUPLICATE_HINT_THRESHOLD && (!best || localBest > best.score)) {
      best = { item: it, score: localBest };
    }
  }
  return best;
}

function PriceHistoryDialog({ item, api, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!item) return;
    setLoading(true);
    api.get(`/items/${item.id}/price-history`)
      .then(res => setData(res.data))
      .catch(() => toast.error('Failed to load price history'))
      .finally(() => setLoading(false));
  }, [item, api]);

  if (!item) return null;

  const trend = data?.trend || [];
  const records = data?.records || [];
  const summary = data?.summary || {};

  // Compute price change for badge
  let changePct = null;
  if (trend.length >= 2) {
    const first = trend[0].avg_price;
    const last = trend[trend.length - 1].avg_price;
    if (first > 0) changePct = ((last - first) / first * 100).toFixed(1);
  }

  return (
    <Dialog open={!!item} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading text-lg flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-teal-600" />
            Price History — <span className="text-teal-600">{item.name}</span>
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div key="loading" className="space-y-3 py-4">{[1,2,3].map(i => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}</div>
        ) : records.length === 0 ? (
          <div key="empty" className="flex flex-col items-center py-12 text-center">
            <TrendingUp className="w-10 h-10 text-slate-300 mb-3" />
            <h3 className="font-heading text-sm font-bold text-navy-900 mb-1">No price data yet</h3>
            <p className="text-xs text-slate-400">Purchase invoices containing this item will populate the price history.</p>
          </div>
        ) : (
          <div key="data" className="space-y-5">
            {/* Summary KPIs */}
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-slate-50 rounded-lg p-3 text-center">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Avg Price</p>
                <p className="text-lg font-bold text-navy-900 tabular-nums mt-0.5">{fmt(summary.avg_price)}</p>
              </div>
              <div className="bg-slate-50 rounded-lg p-3 text-center">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Min</p>
                <p className="text-lg font-bold text-emerald-600 tabular-nums mt-0.5">{fmt(summary.min_price)}</p>
              </div>
              <div className="bg-slate-50 rounded-lg p-3 text-center">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Max</p>
                <p className="text-lg font-bold text-red-500 tabular-nums mt-0.5">{fmt(summary.max_price)}</p>
              </div>
              <div className="bg-slate-50 rounded-lg p-3 text-center">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Trend</p>
                <div className="flex items-center justify-center gap-1 mt-0.5">
                  {changePct !== null ? (
                    <>
                      {parseFloat(changePct) > 0 ? <ArrowUp className="w-4 h-4 text-red-500" /> : parseFloat(changePct) < 0 ? <ArrowDown className="w-4 h-4 text-emerald-600" /> : <Minus className="w-4 h-4 text-slate-400" />}
                      <span className={`text-lg font-bold tabular-nums ${parseFloat(changePct) > 0 ? 'text-red-500' : parseFloat(changePct) < 0 ? 'text-emerald-600' : 'text-slate-500'}`}>
                        {Math.abs(parseFloat(changePct))}%
                      </span>
                    </>
                  ) : <span className="text-lg font-bold text-slate-400">—</span>}
                </div>
              </div>
            </div>

            {/* Price Trend Chart */}
            {trend.length >= 2 && (
              <Card className="border border-slate-200/80 shadow-sm">
                <CardHeader className="pb-2 pt-4 px-5">
                  <CardTitle className="font-heading text-sm font-bold text-navy-900">Price Trend</CardTitle>
                </CardHeader>
                <CardContent className="px-2 pb-3">
                  <div className="h-52" data-testid="price-trend-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={trend} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(d) => { const parts = d.split('-'); return `${parts[1]}/${parts[2]}`; }} />
                        <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(v) => `$${v}`} width={50} />
                        <Tooltip
                          contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '12px' }}
                          formatter={(val) => [`$${val}`, 'Avg Price']}
                          labelFormatter={(d) => `Date: ${d}`}
                        />
                        <Line type="monotone" dataKey="avg_price" stroke="#0d9488" strokeWidth={2} dot={{ r: 3, fill: '#0d9488' }} activeDot={{ r: 5 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Price History Table */}
            <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="font-heading text-sm font-bold text-navy-900">
                  Purchase Records
                  <span className="text-[10px] font-normal text-slate-400 ml-2">{records.length} entries</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="px-0 pb-2">
                <div className="overflow-x-auto max-h-64 overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-50/80 hover:bg-slate-50/80 sticky top-0">
                        <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
                        <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Vendor</TableHead>
                        <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Item Name</TableHead>
                        <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Price</TableHead>
                        <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Qty</TableHead>
                        <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Unit</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {records.slice().reverse().map((r, i) => (
                        <TableRow key={i} className={`${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'}`} data-testid={`price-record-${i}`}>
                          <TableCell className="text-xs tabular-nums text-slate-600">{r.date}</TableCell>
                          <TableCell className="text-xs font-medium text-navy-900">{r.vendor}</TableCell>
                          <TableCell className="text-xs text-slate-500">{r.raw_name}</TableCell>
                          <TableCell className="text-xs text-right font-semibold text-navy-900 tabular-nums">{fmt(r.unit_price)}</TableCell>
                          <TableCell className="text-xs text-right tabular-nums text-slate-600">{r.quantity}</TableCell>
                          <TableCell className="text-xs text-slate-500">{r.unit}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ======================== VENDOR PRICE COMPARISON ========================
function VendorComparison({ api }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    api.get('/prices/vendor-comparison')
      .then(res => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [api]);

  if (loading) return <Card className="border border-slate-100 shadow-sm"><div className="p-6 space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-16 w-full rounded-lg" />)}</div></Card>;
  if (!data?.items?.length) return null;

  const q = filter.toLowerCase().trim();
  const filtered = q ? data.items.filter(it => it.item.toLowerCase().includes(q)) : data.items;

  return (
    <div className="space-y-4" data-testid="vendor-comparison-section">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-navy-900 flex items-center justify-center flex-shrink-0">
          <Scale className="w-4 h-4 text-white" />
        </div>
        <div>
          <h2 className="font-heading text-base font-extrabold text-navy-900 tracking-tight">Vendor Price Comparison</h2>
          <p className="text-[10px] text-slate-400">Latest prices per vendor for each item — lowest price highlighted</p>
        </div>
      </div>

      {data.items.length > 6 && (
        <div className="relative max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9 h-9 text-sm" placeholder="Filter items..." value={filter} onChange={(e) => setFilter(e.target.value)} data-testid="filter-comparison" />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((item) => (
          <Card key={item.item} className="border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow" data-testid={`comparison-card-${item.item}`}>
            <CardHeader className="pb-2 pt-4 px-5">
              <div className="flex items-center justify-between">
                <CardTitle className="font-heading text-sm font-bold text-navy-900">{item.item}</CardTitle>
                {item.savings_pct > 0 && (
                  <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] font-bold">
                    Save {item.savings_pct}%
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent className="px-5 pb-4 pt-0">
              <div className="space-y-1.5">
                {item.vendors.map((v, vi) => {
                  const isBest = v.vendor === item.best_vendor && item.vendor_count > 1;
                  return (
                    <div
                      key={v.vendor}
                      className={`flex items-center gap-3 rounded-lg px-3 py-2 transition-colors ${isBest ? 'bg-emerald-50 border border-emerald-200' : 'bg-slate-50/70'}`}
                      data-testid={`vendor-price-${item.item}-${vi}`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className={`text-xs font-semibold truncate ${isBest ? 'text-emerald-800' : 'text-navy-900'}`}>{v.vendor}</span>
                          {isBest && (
                            <Badge className="bg-emerald-600 text-white text-[8px] px-1.5 py-0 h-4 font-bold" data-testid={`best-badge-${item.item}`}>
                              <Award className="w-2.5 h-2.5 mr-0.5" /> BEST PRICE
                            </Badge>
                          )}
                        </div>
                        <span className="text-[10px] text-slate-400">{v.latest_date}{v.unit ? ` · per ${v.unit}` : ''} · {v.purchase_count} purchase{v.purchase_count !== 1 ? 's' : ''}</span>
                      </div>
                      <span className={`text-sm font-bold tabular-nums flex-shrink-0 ${isBest ? 'text-emerald-700' : 'text-navy-900'}`}>
                        {fmt(v.latest_price)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      {filtered.length === 0 && q && <p className="text-sm text-slate-400 text-center py-6">No items match "{filter}"</p>}
    </div>
  );
}

export default function ItemsPage() {
  const { api } = useAuth();
  const location = useLocation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [storageFilter, setStorageFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');   // all | suggested | approved
  const [dialogOpen, setDialogOpen] = useState(false);
  const [aliasDialog, setAliasDialog] = useState(null);
  const [priceItem, setPriceItem] = useState(null);
  const [form, setForm] = useState({ name: '', category: '', storage_category: '', category_source: 'auto' });
  const [aliasName, setAliasName] = useState('');
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, id: null });
  const [categoryUpdating, setCategoryUpdating] = useState(null);
  const [governing, setGoverning] = useState(null);  // item_id being promoted/dismissed/merged
  const [mergeDialog, setMergeDialog] = useState(null);   // suggested item being merged
  const [mergeTargets, setMergeTargets] = useState([]);
  const [mergeQuery, setMergeQuery] = useState('');
  const [mergeTargetId, setMergeTargetId] = useState('');
  const [mergeConfirming, setMergeConfirming] = useState(false);

  // Highlight support: when navigated to `/items?highlight=<id>`, scroll to
  // the matching row and apply a brief ring so the user can find the
  // canonical destination of a correction-memory link.
  const [highlightId, setHighlightId] = useState(null);
  const rowRefs = useRef({});

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const hid = params.get('highlight');
    setHighlightId(hid || null);
  }, [location.search]);

  // When both the highlight id is known AND the matching row is rendered,
  // scroll it into view. Clear the highlight after 3.5s so the ring fades.
  useEffect(() => {
    if (!highlightId || loading) return;
    const target = items.find(it => it.id === highlightId);
    if (!target) return;
    // If item is currently hidden by a filter, relax it to "all".
    if (target.is_suggested && statusFilter === 'approved') setStatusFilter('all');
    if (!target.is_suggested && statusFilter === 'suggested') setStatusFilter('all');
    const node = rowRefs.current[highlightId];
    if (node && node.scrollIntoView) {
      node.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    const t = setTimeout(() => setHighlightId(null), 3500);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightId, items, loading]);

  const load = async () => {
    setLoading(true);
    try {
      const params = { search };
      if (storageFilter && storageFilter !== 'all') params.storage_category = storageFilter;
      if (statusFilter && statusFilter !== 'all') params.status = statusFilter;
      const res = await api.get('/items', { params });
      setItems(res.data);
    }
    catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  };

  // Separate pool of approved items used only for the advisory Smart
  // Duplicate Hint on suggested rows. We keep it decoupled from the main
  // list so that filter changes (e.g. "Suggested" tab) don't break the hint.
  const [approvedItems, setApprovedItems] = useState([]);
  const loadApprovedItems = async () => {
    try {
      const r = await api.get('/items?status=approved');
      setApprovedItems(Array.isArray(r.data) ? r.data : []);
    } catch {
      setApprovedItems([]);
    }
  };

  useEffect(() => { load(); }, [search, storageFilter, statusFilter]); // eslint-disable-line
  useEffect(() => { loadApprovedItems(); }, []); // eslint-disable-line

  // Pre-compute duplicate hints for visible suggested items (advisory only).
  const duplicateHints = useMemo(() => {
    const out = {};
    if (!approvedItems.length) return out;
    for (const it of items) {
      if (!it.is_suggested) continue;
      const hit = findClosestApproved(it.name, approvedItems);
      if (hit) out[it.id] = hit;  // { item, score }
    }
    return out;
  }, [items, approvedItems]);

  const suggestedCount = items.filter(it => it.is_suggested).length;

  const promoteSuggested = async (item) => {
    setGoverning(item.id);
    try {
      await api.post(`/items/${item.id}/promote`);
      toast.success(`Promoted "${item.name}" to your catalog`);
      load();
      loadApprovedItems();
      dataEvents.emit();
    } catch (err) {
      toast.error('Could not promote: ' + (err.response?.data?.detail || ''));
    } finally { setGoverning(null); }
  };

  const dismissSuggested = async (item) => {
    if (!window.confirm(`Dismiss suggested item "${item.name}"? Aliases will be archived but your correction history stays intact.`)) return;
    setGoverning(item.id);
    try {
      await api.post(`/items/${item.id}/dismiss`);
      toast.info(`Dismissed "${item.name}"`);
      load();
      loadApprovedItems();
    } catch (err) {
      toast.error('Could not dismiss: ' + (err.response?.data?.detail || ''));
    } finally { setGoverning(null); }
  };

  const openMergeDialog = async (item) => {
    setMergeDialog(item);
    setMergeQuery('');
    setMergeTargetId('');
    setMergeConfirming(false);
    try {
      const r = await api.get('/items?status=approved');
      // Exclude the suggested item itself just in case
      setMergeTargets((r.data || []).filter(x => x.id !== item.id));
    } catch {
      setMergeTargets([]);
      toast.error('Could not load target items');
    }
  };

  const confirmMerge = async () => {
    if (!mergeDialog || !mergeTargetId) return;
    setGoverning(mergeDialog.id);
    try {
      const r = await api.post(`/items/${mergeDialog.id}/merge`, { target_item_id: mergeTargetId });
      const target = r.data?.target;
      const xfer = r.data?.aliases_transferred ?? 0;
      const dedup = r.data?.aliases_deduped ?? 0;
      toast.success(
        `Merged "${mergeDialog.name}" into "${target?.name || 'target'}" · ` +
        `${xfer} alias${xfer !== 1 ? 'es' : ''} transferred${dedup ? `, ${dedup} deduped` : ''}`
      );
      setMergeDialog(null);
      load();
      loadApprovedItems();
      dataEvents.emit();
    } catch (err) {
      toast.error('Could not merge: ' + (err.response?.data?.detail || ''));
    } finally {
      setGoverning(null);
    }
  };

  const filteredMergeTargets = useMemo(() => {
    const q = (mergeQuery || '').trim().toLowerCase();
    return (mergeTargets || [])
      .filter(it => !q || (it.name || '').toLowerCase().includes(q) || (it.aliases || []).some(a => (a.alias || '').toLowerCase().includes(q)))
      .slice(0, 60);
  }, [mergeTargets, mergeQuery]);

  const openNew = () => { setEditing(null); setForm({ name: '', category: '', storage_category: '', category_source: 'auto', variants: [] }); setDialogOpen(true); };
  const openEdit = (item) => { setEditing(item); setForm({ name: item.name, category: item.category || '', storage_category: item.storage_category || '', category_source: item.category_source || 'auto', variants: Array.isArray(item.variants) ? item.variants.map(v => ({ key: v.key || '', label: v.label || '' })) : [] }); setDialogOpen(true); };

  const updateStorageCategory = async (itemId, newCat) => {
    setCategoryUpdating(itemId);
    try {
      const res = await api.patch(`/items/${itemId}/storage-category`, { storage_category: newCat });
      setItems(prev => prev.map(it => it.id === itemId ? { ...it, ...res.data, aliases: it.aliases } : it));
      toast.success(`Category set to ${newCat || 'none'} (manual)`);
    } catch (err) {
      toast.error('Update failed: ' + (err.response?.data?.detail || err.message));
    } finally { setCategoryUpdating(null); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Clean up variants: drop empty rows, lowercase keys, default label→key.
      const variants = (form.variants || [])
        .map(v => ({ key: (v.key || '').trim().toLowerCase(), label: (v.label || '').trim() || (v.key || '').trim() }))
        .filter(v => v.key);
      const payload = { ...form, variants };
      if (editing) await api.put(`/items/${editing.id}`, payload);
      else await api.post('/items', payload);
      toast.success(editing ? 'Updated' : 'Created');
      setDialogOpen(false); load(); loadApprovedItems();
      // Notify every other page (Raw Materials, Expenses, Dashboard…) so they re-fetch
      // and render the new canonical name instantly via display_name enrichment.
      dataEvents.emit();
    } catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  const [itemInUse, setItemInUse] = useState(null);  // {id, name, linked_invoices, linked_rows}
  const requestDelete = (id) => setDeleteConfirm({ open: true, id });
  const handleDeleteConfirm = async () => {
    const { id } = deleteConfirm;
    setDeleteConfirm({ open: false, id: null });
    try {
      await api.delete(`/items/${id}`);
      toast.success('Deleted');
      load();
      loadApprovedItems();
      dataEvents.emit();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail && typeof detail === 'object' && detail.error === 'ITEM_IN_USE') {
        // Open the in-use modal instead of a generic toast
        setItemInUse({
          id,
          name: detail.canonical_name || 'this item',
          linked_invoices: detail.linked_invoices || 0,
          linked_rows: detail.linked_rows || 0,
        });
      } else {
        toast.error('Delete failed');
      }
    }
  };
  const cancelDelete = () => setDeleteConfirm({ open: false, id: null });

  const archiveInUseItem = async () => {
    if (!itemInUse) return;
    try {
      await api.post(`/items/${itemInUse.id}/archive`);
      toast.success(`Archived "${itemInUse.name}"`);
      setItemInUse(null);
      load();
      loadApprovedItems();
      dataEvents.emit();
    } catch (err) {
      toast.error('Archive failed: ' + (err.response?.data?.detail || ''));
    }
  };

  const mergeInUseItem = () => {
    if (!itemInUse) return;
    // Find the in-use item in our list and open the existing merge dialog flow.
    const target = items.find(it => it.id === itemInUse.id) || { id: itemInUse.id, name: itemInUse.name };
    setItemInUse(null);
    openMergeDialog(target);
  };

  const addAlias = async () => {
    if (!aliasName.trim() || !aliasDialog) return;
    try {
      await api.post('/aliases', { canonical_item_id: aliasDialog.id, alias_name: aliasName.trim() });
      setAliasName('');
      load();
    } catch { toast.error('Failed'); }
  };

  const deleteAlias = async (aliasId) => {
    try { await api.delete(`/aliases/${aliasId}`); load(); } catch { toast.error('Failed'); }
  };

  const currentAliasItem = items.find(i => i.id === aliasDialog?.id);

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="items-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Items</h1>
          <p className="text-sm text-slate-400 mt-1">Canonical items and name aliases</p>
        </div>
        <Button onClick={openNew} className="bg-navy-900 hover:bg-navy-800 text-white h-10 px-5" data-testid="add-item-btn">
          <Plus className="w-4 h-4 mr-2" /> Add Item
        </Button>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9 h-10" placeholder="Search items..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="search-items" />
        </div>
        <Tabs value={statusFilter} onValueChange={setStatusFilter}>
          <TabsList className="h-9" data-testid="status-filter-tabs">
            <TabsTrigger value="all" className="text-xs px-3" data-testid="filter-status-all">All</TabsTrigger>
            <TabsTrigger value="approved" className="text-xs px-3 gap-1" data-testid="filter-status-approved">
              <CheckCircle2 className="w-3 h-3" /> Approved
            </TabsTrigger>
            <TabsTrigger value="suggested" className="text-xs px-3 gap-1" data-testid="filter-status-suggested">
              <Sparkles className="w-3 h-3 text-amber-500" />
              Suggested
              {statusFilter !== 'suggested' && suggestedCount > 0 && (
                <span className="ml-1 bg-amber-500 text-white text-[9px] font-bold px-1.5 py-[1px] rounded-full" data-testid="filter-status-suggested-count">{suggestedCount}</span>
              )}
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <Tabs value={storageFilter} onValueChange={setStorageFilter}>
          <TabsList className="h-9">
            <TabsTrigger value="all" className="text-xs px-3" data-testid="filter-all">All Items</TabsTrigger>
            <TabsTrigger value="frozen" className="text-xs px-3 gap-1" data-testid="filter-frozen"><Snowflake className="w-3 h-3" />Frozen</TabsTrigger>
            <TabsTrigger value="chilled" className="text-xs px-3 gap-1" data-testid="filter-chilled"><Thermometer className="w-3 h-3" />Chilled</TabsTrigger>
            <TabsTrigger value="dry" className="text-xs px-3 gap-1" data-testid="filter-dry"><Sun className="w-3 h-3" />Dry</TabsTrigger>
            <TabsTrigger value="uncategorized" className="text-xs px-3 gap-1" data-testid="filter-uncategorized"><Package className="w-3 h-3" />Uncategorized</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {loading ? (
        <Card key="loading" className="border border-slate-100 shadow-sm overflow-hidden"><div className="p-6 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}</div></Card>
      ) : items.length === 0 ? (
        <div key="empty" className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4"><Package className="w-6 h-6 text-slate-300" /></div>
          <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No items yet</h3>
          <p className="text-sm text-slate-400">Add items to start normalizing invoice data.</p>
        </div>
      ) : (
        <Card key="data" className="border border-slate-100 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Item Name</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Category</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider w-40">Storage</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Aliases</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right w-48">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, i) => {
                  const hint = duplicateHints[item.id];
                  const isHighlighted = highlightId && highlightId === item.id;
                  return (
                  <TableRow
                    key={item.id}
                    ref={el => { if (el) rowRefs.current[item.id] = el; }}
                    className={`transition-all ${item.is_suggested ? 'bg-amber-50/60 hover:bg-amber-50/80' : (i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40')} hover:bg-teal-50/30 ${isHighlighted ? 'ring-2 ring-teal-500 ring-offset-1' : ''}`}
                    data-testid={`item-row-${item.id}`}
                    data-suggested={item.is_suggested ? 'true' : 'false'}
                    data-highlighted={isHighlighted ? 'true' : 'false'}
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className={`w-8 h-8 rounded-lg ${item.is_suggested ? 'bg-amber-500' : 'bg-navy-900'} text-white flex items-center justify-center text-[11px] font-bold flex-shrink-0`}>
                          {item.is_suggested ? <Sparkles className="w-3.5 h-3.5" /> : item.name?.charAt(0)}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-sm font-semibold text-navy-900">{item.name}</span>
                            {item.is_suggested && (
                              <Badge className="bg-amber-100 text-amber-800 border border-amber-300 text-[9px] font-bold uppercase h-4 px-1.5 gap-1" data-testid={`badge-suggested-${item.id}`}>
                                <Sparkles className="w-2.5 h-2.5" /> Suggested
                              </Badge>
                            )}
                            {Array.isArray(item.variants) && item.variants.length > 0 && (
                              <div className="flex flex-wrap gap-1" data-testid={`variants-chips-${item.id}`}>
                                {item.variants.map(v => (
                                  <Badge
                                    key={v.key}
                                    className="bg-indigo-50 text-indigo-700 border border-indigo-200 text-[9px] h-4 px-1.5 font-medium"
                                    data-testid={`variant-chip-${item.id}-${v.key}`}
                                  >
                                    {v.label || v.key}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </div>
                          {item.is_suggested && (
                            <p className="text-[10px] text-amber-700 italic mt-0.5" data-testid={`origin-hint-${item.id}`}>
                              Suggested from {item.suggested_source === 'user_edit' ? 'a user edit' : item.suggested_source || 'user activity'}
                            </p>
                          )}
                          {item.is_suggested && hint && (
                            <div
                              className="flex items-center gap-1 mt-1 text-[10px] text-indigo-700"
                              data-testid={`duplicate-hint-${item.id}`}
                              data-hint-target-id={hint.item.id}
                              data-hint-score={hint.score.toFixed(2)}
                              title="Advisory only — review and decide if you want to Merge."
                            >
                              <AlertTriangle className="w-2.5 h-2.5 flex-shrink-0" />
                              <span className="font-medium">
                                Possible duplicate of{' '}
                                <span className="font-bold">"{hint.item.name}"</span>
                              </span>
                              <span className="text-slate-400 ml-0.5">({Math.round(hint.score * 100)}% match)</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      {item.category ? <Badge variant="outline" className="text-[10px] font-semibold">{item.category}</Badge> : <span className="text-xs text-slate-300">—</span>}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <Select
                          value={item.storage_category || '_none'}
                          onValueChange={(v) => updateStorageCategory(item.id, v === '_none' ? '' : v)}
                          disabled={categoryUpdating === item.id}
                        >
                          <SelectTrigger className="h-7 w-28 text-[10px] border-slate-200" data-testid={`storage-cat-${item.id}`}>
                            <SelectValue placeholder="—" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="_none" className="text-[10px]">—</SelectItem>
                            <SelectItem value="frozen" className="text-[10px]"><span className="flex items-center gap-1"><Snowflake className="w-3 h-3 text-blue-500" />Frozen</span></SelectItem>
                            <SelectItem value="chilled" className="text-[10px]"><span className="flex items-center gap-1"><Thermometer className="w-3 h-3 text-cyan-500" />Chilled</span></SelectItem>
                            <SelectItem value="dry" className="text-[10px]"><span className="flex items-center gap-1"><Sun className="w-3 h-3 text-amber-500" />Dry</span></SelectItem>
                            <SelectItem value="uncategorized" className="text-[10px]"><span className="flex items-center gap-1"><Package className="w-3 h-3 text-slate-400" />Uncategorized</span></SelectItem>
                          </SelectContent>
                        </Select>
                        {item.category_source === 'manual' && (
                          <Badge className="text-[8px] bg-indigo-50 text-indigo-600 border-indigo-200 px-1 py-0 h-4">manual</Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1 max-w-md">
                        {(item.aliases || []).slice(0, 4).map((a) => (
                          <Badge key={a.id} variant="secondary" className="text-[10px] bg-teal-50 text-teal-700 font-medium">{a.alias_name}</Badge>
                        ))}
                        {(item.aliases?.length || 0) > 4 && <Badge variant="secondary" className="text-[10px] bg-slate-100 text-slate-500 font-medium">+{item.aliases.length - 4}</Badge>}
                        {!item.aliases?.length && <span className="text-[11px] text-slate-300 italic">None</span>}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1 items-center flex-wrap">
                        {item.is_suggested && (
                          <>
                            <Button
                              size="sm"
                              className="h-7 px-2 text-[10px] bg-teal-600 hover:bg-teal-700 text-white gap-1"
                              onClick={() => promoteSuggested(item)}
                              disabled={governing === item.id}
                              data-testid={`promote-item-${item.id}`}
                            >
                              <CheckCircle2 className="w-3 h-3" /> Promote
                            </Button>
                            <Button
                              size="sm" variant="outline"
                              className="h-7 px-2 text-[10px] border-indigo-300 text-indigo-700 hover:bg-indigo-50 gap-1"
                              onClick={() => openMergeDialog(item)}
                              disabled={governing === item.id}
                              data-testid={`merge-item-${item.id}`}
                            >
                              <GitMerge className="w-3 h-3" /> Merge
                            </Button>
                            <Button
                              size="sm" variant="outline"
                              className="h-7 px-2 text-[10px] border-slate-300 text-slate-600 gap-1"
                              onClick={() => dismissSuggested(item)}
                              disabled={governing === item.id}
                              data-testid={`dismiss-item-${item.id}`}
                            >
                              <XCircle className="w-3 h-3" /> Dismiss
                            </Button>
                          </>
                        )}
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-[10px] text-slate-500 hover:text-teal-700" onClick={() => setPriceItem(item)} data-testid={`price-history-${item.id}`}>
                          <TrendingUp className="w-3 h-3 mr-1" /> Prices
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-[10px] text-slate-500 hover:text-teal-700" onClick={() => { setAliasDialog(item); setAliasName(''); }} data-testid={`manage-aliases-${item.id}`}>
                          <Tag className="w-3 h-3 mr-1" /> Aliases
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEdit(item)} data-testid={`edit-item-${item.id}`}><Edit className="w-3.5 h-3.5 text-slate-500" /></Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => requestDelete(item.id)} data-testid={`delete-item-${item.id}`}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      {/* Vendor Price Comparison */}
      <VendorComparison api={api} />

      {/* Add/Edit Item Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-heading text-lg">{editing ? 'Edit Item' : 'New Item'}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Item Name</Label><Input className="mt-1.5 h-10" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="input-item-name" /></div>
            <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Category</Label><Input className="mt-1.5 h-10" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="e.g. Meat, Dairy, Vegetables" /></div>
            <div>
              <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Storage Category</Label>
              <Select value={form.storage_category || '_none'} onValueChange={(v) => setForm({ ...form, storage_category: v === '_none' ? '' : v, category_source: v === '_none' ? 'auto' : 'manual' })}>
                <SelectTrigger className="mt-1.5 h-10" data-testid="input-storage-category">
                  <SelectValue placeholder="Select storage type..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">None</SelectItem>
                  <SelectItem value="frozen"><span className="flex items-center gap-2"><Snowflake className="w-3.5 h-3.5 text-blue-500" />Frozen</span></SelectItem>
                  <SelectItem value="chilled"><span className="flex items-center gap-2"><Thermometer className="w-3.5 h-3.5 text-cyan-500" />Chilled</span></SelectItem>
                  <SelectItem value="dry"><span className="flex items-center gap-2"><Sun className="w-3.5 h-3.5 text-amber-500" />Dry</span></SelectItem>
                  <SelectItem value="uncategorized"><span className="flex items-center gap-2"><Package className="w-3.5 h-3.5 text-slate-400" />Uncategorized</span></SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Variants <span className="text-slate-300 font-normal normal-case">(optional — e.g. male/female, small/large)</span></Label>
              <div className="mt-1.5 space-y-2" data-testid="variants-editor">
                {(form.variants || []).map((v, vi) => (
                  <div key={vi} className="flex gap-2 items-center" data-testid={`variant-row-${vi}`}>
                    <Input
                      className="h-8 text-xs flex-1"
                      placeholder="key (e.g. male)"
                      value={v.key}
                      onChange={(e) => {
                        const next = [...(form.variants || [])];
                        next[vi] = { ...next[vi], key: e.target.value.trim().toLowerCase() };
                        setForm({ ...form, variants: next });
                      }}
                      data-testid={`variant-key-${vi}`}
                    />
                    <Input
                      className="h-8 text-xs flex-1"
                      placeholder="label (e.g. Male)"
                      value={v.label}
                      onChange={(e) => {
                        const next = [...(form.variants || [])];
                        next[vi] = { ...next[vi], label: e.target.value };
                        setForm({ ...form, variants: next });
                      }}
                      data-testid={`variant-label-${vi}`}
                    />
                    <Button
                      type="button" variant="ghost" size="sm"
                      className="h-8 w-8 p-0 text-slate-400 hover:text-red-500"
                      onClick={() => setForm({ ...form, variants: (form.variants || []).filter((_, i) => i !== vi) })}
                      data-testid={`variant-remove-${vi}`}
                    >
                      <X className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ))}
                <Button
                  type="button" variant="outline" size="sm"
                  className="h-7 text-[11px] gap-1"
                  onClick={() => setForm({ ...form, variants: [...(form.variants || []), { key: '', label: '' }] })}
                  data-testid="variant-add"
                >
                  <Plus className="w-3 h-3" /> Add variant
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving || !form.name} className="bg-teal-600 hover:bg-teal-700 text-white" data-testid="save-item-btn">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null} Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Aliases Dialog */}
      <Dialog open={!!aliasDialog} onOpenChange={() => setAliasDialog(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-heading text-lg">Aliases for <span className="text-teal-600">{aliasDialog?.name}</span></DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="flex gap-2">
              <Input value={aliasName} onChange={(e) => setAliasName(e.target.value)} placeholder="Type alias name..." className="flex-1 h-10" data-testid="input-alias-name" onKeyDown={(e) => e.key === 'Enter' && addAlias()} />
              <Button onClick={addAlias} disabled={!aliasName.trim()} className="bg-teal-600 hover:bg-teal-700 text-white h-10"><Plus className="w-4 h-4" /></Button>
            </div>
            <div className="flex flex-wrap gap-2 min-h-[40px]">
              {currentAliasItem?.aliases?.map((a) => (
                <Badge key={a.id} className="bg-slate-100 text-slate-700 hover:bg-slate-200 gap-1.5 pr-1.5 text-xs">
                  {a.alias_name}
                  <button onClick={() => deleteAlias(a.id)} className="hover:text-red-500 transition-colors"><X className="w-3 h-3" /></button>
                </Badge>
              ))}
              {!currentAliasItem?.aliases?.length && <p className="text-xs text-slate-400 italic">No aliases yet. Add one above.</p>}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Price History Dialog */}
      <PriceHistoryDialog item={priceItem} api={api} onClose={() => setPriceItem(null)} />
      <ConfirmDeleteDialog open={deleteConfirm.open} onClose={cancelDelete} onConfirm={handleDeleteConfirm} message="Are you sure you want to delete this item and all its aliases?" />

      {/* Item In-Use blocker — fired when DELETE returns ITEM_IN_USE */}
      <Dialog open={!!itemInUse} onOpenChange={(o) => !o && setItemInUse(null)}>
        <DialogContent className="max-w-md" data-testid="item-in-use-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading text-lg flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              Item is in use
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-slate-700">
              <span className="font-semibold">"{itemInUse?.name}"</span> is used in
              existing invoices and cannot be deleted.
            </p>
            <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200">
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Linked invoices</p>
                <p className="text-2xl font-bold text-navy-900 tabular-nums" data-testid="in-use-linked-invoices">{itemInUse?.linked_invoices ?? 0}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Linked rows</p>
                <p className="text-2xl font-bold text-navy-900 tabular-nums" data-testid="in-use-linked-rows">{itemInUse?.linked_rows ?? 0}</p>
              </div>
            </div>
            <p className="text-xs text-slate-500">
              Deleting it would orphan those invoice rows. Choose a safe action below.
            </p>
          </div>
          <DialogFooter className="flex-col-reverse sm:flex-row sm:justify-between sm:gap-2">
            <Button variant="ghost" onClick={() => setItemInUse(null)} data-testid="in-use-cancel">Cancel</Button>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={archiveInUseItem}
                className="border-slate-300 gap-1"
                data-testid="in-use-archive"
              >
                Archive item
              </Button>
              <Button
                onClick={mergeInUseItem}
                className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1"
                data-testid="in-use-merge"
              >
                <GitMerge className="w-3.5 h-3.5" /> Merge into another
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Merge Suggested → Existing Item Dialog */}
      <Dialog open={!!mergeDialog} onOpenChange={(o) => !o && setMergeDialog(null)}>
        <DialogContent className="max-w-lg" data-testid="merge-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading text-lg flex items-center gap-2">
              <GitMerge className="w-4 h-4 text-indigo-600" />
              Merge into existing item
            </DialogTitle>
          </DialogHeader>
          {!mergeConfirming ? (
            <>
              <div className="flex items-start gap-2 p-2.5 bg-amber-50 border border-amber-200 rounded-md text-[11px] text-amber-800" data-testid="merge-context">
                <Sparkles className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>
                  Suggested: <span className="font-semibold">{mergeDialog?.name}</span>.
                  Pick an existing approved item — we will add this suggestion as an alias and
                  keep your correction history intact. No duplicate catalog entry will be created.
                </span>
              </div>
              <div className="relative mt-2">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <Input
                  className="pl-9 h-9 text-sm"
                  placeholder="Search approved items..."
                  value={mergeQuery}
                  onChange={(e) => setMergeQuery(e.target.value)}
                  data-testid="merge-search"
                  autoFocus
                />
              </div>
              <div className="border border-slate-200 rounded-lg max-h-64 overflow-y-auto mt-2" data-testid="merge-target-list">
                {filteredMergeTargets.length === 0 ? (
                  <div className="p-6 text-center text-xs text-slate-400" data-testid="merge-target-empty">
                    {mergeQuery ? 'No approved items match' : 'No approved items available as merge targets'}
                  </div>
                ) : filteredMergeTargets.map(it => (
                  <button
                    key={it.id}
                    onClick={() => setMergeTargetId(it.id)}
                    className={`w-full text-left px-3 py-2 border-b border-slate-100 last:border-0 transition-colors ${
                      mergeTargetId === it.id ? 'bg-teal-50 border-l-2 border-l-teal-600' : 'hover:bg-slate-50'
                    }`}
                    data-testid={`merge-target-${it.id}`}
                  >
                    <div className="flex items-center gap-2">
                      <div className={`w-6 h-6 rounded bg-navy-900 text-white flex items-center justify-center text-[10px] font-bold flex-shrink-0`}>
                        {it.name?.charAt(0)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[12px] font-semibold text-navy-900 truncate">{it.name}</p>
                        <p className="text-[10px] text-slate-500 truncate">
                          {(it.aliases || []).length} alias{(it.aliases || []).length !== 1 ? 'es' : ''}
                          {it.category && <> · {it.category}</>}
                        </p>
                      </div>
                      {mergeTargetId === it.id && <CheckCircle2 className="w-4 h-4 text-teal-600 flex-shrink-0" />}
                    </div>
                  </button>
                ))}
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setMergeDialog(null)} data-testid="merge-cancel">Cancel</Button>
                <Button
                  disabled={!mergeTargetId}
                  onClick={() => setMergeConfirming(true)}
                  className="bg-indigo-600 hover:bg-indigo-700 gap-1"
                  data-testid="merge-next"
                >
                  Next <GitMerge className="w-3 h-3" />
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <div className="text-sm text-slate-700 space-y-3" data-testid="merge-confirm-step">
                <p>
                  You're about to merge
                  <span className="font-semibold text-amber-700"> "{mergeDialog?.name}"</span>
                  {' '}into
                  <span className="font-semibold text-teal-700"> "{mergeTargets.find(t => t.id === mergeTargetId)?.name}"</span>.
                </p>
                <ul className="text-[12px] text-slate-600 list-disc pl-5 space-y-1">
                  <li>The suggestion's name + aliases become aliases on the existing item</li>
                  <li>Correction memory rows are preserved</li>
                  <li>No duplicate canonical item will be created</li>
                  <li>The suggestion is archived (non-destructive)</li>
                </ul>
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setMergeConfirming(false)} data-testid="merge-confirm-back">Back</Button>
                <Button
                  onClick={confirmMerge}
                  disabled={governing === mergeDialog?.id}
                  className="bg-indigo-600 hover:bg-indigo-700 gap-1"
                  data-testid="merge-confirm"
                >
                  {governing === mergeDialog?.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <GitMerge className="w-3 h-3" />}
                  Confirm merge
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
