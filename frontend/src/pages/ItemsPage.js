import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { Search, Plus, Edit, Trash2, Loader2, Tag, X, Package } from 'lucide-react';

export default function ItemsPage() {
  const { api } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [aliasDialog, setAliasDialog] = useState(null);
  const [form, setForm] = useState({ name: '', category: '' });
  const [aliasName, setAliasName] = useState('');
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const res = await api.get('/items', { params: { search } }); setItems(res.data); }
    catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [search]); // eslint-disable-line

  const openNew = () => { setEditing(null); setForm({ name: '', category: '' }); setDialogOpen(true); };
  const openEdit = (item) => { setEditing(item); setForm({ name: item.name, category: item.category || '' }); setDialogOpen(true); };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editing) await api.put(`/items/${editing.id}`, form);
      else await api.post('/items', form);
      toast.success(editing ? 'Updated' : 'Created');
      setDialogOpen(false); load();
    } catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete item and all aliases?')) return;
    try { await api.delete(`/items/${id}`); toast.success('Deleted'); load(); } catch { toast.error('Failed'); }
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

  // Keep alias dialog synced with latest item data
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

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input className="pl-9 h-10" placeholder="Search items..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="search-items" />
      </div>

      {loading ? (
        <Card className="border border-slate-100 shadow-sm overflow-hidden"><div className="p-6 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}</div></Card>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4"><Package className="w-6 h-6 text-slate-300" /></div>
          <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No items yet</h3>
          <p className="text-sm text-slate-400">Add items to start normalizing invoice data.</p>
        </div>
      ) : (
        <Card className="border border-slate-100 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Item Name</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Category</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Aliases</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right w-40">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, i) => (
                  <TableRow key={item.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`} data-testid={`item-row-${item.id}`}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-navy-900 text-white flex items-center justify-center text-[11px] font-bold flex-shrink-0">{item.name?.charAt(0)}</div>
                        <span className="text-sm font-semibold text-navy-900">{item.name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {item.category ? <Badge variant="outline" className="text-[10px] font-semibold">{item.category}</Badge> : <span className="text-xs text-slate-300">—</span>}
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
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-[10px] text-slate-500 hover:text-teal-700" onClick={() => { setAliasDialog(item); setAliasName(''); }} data-testid={`manage-aliases-${item.id}`}>
                          <Tag className="w-3 h-3 mr-1" /> Aliases
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEdit(item)} data-testid={`edit-item-${item.id}`}><Edit className="w-3.5 h-3.5 text-slate-500" /></Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleDelete(item.id)} data-testid={`delete-item-${item.id}`}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-heading text-lg">{editing ? 'Edit Item' : 'New Item'}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Item Name</Label><Input className="mt-1.5 h-10" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="input-item-name" /></div>
            <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Category</Label><Input className="mt-1.5 h-10" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="e.g. Meat, Dairy, Vegetables" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving || !form.name} className="bg-teal-600 hover:bg-teal-700 text-white" data-testid="save-item-btn">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null} Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
    </div>
  );
}
