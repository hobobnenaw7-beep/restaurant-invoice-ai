import { TrendingUp, TrendingDown, Minus, BarChart3, ShieldCheck, AlertTriangle, Activity } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export default function ProfitIntelligence({ data }) {
  if (!data) return null;

  return (
    <div className="space-y-4" data-testid="profit-intelligence">
      {/* Cost Drivers */}
      <Card className="border-slate-700/50 bg-slate-900/50">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-amber-400" />
            Top Cost Drivers
            <span className="text-xs text-slate-500 font-normal ml-auto">% of total ${data.total_spend?.toLocaleString()}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5">
          {(data.cost_drivers || []).slice(0, 5).map((d, i) => (
            <div key={i} className="flex items-center gap-3" data-testid={`cost-driver-${i}`}>
              <span className="text-xs text-slate-500 w-4 text-right">{i + 1}.</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-slate-300 truncate">{d.product}</span>
                  {d.pct_of_spend > 30 && <Badge variant="outline" className="text-[10px] border-red-500/30 text-red-400 px-1">High</Badge>}
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full mt-1 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${d.pct_of_spend > 30 ? 'bg-red-500/70' : d.pct_of_spend > 15 ? 'bg-amber-500/70' : 'bg-emerald-500/60'}`}
                    style={{ width: `${Math.min(d.pct_of_spend, 100)}%` }}
                  />
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <div className="text-sm text-slate-200 font-medium">${d.total_spent?.toLocaleString()}</div>
                <div className="text-xs text-slate-500">{d.pct_of_spend}%</div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4">
        {/* Price Trends */}
        <Card className="border-slate-700/50 bg-slate-900/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              Price Trends (30d)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(data.price_trends || []).slice(0, 6).map((t, i) => (
              <div key={i} className="flex items-center justify-between text-xs" data-testid={`price-trend-${i}`}>
                <span className="text-slate-400 truncate flex-1 mr-2">{t.product?.substring(0, 28)}</span>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className="text-slate-300">${t.current_price}</span>
                  <TrendBadge pct={t.trend_30d_pct} />
                </div>
              </div>
            ))}
            {(!data.price_trends || data.price_trends.length === 0) && (
              <div className="text-xs text-slate-600 text-center py-4">Need ≥2 data points for trends</div>
            )}
          </CardContent>
        </Card>

        {/* Vendor Stability */}
        <Card className="border-slate-700/50 bg-slate-900/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Vendor Stability
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(data.vendor_stability || []).map((v, i) => (
              <div key={i} data-testid={`vendor-stability-${i}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-300">{v.vendor}</span>
                  <StabilityLabel label={v.stability_label} cv={v.avg_cv_pct} />
                </div>
                <div className="text-xs text-slate-500">{v.products_analyzed} products analyzed</div>
                {v.stability_label === 'Volatile' && v.product_details?.slice(0, 2).map((pd, j) => (
                  <div key={j} className="text-xs text-red-400/70 mt-0.5 pl-2">
                    {pd.product_key?.substring(0, 25)}: CV {pd.cv_pct}%
                  </div>
                ))}
              </div>
            ))}
            {(!data.vendor_stability || data.vendor_stability.length === 0) && (
              <div className="text-xs text-slate-600 text-center py-4">Need ≥3 data points per product</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function TrendBadge({ pct }) {
  if (pct === null || pct === undefined) return <span className="text-slate-600 text-xs">—</span>;
  if (pct > 1) return (
    <span className="flex items-center gap-0.5 text-red-400 font-medium">
      <TrendingUp className="w-3 h-3" />+{pct}%
    </span>
  );
  if (pct < -1) return (
    <span className="flex items-center gap-0.5 text-emerald-400 font-medium">
      <TrendingDown className="w-3 h-3" />{pct}%
    </span>
  );
  return (
    <span className="flex items-center gap-0.5 text-slate-500">
      <Minus className="w-3 h-3" />0%
    </span>
  );
}

function StabilityLabel({ label, cv }) {
  const config = {
    Stable: { color: 'text-emerald-400', icon: <ShieldCheck className="w-3 h-3" /> },
    Moderate: { color: 'text-amber-400', icon: <AlertTriangle className="w-3 h-3" /> },
    Volatile: { color: 'text-red-400', icon: <AlertTriangle className="w-3 h-3" /> },
  };
  const c = config[label] || config.Stable;
  return (
    <span className={`flex items-center gap-1 text-xs font-medium ${c.color}`}>
      {c.icon} {label} ({cv}%)
    </span>
  );
}
