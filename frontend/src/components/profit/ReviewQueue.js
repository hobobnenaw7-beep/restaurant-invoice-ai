import { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, AlertTriangle, HelpCircle, Loader2, Check } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';

export default function ReviewQueue({ api, onConfirm }) {
  const [items, setItems] = useState([]);
  const [breakdown, setBreakdown] = useState({});
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(null);

  const loadQueue = useCallback(async () => {
    try {
      const res = await api.get('/profit/review-queue');
      setItems(res.data.items || []);
      setBreakdown(res.data.reason_breakdown || {});
    } catch (e) {
      console.error('Review queue error:', e);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { loadQueue(); }, [loadQueue]);

  const handleConfirm = useCallback(async (item, overrideQty) => {
    setConfirming(item.id);
    try {
      const body = { item_id: item.id };
      if (overrideQty !== undefined && overrideQty !== null) {
        body.confirmed_quantity = parseFloat(overrideQty);
      }
      await api.post('/profit/confirm-item', body);
      setItems(prev => prev.filter(i => i.id !== item.id));
      toast.success(`Confirmed: ${item.raw_name.substring(0, 30)}`);
      onConfirm?.();
    } catch (e) {
      toast.error('Failed to confirm item');
    } finally {
      setConfirming(null);
    }
  }, [api, onConfirm]);

  return (
    <Card className="border-slate-700/50 bg-slate-900/50" data-testid="review-queue">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-orange-400" />
            Review Queue
            {items.length > 0 && (
              <Badge variant="outline" className="text-[10px] border-orange-500/30 text-orange-400 ml-1">
                {items.length}
              </Badge>
            )}
          </CardTitle>
          <div className="flex gap-1.5">
            {Object.entries(breakdown).map(([reason, count]) => (
              <Badge key={reason} variant="outline" className="text-[10px] text-slate-400 border-slate-600/50">
                {reason}: {count}
              </Badge>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-slate-500" /></div>
        ) : items.length === 0 ? (
          <div className="text-center py-8" data-testid="review-queue-empty">
            <CheckCircle2 className="w-8 h-8 text-emerald-500/40 mx-auto mb-2" />
            <div className="text-sm text-slate-500">All items reviewed</div>
            <div className="text-xs text-slate-600 mt-1">New items appear after invoice extraction</div>
          </div>
        ) : (
          <div className="space-y-1">
            {/* Header */}
            <div className="grid grid-cols-[1fr_80px_80px_80px_140px_100px] gap-2 px-3 py-1.5 text-[10px] text-slate-500 uppercase tracking-wider font-medium border-b border-slate-700/30">
              <span>Product</span>
              <span className="text-right">Qty</span>
              <span className="text-right">Price</span>
              <span className="text-right">Total</span>
              <span>Reason</span>
              <span className="text-right">Action</span>
            </div>
            {items.map(item => (
              <ReviewRow
                key={item.id}
                item={item}
                confirming={confirming === item.id}
                onConfirm={handleConfirm}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReviewRow({ item, confirming, onConfirm }) {
  const [editQty, setEditQty] = useState('');
  const [showEdit, setShowEdit] = useState(false);

  const reasonColors = {
    'Qty Ambiguous': 'border-amber-500/30 text-amber-400',
    'Price Mismatch': 'border-red-500/30 text-red-400',
    'Memory Supported (Qty=1)': 'border-cyan-500/30 text-cyan-400',
    'Qty Missing': 'border-orange-500/30 text-orange-400',
    'Price Missing': 'border-orange-500/30 text-orange-400',
    'Qty & Price Missing': 'border-red-500/30 text-red-400',
    'Review Required': 'border-slate-500/30 text-slate-400',
  };

  const reasonStyle = reasonColors[item.reason_label] || reasonColors['Review Required'];

  return (
    <div
      className="grid grid-cols-[1fr_80px_80px_80px_140px_100px] gap-2 items-center px-3 py-2 rounded hover:bg-slate-800/40 transition-colors group"
      data-testid={`review-item-${item.id}`}
    >
      <div className="min-w-0">
        <div className="text-sm text-slate-300 truncate">{item.raw_name}</div>
        {item.item_code && <div className="text-[10px] text-slate-600">{item.item_code}</div>}
      </div>
      <div className="text-right">
        {showEdit ? (
          <Input
            value={editQty}
            onChange={e => setEditQty(e.target.value)}
            className="h-6 text-xs w-16 bg-slate-800 border-slate-600 text-right ml-auto"
            placeholder={String(item.quantity)}
            autoFocus
            data-testid="qty-edit-input"
          />
        ) : (
          <span className="text-sm text-slate-300 cursor-pointer hover:text-emerald-400" onClick={() => setShowEdit(true)}>
            {item.quantity}
          </span>
        )}
      </div>
      <span className="text-sm text-slate-300 text-right">${item.unit_price}</span>
      <span className="text-sm text-slate-300 text-right">${item.total}</span>
      <Badge variant="outline" className={`text-[10px] px-1.5 w-fit ${reasonStyle}`}>
        {item.reason_label}
      </Badge>
      <div className="text-right">
        <Button
          size="sm"
          disabled={confirming}
          onClick={() => onConfirm(item, showEdit && editQty ? editQty : undefined)}
          className="h-7 text-xs bg-emerald-600 hover:bg-emerald-500 text-white px-3"
          data-testid="confirm-button"
        >
          {confirming ? <Loader2 className="w-3 h-3 animate-spin" /> : <><Check className="w-3 h-3 mr-1" />Confirm</>}
        </Button>
      </div>
    </div>
  );
}
