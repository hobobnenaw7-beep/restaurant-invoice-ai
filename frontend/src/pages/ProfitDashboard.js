import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Search, TrendingUp, TrendingDown, Minus, DollarSign, AlertTriangle, CheckCircle2, ShieldCheck, BarChart3, Zap, ArrowRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import DecisionSearch from '@/components/profit/DecisionSearch';
import ProfitIntelligence from '@/components/profit/ProfitIntelligence';
import ReviewQueue from '@/components/profit/ReviewQueue';
import AISidebar from '@/components/profit/AISidebar';

export default function ProfitDashboard() {
  const { api } = useAuth();
  const [intelligence, setIntelligence] = useState(null);
  const [reviewCount, setReviewCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [intRes, revRes] = await Promise.all([
        api.get('/profit/intelligence'),
        api.get('/profit/review-queue'),
      ]);
      setIntelligence(intRes.data);
      setReviewCount(revRes.data.total_count);
    } catch (e) {
      console.error('Dashboard load error:', e);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleConfirm = useCallback(() => {
    setReviewCount(prev => Math.max(0, prev - 1));
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[70vh]" data-testid="profit-dashboard-loading">
        <div className="animate-spin w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  const totalSpend = intelligence?.total_spend || 0;
  const dataPoints = intelligence?.data_points || 0;
  const topDriver = intelligence?.cost_drivers?.[0];
  const topTrend = intelligence?.price_trends?.[0];

  return (
    <div className="flex gap-0 h-[calc(100vh-64px)]" data-testid="profit-dashboard">
      {/* ── Main Panel (Left/Center) ── */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 min-w-0">
        {/* KPI Strip */}
        <div className="grid grid-cols-4 gap-4" data-testid="kpi-strip">
          <KPICard
            label="Total Spend"
            value={`$${totalSpend.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}`}
            sub={`${dataPoints} verified items`}
            icon={<DollarSign className="w-4 h-4" />}
            color="emerald"
          />
          <KPICard
            label="Top Cost Driver"
            value={topDriver?.product?.substring(0, 20) || 'N/A'}
            sub={topDriver ? `${topDriver.pct_of_spend}% of spend` : ''}
            icon={<BarChart3 className="w-4 h-4" />}
            color="amber"
            severity={topDriver?.pct_of_spend > 30 ? 'high' : 'normal'}
          />
          <KPICard
            label="Biggest Price Move"
            value={topTrend ? `${topTrend.trend_30d_pct > 0 ? '+' : ''}${topTrend.trend_30d_pct || 0}%` : 'N/A'}
            sub={topTrend?.product?.substring(0, 22) || ''}
            icon={topTrend?.trend_30d_pct > 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            color={topTrend?.trend_30d_pct > 0 ? 'red' : 'emerald'}
          />
          <KPICard
            label="Review Queue"
            value={reviewCount}
            sub={reviewCount > 0 ? 'Items need attention' : 'All clear'}
            icon={reviewCount > 0 ? <AlertTriangle className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
            color={reviewCount > 0 ? 'orange' : 'emerald'}
          />
        </div>

        {/* Smart Insights Banner */}
        <SmartInsights intelligence={intelligence} />

        {/* Decision Engine Search */}
        <DecisionSearch api={api} />

        {/* Profit Intelligence */}
        <ProfitIntelligence data={intelligence} />

        {/* Review Queue */}
        <ReviewQueue api={api} onConfirm={handleConfirm} />
      </div>

      {/* ── AI Sidebar (Right — Permanent) ── */}
      <AISidebar api={api} intelligence={intelligence} />
    </div>
  );
}

function KPICard({ label, value, sub, icon, color = 'emerald', severity }) {
  const colorMap = {
    emerald: 'border-emerald-500/30 bg-emerald-950/20',
    amber: 'border-amber-500/30 bg-amber-950/20',
    red: 'border-red-500/30 bg-red-950/20',
    orange: 'border-orange-500/30 bg-orange-950/20',
  };
  const iconColorMap = {
    emerald: 'text-emerald-400',
    amber: 'text-amber-400',
    red: 'text-red-400',
    orange: 'text-orange-400',
  };

  return (
    <Card className={`border ${colorMap[color]} backdrop-blur-sm`} data-testid={`kpi-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-400 uppercase tracking-wider font-medium">{label}</span>
          <span className={iconColorMap[color]}>{icon}</span>
        </div>
        <div className={`text-xl font-bold ${severity === 'high' ? 'text-amber-300' : 'text-slate-100'}`}>
          {value}
        </div>
        {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function SmartInsights({ intelligence }) {
  const trends = intelligence?.price_trends || [];
  const drivers = intelligence?.cost_drivers || [];

  const alerts = [];

  // Price increases
  trends.forEach(t => {
    if (t.trend_30d_pct && t.trend_30d_pct > 5) {
      alerts.push({
        type: 'price_up',
        severity: t.trend_30d_pct > 15 ? 'high' : 'medium',
        message: `${t.product.substring(0, 30)} price up ${t.trend_30d_pct}% (30d)`,
        detail: `$${t.avg_price} → $${t.current_price}`,
      });
    }
  });

  // Spend concentration
  drivers.forEach(d => {
    if (d.pct_of_spend > 25) {
      alerts.push({
        type: 'concentration',
        severity: d.pct_of_spend > 40 ? 'high' : 'medium',
        message: `${d.product.substring(0, 30)} is ${d.pct_of_spend}% of total spend`,
        detail: `$${d.total_spent.toLocaleString()} across ${d.total_qty} units`,
      });
    }
  });

  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2" data-testid="smart-insights">
      <div className="flex items-center gap-2 mb-1">
        <Zap className="w-4 h-4 text-amber-400" />
        <span className="text-sm font-semibold text-slate-300">Action Required</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {alerts.slice(0, 4).map((a, i) => (
          <div
            key={i}
            className={`flex items-start gap-3 p-3 rounded-lg border ${
              a.severity === 'high'
                ? 'border-red-500/30 bg-red-950/10'
                : 'border-amber-500/20 bg-amber-950/10'
            }`}
            data-testid={`insight-${i}`}
          >
            {a.type === 'price_up' ? (
              <TrendingUp className={`w-4 h-4 mt-0.5 flex-shrink-0 ${a.severity === 'high' ? 'text-red-400' : 'text-amber-400'}`} />
            ) : (
              <AlertTriangle className={`w-4 h-4 mt-0.5 flex-shrink-0 ${a.severity === 'high' ? 'text-red-400' : 'text-amber-400'}`} />
            )}
            <div className="min-w-0">
              <div className="text-sm text-slate-200 font-medium">{a.message}</div>
              <div className="text-xs text-slate-500 mt-0.5">{a.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
