import { useState, useEffect, useCallback } from 'react';
import { Bot, RefreshCw, Loader2, Zap, TrendingUp, AlertTriangle, DollarSign } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import ReactMarkdown from 'react-markdown';

export default function AISidebar({ api, intelligence }) {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [autoInsights, setAutoInsights] = useState([]);

  const fetchInsights = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.post('/profit/ai-insights', {
        dashboard_context: {
          total_spend: intelligence?.total_spend,
          top_driver: intelligence?.cost_drivers?.[0]?.product,
          review_pending: intelligence?.data_points,
        },
      });
      setInsights(res.data);
      setAutoInsights(res.data.auto_insights || []);
    } catch (e) {
      console.error('AI insights error:', e);
    } finally {
      setLoading(false);
    }
  }, [api, intelligence]);

  useEffect(() => {
    if (intelligence) fetchInsights();
  }, [intelligence]); // eslint-disable-line react-hooks/exhaustive-deps

  const insightIcons = {
    price_increase: <TrendingUp className="w-3.5 h-3.5 text-red-400" />,
    price_decrease: <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />,
    spend_concentration: <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />,
  };

  return (
    <div className="w-80 border-l border-slate-700/50 bg-slate-950/60 flex flex-col h-full overflow-hidden flex-shrink-0" data-testid="ai-sidebar">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">Profit Advisor</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchInsights}
          disabled={loading}
          className="h-7 w-7 p-0 text-slate-400 hover:text-emerald-400"
          data-testid="refresh-insights"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Key Metrics */}
        {insights?.computed_metrics && (
          <div className="grid grid-cols-2 gap-2" data-testid="sidebar-metrics">
            <MetricPill label="Spend" value={`$${(insights.computed_metrics.total_spend || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}`} icon={<DollarSign className="w-3 h-3" />} />
            <MetricPill label="Items" value={insights.computed_metrics.total_items} icon={<Zap className="w-3 h-3" />} />
          </div>
        )}

        {/* Deterministic Auto-Insights */}
        {autoInsights.length > 0 && (
          <div data-testid="auto-insights">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium mb-2">Detected Issues</div>
            <div className="space-y-2">
              {autoInsights.map((ins, i) => (
                <div
                  key={i}
                  className={`p-2.5 rounded-lg border text-xs ${
                    ins.severity === 'high'
                      ? 'border-red-500/20 bg-red-950/10'
                      : ins.severity === 'medium'
                      ? 'border-amber-500/20 bg-amber-950/10'
                      : 'border-slate-700/30 bg-slate-800/20'
                  }`}
                  data-testid={`auto-insight-${i}`}
                >
                  <div className="flex items-start gap-2">
                    {insightIcons[ins.type] || <Zap className="w-3.5 h-3.5 text-slate-400" />}
                    <div>
                      <div className="text-slate-300">{ins.message}</div>
                      {ins.type === 'price_increase' && (
                        <div className="text-slate-500 mt-0.5">${ins.old_price} → ${ins.new_price}</div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* AI Explanation */}
        {insights?.ai_explanation && (
          <div data-testid="ai-explanation">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium mb-2 flex items-center gap-1.5">
              <Bot className="w-3 h-3 text-emerald-400" />
              AI Analysis
            </div>
            <div className="text-xs text-slate-400 leading-relaxed prose prose-invert prose-xs max-w-none [&_strong]:text-slate-200 [&_p]:mb-2">
              <ReactMarkdown>{insights.ai_explanation}</ReactMarkdown>
            </div>
            <div className="mt-2 text-[10px] text-slate-600 italic">
              Based on {insights.computed_metrics?.total_items || 0} verified items. AI explains only — all numbers are precomputed.
            </div>
          </div>
        )}

        {!insights?.ai_explanation && !loading && insights && (
          <div className="text-xs text-slate-600 text-center py-4" data-testid="ai-unavailable">
            AI analysis unavailable. Deterministic insights above are fully functional.
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-8 gap-2">
            <Loader2 className="w-5 h-5 animate-spin text-emerald-500/50" />
            <span className="text-xs text-slate-500">Analyzing...</span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-slate-700/30 text-[10px] text-slate-600">
        Data: Trusted + User-Confirmed only
      </div>
    </div>
  );
}

function MetricPill({ label, value, icon }) {
  return (
    <div className="flex items-center gap-1.5 bg-slate-800/40 rounded-md px-2 py-1.5 border border-slate-700/30">
      <span className="text-slate-500">{icon}</span>
      <div>
        <div className="text-[10px] text-slate-500">{label}</div>
        <div className="text-xs text-slate-200 font-medium">{value}</div>
      </div>
    </div>
  );
}
