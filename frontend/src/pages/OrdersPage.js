import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import {
  ShoppingCart, Plus, Trash2, Search, Package, Info, X, AlertCircle, Sparkles,
} from 'lucide-react';

// ─── ItemPicker (modal-embedded) ─────────────────────────────────────
function ItemPicker({ items, onPick, excludeIds }) {
  const [q, setQ] = useState('');
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return items
      .filter(i => !excludeIds.has(i.id))
      .filter(i => !needle || (i.name || '').toLowerCase().includes(needle) || (i.category || '').toLowerCase().includes(needle))
      .slice(0, 60);
  }, [items, q, excludeIds]);

  return (
    <div className="border border-slate-200 rounded-lg" data-testid="item-picker">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100">
        <Search className="w-4 h-4 text-slate-400" />
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search catalog…"
          className="flex-1 bg-transparent outline-none text-sm"
          data-testid="item-picker-search"
        />
      </div>
      <div className="max-h-56 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-400">No items match</div>
        ) : filtered.map(it => (
          <button
            key={it.id}
            onClick={() => onPick(it)}
            className="w-full text-left flex items-center gap-3 px-3 py-2 hover:bg-slate-50 border-b border-slate-50 last:border-0 transition-colors"
            data-testid={`item-pick-${it.id}`}
          >
            <Package className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-medium text-navy-900 truncate">{it.name}</div>
              <div className="text-[10px] text-slate-500 truncate">
                {it.category || 'Uncategorized'}
                {it.storage_category && <> · <span className="capitalize">{it.storage_category}</span></>}
              </div>
            </div>
            <Plus className="w-3.5 h-3.5 text-teal-600" />
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Create Order Modal ─────────────────────────────────────────────
function CreateOrderModal({ open, onClose, onCreated, api, preseedItemIds }) {
  const [items, setItems] = useState([]);
  const [lines, setLines] = useState([]);
  const [vendor, setVendor] = useState('');
  const [orderDate, setOrderDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState({}); // item_id -> bool

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api.get('/items').then(async (r) => {
      const catalog = r.data || [];
      if (cancelled) return;
      setItems(catalog);

      // Smart re-order preseed: for each preseedItemIds, add a line with
      // enriched last-known price/vendor/unit. Quantities stay empty (spec).
      if (preseedItemIds && preseedItemIds.length > 0) {
        const byId = new Map(catalog.map((c) => [c.id, c]));
        const initialLines = preseedItemIds
          .map((id) => byId.get(id))
          .filter(Boolean)
          .map((it) => ({
            item_id: it.id,
            item_name: it.name,
            category: it.category || '',
            unit: '',
            quantity: 0,            // blank on purpose
            last_known_price: null,
            last_known_vendor: '',
          }));
        setLines(initialLines);
        // Enrich each in the background
        const lh = {};
        initialLines.forEach((l) => { lh[l.item_id] = true; });
        setLoadingHistory(lh);
        await Promise.all(initialLines.map(async (l) => {
          try {
            const hr = await api.get(`/items/${l.item_id}/price-history`);
            const rec = (hr.data?.records || []).slice(-1)[0];
            setLines((prev) => prev.map((x) => x.item_id === l.item_id ? {
              ...x,
              unit: rec?.unit || '',
              last_known_price: rec?.unit_price ?? null,
              last_known_vendor: rec?.vendor || '',
            } : x));
          } catch { /* ignore */ }
          finally { setLoadingHistory((lhp) => ({ ...lhp, [l.item_id]: false })); }
        }));
      } else {
        setLines([]);
      }
    }).catch(() => setItems([]));
    setVendor(''); setNote('');
    return () => { cancelled = true; };
  }, [open, api, preseedItemIds]);

  const excludeIds = useMemo(() => new Set(lines.map(l => l.item_id)), [lines]);

  const handlePick = async (it) => {
    // Add line immediately; enrich last price/vendor/unit in background.
    const line = {
      item_id: it.id,
      item_name: it.name,
      category: it.category || '',
      unit: '',
      quantity: 1,
      last_known_price: null,
      last_known_vendor: '',
    };
    setLines(prev => [...prev, line]);
    setLoadingHistory(lh => ({ ...lh, [it.id]: true }));
    try {
      const r = await api.get(`/items/${it.id}/price-history`);
      const rec = (r.data?.records || []).slice(-1)[0];  // latest
      setLines(prev => prev.map(l => l.item_id === it.id ? {
        ...l,
        unit: rec?.unit || '',
        last_known_price: rec?.unit_price ?? null,
        last_known_vendor: rec?.vendor || '',
      } : l));
    } catch { /* non-fatal — spec says "if available" */ }
    finally { setLoadingHistory(lh => ({ ...lh, [it.id]: false })); }
  };

  const handleRemove = (id) => setLines(prev => prev.filter(l => l.item_id !== id));
  const handleQty = (id, q) => setLines(prev => prev.map(l => l.item_id === id ? { ...l, quantity: Number(q) || 0 } : l));

  const estimated = useMemo(() => lines.reduce((acc, l) => {
    const p = Number(l.last_known_price || 0);
    const q = Number(l.quantity || 0);
    return acc + (p * q);
  }, 0), [lines]);

  const handleSave = async (status = 'draft') => {
    if (lines.length === 0) {
      toast.error('Add at least one item from the catalog');
      return;
    }
    setSaving(true);
    try {
      const body = {
        order_date: orderDate,
        vendor_name: vendor,
        note,
        status,
        items: lines.map(l => ({
          item_id: l.item_id,
          quantity: Number(l.quantity || 0),
          unit: l.unit || '',
          last_known_price: l.last_known_price,
          last_known_vendor: l.last_known_vendor || '',
        })),
      };
      const r = await api.post('/orders', body);
      toast.success(`Order ${status === 'draft' ? 'saved as draft' : 'marked as submitted'}`);
      onCreated?.(r.data);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to save order');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col" data-testid="create-order-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShoppingCart className="w-4 h-4 text-teal-600" /> New Order
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          {/* Guardrail banner */}
          <div className="flex items-start gap-2 p-2.5 bg-amber-50 border border-amber-200 rounded-md text-[11px] text-amber-800" data-testid="orders-guardrail">
            <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span>
              Orders are built from your <strong>Item Catalog</strong>. Free-text product entry is not allowed —
              this keeps every order tied to a canonical product.
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] font-semibold text-slate-600 block mb-1">Order Date</label>
              <Input type="date" value={orderDate} onChange={e => setOrderDate(e.target.value)} data-testid="order-date" />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-600 block mb-1">Vendor (optional)</label>
              <Input placeholder="e.g., Sysco" value={vendor} onChange={e => setVendor(e.target.value)} data-testid="order-vendor" />
            </div>
          </div>

          <div>
            <label className="text-[11px] font-semibold text-slate-600 block mb-1">Pick from Item Catalog</label>
            <ItemPicker items={items} onPick={handlePick} excludeIds={excludeIds} />
          </div>

          <div>
            <label className="text-[11px] font-semibold text-slate-600 block mb-1">
              Line Items ({lines.length})
            </label>
            {lines.length === 0 ? (
              <div className="border border-dashed border-slate-300 rounded-lg py-8 text-center text-xs text-slate-400" data-testid="empty-lines">
                No items yet — pick from the catalog above.
              </div>
            ) : (
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                {lines.map(l => (
                  <div key={l.item_id} className="flex items-center gap-3 px-3 py-2 border-b border-slate-100 last:border-0" data-testid={`line-${l.item_id}`}>
                    <Package className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium text-navy-900 truncate">{l.item_name}</div>
                      <div className="text-[10px] text-slate-500 truncate">
                        {l.category || 'Uncategorized'}
                        {loadingHistory[l.item_id] && <> · loading last price…</>}
                        {!loadingHistory[l.item_id] && l.last_known_price != null && (
                          <> · last ${Number(l.last_known_price).toFixed(2)}{l.unit ? `/${l.unit}` : ''}{l.last_known_vendor && <> · {l.last_known_vendor}</>}</>
                        )}
                      </div>
                    </div>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={l.quantity}
                      onChange={e => handleQty(l.item_id, e.target.value)}
                      className="w-20 h-8 text-xs"
                      data-testid={`line-qty-${l.item_id}`}
                    />
                    <span className="text-[11px] text-slate-500 w-10">{l.unit || ''}</span>
                    <button
                      onClick={() => handleRemove(l.item_id)}
                      className="text-slate-400 hover:text-red-500 transition-colors"
                      data-testid={`line-remove-${l.item_id}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="text-[11px] font-semibold text-slate-600 block mb-1">Note (optional)</label>
            <Textarea value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder="e.g., for weekend service" data-testid="order-note" />
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between gap-2 border-t border-slate-100 pt-3 mt-3">
          <div className="text-xs text-slate-500">
            Estimated total: <span className="font-semibold text-navy-900">${estimated.toFixed(2)}</span>
            <span className="text-[10px] text-slate-400 ml-2">(based on last-known prices — informational only)</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={onClose} data-testid="cancel-order">Cancel</Button>
            <Button variant="outline" onClick={() => handleSave('draft')} disabled={saving} data-testid="save-draft-order">
              Save as Draft
            </Button>
            <Button onClick={() => handleSave('submitted')} disabled={saving} className="bg-teal-600 hover:bg-teal-700" data-testid="submit-order">
              Mark as Submitted
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Orders Page ────────────────────────────────────────────────────
export default function OrdersPage() {
  const { api } = useAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [preseed, setPreseed] = useState(null); // array of item_ids

  const load = () => {
    setLoading(true);
    api.get('/orders').then(r => setOrders(r.data?.items || [])).finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this order?')) return;
    try {
      await api.delete(`/orders/${id}`);
      toast.success('Order deleted');
      setOrders(o => o.filter(x => x.id !== id));
    } catch { toast.error('Failed to delete order'); }
  };

  const lastOrder = orders && orders.length > 0 ? orders[0] : null;
  const hasLastOrder = !!(lastOrder && lastOrder.items && lastOrder.items.length > 0);

  const handleSmartReorder = () => {
    if (!hasLastOrder) {
      toast.error('No previous order to re-order from');
      return;
    }
    const ids = lastOrder.items.map((it) => it.item_id).filter(Boolean);
    setPreseed(ids);
    setModalOpen(true);
    toast.info('Re-order preloaded — review quantities before saving', { duration: 4000 });
  };

  const handleNewOrder = () => {
    setPreseed(null);
    setModalOpen(true);
  };
  const handleCloseModal = () => {
    setModalOpen(false);
    setPreseed(null);
  };

  return (
    <div className="space-y-6" data-testid="orders-page">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold text-navy-900 flex items-center gap-2">
            <ShoppingCart className="w-5 h-5 text-teal-600" /> Orders
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Build item-driven orders from your catalog. Lightweight preview — this page does not
            execute external purchases.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {hasLastOrder && (
            <Button
              onClick={handleSmartReorder}
              variant="outline"
              className="gap-1.5 border-teal-300 text-teal-700 hover:bg-teal-50"
              data-testid="smart-reorder-btn"
            >
              <Sparkles className="w-4 h-4" /> Re-order last week (Smart)
            </Button>
          )}
          <Button onClick={handleNewOrder} className="bg-teal-600 hover:bg-teal-700" data-testid="new-order-btn">
            <Plus className="w-4 h-4 mr-1.5" /> New Order
          </Button>
        </div>
      </div>

      <div className="flex items-start gap-2 p-3 bg-slate-50 border border-slate-200 rounded-lg text-[12px] text-slate-600" data-testid="orders-info-banner">
        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5 text-slate-400" />
        <span>
          Orders are <strong>Item-driven</strong>. Every line must reference a product in your Item Catalog —
          free-text entries are disabled to prevent duplicate product definitions.
          Procurement recommendations are <strong>not</strong> auto-applied here.
          Smart re-order preloads items from your most recent order — quantities stay blank so you can review.
          <a href="/procurement" className="ml-1 font-semibold text-teal-700 hover:underline" data-testid="orders-procurement-link">Better price available? View Procurement →</a>
        </span>
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : orders.length === 0 ? (
        <div className="border border-dashed border-slate-300 rounded-xl py-16 text-center" data-testid="orders-empty-state">
          <ShoppingCart className="w-8 h-8 text-slate-300 mx-auto mb-3" />
          <p className="text-sm font-semibold text-navy-900">No orders yet</p>
          <p className="text-xs text-slate-500 mt-1">Click <strong>New Order</strong> to build one from your Item Catalog.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="orders-list">
          {orders.map(o => (
            <div key={o.id} className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`order-row-${o.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <Badge className={o.status === 'draft' ? 'bg-slate-100 text-slate-600' : 'bg-teal-100 text-teal-700'}>
                      {o.status}
                    </Badge>
                    <span className="text-xs text-slate-500">{o.order_date || '—'}</span>
                    {o.vendor_name && <span className="text-xs text-slate-500">· {o.vendor_name}</span>}
                    <span className="text-xs text-slate-500">· {o.items?.length || 0} items</span>
                    <span className="text-xs font-semibold text-navy-900">· ${Number(o.total_estimated || 0).toFixed(2)}</span>
                  </div>
                  {o.items?.length > 0 && (
                    <div className="text-[11px] text-slate-500 truncate">
                      {o.items.slice(0, 4).map(it => `${it.item_name} × ${it.quantity}${it.unit ? ' '+it.unit : ''}`).join(' · ')}
                      {o.items.length > 4 && ` · +${o.items.length - 4} more`}
                    </div>
                  )}
                  {o.note && <div className="text-[11px] text-slate-500 italic mt-1">"{o.note}"</div>}
                </div>
                <button
                  onClick={() => handleDelete(o.id)}
                  className="text-slate-400 hover:text-red-500 transition-colors p-1"
                  data-testid={`order-delete-${o.id}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateOrderModal open={modalOpen} onClose={handleCloseModal} onCreated={() => load()} api={api} preseedItemIds={preseed} />
    </div>
  );
}
