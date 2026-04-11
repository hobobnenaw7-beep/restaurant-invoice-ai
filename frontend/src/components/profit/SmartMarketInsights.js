import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, DollarSign, AlertTriangle, ArrowRight, Loader2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

export default function SmartMarketInsights({ api }) {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await api.get('/profit/intelligence');
      setInsights(buildInsights(res.data));
    } catch (e) {
      console.error('Market insights error:', e);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  if (loading) return null;
  if (!insights || insights.length === 0) return null;

  return (
    <div className="mt-6" data-testid="smart-market-insights">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-1 h-4 bg-teal-500 rounded-full" />
        <h2 className="text-sm font-semibold text-slate-700">Smart Market Insights</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {insights.map((item, i) => (
          <Card key={i} className="border-slate-200 bg-white shadow-sm" data-testid={`market-insight-${i}`}>
            <CardContent className="p-3">
              <div className="flex items-start gap-2.5">
                <div className={`mt-0.5 p-1.5 rounded-md ${item.iconBg}`}>
                  {item.icon}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-800 font-medium leading-snug">{item.headline}</div>
                  <div className="text-xs text-teal-600 mt-1 flex items-center gap-1">
                    <ArrowRight className="w-3 h-3 flex-shrink-0" />
                    {item.action}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function buildInsights(data) {
  if (!data || data.data_points === 0) return [];

  const items = [];
  const trends = data.price_trends || [];
  const drivers = data.cost_drivers || [];
  const stability = data.vendor_stability || [];

  // 1. Price Alerts — significant increases
  for (const t of trends) {
    if (items.length >= 5) break;
    const pct = t.trend_30d_pct;
    if (pct && pct > 8) {
      const shortName = t.product.replace(/^(SYS|CLS|CHS|REL|CAJ)\s+/gi, '').substring(0, 25);
      items.push({
        headline: `${shortName} price +${pct}%`,
        action: t.vendors?.length > 1 ? 'Compare vendors for better rate' : 'Monitor or negotiate pricing',
        icon: <TrendingUp className="w-3.5 h-3.5 text-red-500" />,
        iconBg: 'bg-red-50',
      });
    }
  }

  // 2. Savings Opportunities — high-spend concentration
  for (const d of drivers) {
    if (items.length >= 5) break;
    if (d.pct_of_spend > 25) {
      const saving = Math.round(d.total_spent * 0.05);
      const shortName = d.product.replace(/^(SYS|CLS|CHS|REL|CAJ)\s+/gi, '').substring(0, 25);
      items.push({
        headline: `Save ~$${saving} on ${shortName}`,
        action: 'Review portions or negotiate volume discount',
        icon: <DollarSign className="w-3.5 h-3.5 text-emerald-500" />,
        iconBg: 'bg-emerald-50',
      });
    }
  }

  // 3. Risk Alerts — fees, volatile vendors, concentration
  // Track product names used in price alerts to avoid duplicates
  const usedProducts = new Set();
  for (const t of trends) {
    const pct = t.trend_30d_pct;
    if (pct && pct > 8) {
      usedProducts.add(t.product.toUpperCase().substring(0, 20));
    }
  }

  for (const t of trends) {
    if (items.length >= 5) break;
    const name = t.product.toUpperCase();
    const isFee = name.includes('FUEL') || name.includes('SURCHARGE') || name.includes('FEE');
    if (isFee && t.trend_30d_pct && t.trend_30d_pct > 5) {
      if (usedProducts.has(t.product.toUpperCase().substring(0, 20))) continue;
      const headline = `${t.product.substring(0, 25)} up ${t.trend_30d_pct}%`;
      items.push({
        headline,
        action: 'Negotiate fee caps or consolidate deliveries',
        icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />,
        iconBg: 'bg-amber-50',
      });
    }
  }

  for (const v of stability) {
    if (items.length >= 5) break;
    if (v.stability_label === 'Volatile') {
      items.push({
        headline: `${v.vendor} — Unstable pricing`,
        action: 'Consider backup vendor or lock contract',
        icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />,
        iconBg: 'bg-amber-50',
      });
    }
  }

  return items.slice(0, 5);
}
