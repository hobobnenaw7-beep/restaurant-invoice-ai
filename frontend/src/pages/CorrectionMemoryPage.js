import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Brain, Trash2, Pencil, ChevronLeft, Package, ArrowRight, Clock, ToggleRight } from 'lucide-react';

// ── Helpers ──

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function describeChanges(c) {
  const changes = [];
  if (c.original_raw_name && c.corrected_name && c.original_raw_name !== c.corrected_name) {
    changes.push({ field: 'Name', from: c.original_raw_name, to: c.corrected_name });
  }
  const specs = c.corrected_specs || {};
  if (specs.pack_size) changes.push({ field: 'Pack size', from: '—', to: specs.pack_size });
  if (specs.unit_price != null) changes.push({ field: 'Unit price', from: '—', to: `$${Number(specs.unit_price).toFixed(2)}` });
  if (specs.total != null) changes.push({ field: 'Total', from: '—', to: `$${Number(specs.total).toFixed(2)}` });
  return changes;
}

// ── Main Page ──

export default function CorrectionMemoryPage() {
  const { api } = useAuth();
  const [vendors, setVendors] = useState([]);
  const [selectedVendor, setSelectedVendor] = useState(null);
  const [corrections, setCorrections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editDialog, setEditDialog] = useState(null);

  // Fetch vendor list
  const fetchVendors = useCallback(async () => {
    try {
      const res = await api.get('/corrections/vendors');
      setVendors(res.data || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, [api]);

  useEffect(() => { fetchVendors(); }, [fetchVendors]);

  // Fetch corrections for selected vendor
  const selectVendor = useCallback(async (v) => {
    setSelectedVendor(v);
    try {
      const res = await api.get(`/corrections/by-vendor/${v.supplier_id}`);
      setCorrections(res.data || []);
    } catch { setCorrections([]); }
  }, [api]);

  // Toggle enabled
  const toggleEnabled = useCallback(async (c) => {
    const newVal = !(c.enabled !== false);
    try {
      await api.patch(`/corrections/${c.id}/toggle`, { enabled: newVal });
      setCorrections(prev => prev.map(x => x.id === c.id ? { ...x, enabled: newVal } : x));
      toast.success(newVal ? 'Correction enabled' : 'Correction disabled');
    } catch { toast.error('Failed to update'); }
  }, [api]);

  // Delete
  const deleteCorrection = useCallback(async (c) => {
    try {
      await api.delete(`/corrections/${c.id}`);
      setCorrections(prev => prev.filter(x => x.id !== c.id));
      setVendors(prev => prev.map(v =>
        v.supplier_id === selectedVendor?.supplier_id
          ? { ...v, correction_count: v.correction_count - 1 }
          : v
      ));
      toast.success('Correction deleted');
    } catch { toast.error('Failed to delete'); }
  }, [api, selectedVendor]);

  // Save edit
  const saveEdit = useCallback(async () => {
    if (!editDialog) return;
    try {
      const body = {};
      if (editDialog.corrected_name !== editDialog._original.corrected_name) body.corrected_name = editDialog.corrected_name;
      const specs = {};
      if (editDialog.pack_size !== (editDialog._original.corrected_specs?.pack_size || '')) specs.pack_size = editDialog.pack_size || undefined;
      if (editDialog.unit_price !== String(editDialog._original.corrected_specs?.unit_price ?? '')) specs.unit_price = editDialog.unit_price ? parseFloat(editDialog.unit_price) : undefined;
      if (editDialog.total !== String(editDialog._original.corrected_specs?.total ?? '')) specs.total = editDialog.total ? parseFloat(editDialog.total) : undefined;
      if (Object.keys(specs).length > 0) body.corrected_specs = { ...(editDialog._original.corrected_specs || {}), ...specs };
      if (Object.keys(body).length === 0) { setEditDialog(null); return; }
      const res = await api.patch(`/corrections/${editDialog.id}`, body);
      setCorrections(prev => prev.map(x => x.id === editDialog.id ? res.data : x));
      setEditDialog(null);
      toast.success('Correction updated');
    } catch { toast.error('Failed to save'); }
  }, [api, editDialog]);

  const openEdit = (c) => {
    setEditDialog({
      id: c.id,
      corrected_name: c.corrected_name || '',
      pack_size: c.corrected_specs?.pack_size || '',
      unit_price: c.corrected_specs?.unit_price != null ? String(c.corrected_specs.unit_price) : '',
      total: c.corrected_specs?.total != null ? String(c.corrected_specs.total) : '',
      _original: c,
    });
  };

  // ── Vendor list view ──
  if (!selectedVendor) {
    return (
      <div className="max-w-4xl mx-auto" data-testid="correction-memory-page">
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-1">
            <Brain className="w-5 h-5 text-teal-600" />
            <h1 className="text-xl font-bold text-slate-900">Correction Memory</h1>
          </div>
          <p className="text-sm text-slate-500">Review and manage what the system has learned from your edits.</p>
        </div>

        {loading ? (
          <div className="text-sm text-slate-400 py-8 text-center">Loading...</div>
        ) : vendors.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-xl border border-slate-200" data-testid="no-corrections">
            <Brain className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-sm font-medium text-slate-500">No corrections stored yet</p>
            <p className="text-xs text-slate-400 mt-1">When you edit invoice items, corrections are saved here automatically.</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden" data-testid="vendor-list">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80">
                  <TableHead className="text-xs font-bold text-slate-600 uppercase tracking-wider">Vendor</TableHead>
                  <TableHead className="text-xs font-bold text-slate-600 uppercase tracking-wider text-center w-28">Corrections</TableHead>
                  <TableHead className="text-xs font-bold text-slate-600 uppercase tracking-wider text-center w-24">Active</TableHead>
                  <TableHead className="text-xs font-bold text-slate-600 uppercase tracking-wider text-center w-28">Total Used</TableHead>
                  <TableHead className="text-xs font-bold text-slate-600 uppercase tracking-wider w-36">Last Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {vendors.map((v, i) => (
                  <TableRow
                    key={v.supplier_id}
                    className="cursor-pointer hover:bg-slate-50/60 transition-colors"
                    onClick={() => selectVendor(v)}
                    data-testid={`vendor-row-${i}`}
                  >
                    <TableCell className="font-medium text-sm text-slate-800">{v.supplier_name}</TableCell>
                    <TableCell className="text-center">
                      <Badge className="bg-slate-100 text-slate-600 text-xs">{v.correction_count}</Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge className="bg-teal-50 text-teal-700 text-xs">{v.enabled_count}</Badge>
                    </TableCell>
                    <TableCell className="text-center text-xs text-slate-500">{v.total_usage}x</TableCell>
                    <TableCell className="text-xs text-slate-500">{fmtDate(v.last_updated)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    );
  }

  // ── Corrections table for selected vendor ──
  return (
    <div className="max-w-5xl mx-auto" data-testid="correction-memory-page">
      <div className="mb-5">
        <button
          className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 mb-3 transition-colors"
          onClick={() => { setSelectedVendor(null); fetchVendors(); }}
          data-testid="back-to-vendors"
        >
          <ChevronLeft className="w-3.5 h-3.5" /> All Vendors
        </button>
        <div className="flex items-center gap-3">
          <Brain className="w-5 h-5 text-teal-600" />
          <h1 className="text-xl font-bold text-slate-900">{selectedVendor.supplier_name}</h1>
          <Badge className="bg-slate-100 text-slate-600 text-xs">{corrections.length} corrections</Badge>
        </div>
        <p className="text-sm text-slate-500 mt-1">Stored corrections for this vendor. Toggle, edit, or delete as needed.</p>
      </div>

      {corrections.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-xl border border-slate-200">
          <p className="text-sm text-slate-400">No corrections for this vendor.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden" data-testid="corrections-table">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50/80">
                <TableHead className="text-[10px] font-bold text-slate-600 uppercase tracking-wider w-10">
                  <ToggleRight className="w-3.5 h-3.5" />
                </TableHead>
                <TableHead className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">Item</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">Changes</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-600 uppercase tracking-wider text-center w-20">Used</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-600 uppercase tracking-wider w-28">Last Used</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-600 uppercase tracking-wider w-28">Saved</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-600 uppercase tracking-wider text-right w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {corrections.map((c, i) => {
                const changes = describeChanges(c);
                const isEnabled = c.enabled !== false;
                return (
                  <TableRow
                    key={c.id}
                    className={`${!isEnabled ? 'opacity-50' : ''} transition-opacity`}
                    data-testid={`correction-row-${i}`}
                  >
                    <TableCell>
                      <Switch
                        checked={isEnabled}
                        onCheckedChange={() => toggleEnabled(c)}
                        className="scale-75"
                        data-testid={`toggle-correction-${i}`}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Package className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <div>
                          <p className="text-xs font-semibold text-slate-800" data-testid={`correction-key-${i}`}>{c.normalized_key}</p>
                          <p className="text-[10px] text-slate-400">{c.original_raw_name}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="space-y-0.5">
                        {changes.length === 0 ? (
                          <span className="text-[10px] text-slate-400">No changes recorded</span>
                        ) : changes.map((ch, ci) => (
                          <div key={ci} className="flex items-center gap-1.5 text-[10px]">
                            <span className="text-slate-400 font-medium w-16 flex-shrink-0">{ch.field}</span>
                            {ch.from !== '—' && <span className="text-slate-400">{ch.from}</span>}
                            {ch.from !== '—' && <ArrowRight className="w-2.5 h-2.5 text-slate-300" />}
                            <span className="font-semibold text-slate-700">{ch.to}</span>
                          </div>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      <span className="text-xs font-medium text-slate-600" data-testid={`usage-count-${i}`}>
                        {c.usage_count || 0}x
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 text-[10px] text-slate-500">
                        {c.last_used_at ? (
                          <><Clock className="w-2.5 h-2.5" /> {fmtDate(c.last_used_at)}</>
                        ) : (
                          <span className="text-slate-300">Never</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-[10px] text-slate-500">{fmtDate(c.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-slate-400 hover:text-slate-700"
                          onClick={() => openEdit(c)}
                          data-testid={`edit-correction-${i}`}
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-slate-400 hover:text-red-600"
                          onClick={() => deleteCorrection(c)}
                          data-testid={`delete-correction-${i}`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* ── Edit Dialog ── */}
      <Dialog open={!!editDialog} onOpenChange={(open) => { if (!open) setEditDialog(null); }}>
        <DialogContent className="max-w-md" data-testid="edit-correction-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">Edit Correction</DialogTitle>
          </DialogHeader>
          {editDialog && (
            <div className="space-y-3 py-2">
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Item Key</label>
                <p className="text-sm font-medium text-slate-800">{editDialog._original.normalized_key}</p>
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Corrected Name</label>
                <Input
                  value={editDialog.corrected_name}
                  onChange={e => setEditDialog(p => ({ ...p, corrected_name: e.target.value }))}
                  className="h-8 text-sm"
                  data-testid="edit-corrected-name"
                />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Pack Size</label>
                <Input
                  value={editDialog.pack_size}
                  onChange={e => setEditDialog(p => ({ ...p, pack_size: e.target.value }))}
                  className="h-8 text-sm"
                  placeholder="e.g. 2/5 LB"
                  data-testid="edit-pack-size"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Unit Price</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editDialog.unit_price}
                    onChange={e => setEditDialog(p => ({ ...p, unit_price: e.target.value }))}
                    className="h-8 text-sm"
                    data-testid="edit-unit-price"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Total</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editDialog.total}
                    onChange={e => setEditDialog(p => ({ ...p, total: e.target.value }))}
                    className="h-8 text-sm"
                    data-testid="edit-total"
                  />
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" className="h-8 text-xs" onClick={() => setEditDialog(null)}>Cancel</Button>
            <Button className="h-8 text-xs bg-teal-600 hover:bg-teal-700" onClick={saveEdit} data-testid="save-edit-btn">Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
