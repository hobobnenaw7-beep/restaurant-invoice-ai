import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  Shield, Search, ChevronLeft, ChevronRight, Clock,
  Plus, Pencil, Trash2, CheckCircle2, XCircle, LogIn,
  UserCog, Filter, X, Eye
} from 'lucide-react';

const ACTION_ICONS = {
  CREATE: { icon: Plus, color: 'text-teal-600', bg: 'bg-teal-50', label: 'Created' },
  UPDATE: { icon: Pencil, color: 'text-amber-600', bg: 'bg-amber-50', label: 'Updated' },
  DELETE: { icon: Trash2, color: 'text-red-600', bg: 'bg-red-50', label: 'Deleted' },
  APPROVE: { icon: CheckCircle2, color: 'text-emerald-600', bg: 'bg-emerald-50', label: 'Approved' },
  REJECT: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50', label: 'Rejected' },
  LOGIN: { icon: LogIn, color: 'text-indigo-600', bg: 'bg-indigo-50', label: 'Login' },
  ROLE_CHANGE: { icon: UserCog, color: 'text-purple-600', bg: 'bg-purple-50', label: 'Role Change' },
};

const ACTION_TYPES = ['CREATE', 'UPDATE', 'DELETE', 'APPROVE', 'REJECT', 'LOGIN', 'ROLE_CHANGE'];
const ENTITY_TYPES = ['Expense', 'Sale', 'Vendor', 'Item', 'User'];

function formatTs(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true });
  } catch { return ts.slice(0, 16); }
}

function formatDate(ts) {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch { return ts.slice(0, 10); }
}

function ValueDiff({ label, old_val, new_val }) {
  if (old_val === new_val || old_val === undefined) return null;
  const fmt = (v) => {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'object') return JSON.stringify(v).slice(0, 50);
    return String(v);
  };
  return (
    <div className="text-[11px]">
      <span className="text-slate-400">{label}: </span>
      <span className="text-red-500 line-through">{fmt(old_val)}</span>
      <span className="text-slate-300 mx-1">&rarr;</span>
      <span className="text-teal-700 font-semibold">{fmt(new_val)}</span>
    </div>
  );
}

export default function AuditLogPage() {
  const { api } = useAuth();
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState([]);
  const [expandedId, setExpandedId] = useState(null);

  // Filters
  const [actionType, setActionType] = useState('');
  const [entityType, setEntityType] = useState('');
  const [userId, setUserId] = useState('');
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);

  const load = useCallback(async (pg) => {
    setLoading(true);
    try {
      const params = { page: pg || page, page_size: 25 };
      if (actionType) params.action_type = actionType;
      if (entityType) params.entity_type = entityType;
      if (userId) params.user_id = userId;
      if (search) params.search = search;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await api.get('/audit-logs', { params });
      setLogs(res.data.logs || []);
      setTotal(res.data.total || 0);
      setPage(res.data.page || 1);
      setTotalPages(res.data.total_pages || 1);
      if (res.data.users) setUsers(res.data.users);
    } catch (e) {
      if (e?.response?.status === 403) {
        toast.error('Manager access required');
      } else {
        toast.error('Failed to load audit logs');
      }
    } finally {
      setLoading(false);
    }
  }, [api, page, actionType, entityType, userId, search, dateFrom, dateTo]);

  useEffect(() => { load(1); }, [actionType, entityType, userId, search, dateFrom, dateTo]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = useCallback((e) => {
    e?.preventDefault();
    setSearch(searchInput);
  }, [searchInput]);

  const clearFilters = useCallback(() => {
    setActionType(''); setEntityType(''); setUserId('');
    setSearch(''); setSearchInput('');
    setDateFrom(''); setDateTo('');
  }, []);

  const hasFilters = actionType || entityType || userId || search || dateFrom || dateTo;

  const goPage = useCallback((p) => {
    setPage(p);
    load(p);
  }, [load]);

  return (
    <div className="space-y-5 max-w-[1100px]" data-testid="audit-log-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Audit Log</h1>
          <p className="text-sm text-slate-400 mt-1">Track all actions across the system</p>
        </div>
        <Badge variant="secondary" className="text-xs" data-testid="audit-total-badge">
          {total} record{total !== 1 ? 's' : ''}
        </Badge>
      </div>

      {/* Search + Filter Toggle */}
      <div className="flex items-center gap-3">
        <form onSubmit={handleSearch} className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search logs... (vendor name, item, description)"
            className="pl-9 pr-9 h-10 text-sm border-slate-200"
            data-testid="audit-search-input"
          />
          {searchInput && (
            <button type="button" onClick={() => { setSearchInput(''); setSearch(''); }} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
              <X className="w-4 h-4" />
            </button>
          )}
        </form>
        <Button
          variant={filtersOpen ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFiltersOpen(p => !p)}
          className="h-10 px-4"
          data-testid="audit-filter-toggle"
        >
          <Filter className="w-4 h-4 mr-1.5" />
          Filters
          {hasFilters && <Badge className="ml-1.5 bg-teal-600 text-white text-[8px] h-4 px-1">ON</Badge>}
        </Button>
      </div>

      {/* Filter Panel */}
      {filtersOpen && (
        <Card className="border border-slate-100" data-testid="audit-filter-panel">
          <CardContent className="py-4 px-5">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase mb-1 block">Action</label>
                <Select value={actionType} onValueChange={(v) => setActionType(v === 'all' ? '' : v)}>
                  <SelectTrigger className="h-9 text-xs" data-testid="audit-filter-action">
                    <SelectValue placeholder="All Actions" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Actions</SelectItem>
                    {ACTION_TYPES.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase mb-1 block">Entity</label>
                <Select value={entityType} onValueChange={(v) => setEntityType(v === 'all' ? '' : v)}>
                  <SelectTrigger className="h-9 text-xs" data-testid="audit-filter-entity">
                    <SelectValue placeholder="All Entities" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Entities</SelectItem>
                    {ENTITY_TYPES.map(e => <SelectItem key={e} value={e}>{e}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase mb-1 block">User</label>
                <Select value={userId} onValueChange={(v) => setUserId(v === 'all' ? '' : v)}>
                  <SelectTrigger className="h-9 text-xs" data-testid="audit-filter-user">
                    <SelectValue placeholder="All Users" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Users</SelectItem>
                    {users.map(u => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase mb-1 block">From</label>
                <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="h-9 text-xs" data-testid="audit-filter-from" />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase mb-1 block">To</label>
                <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="h-9 text-xs" data-testid="audit-filter-to" />
              </div>
            </div>
            {hasFilters && (
              <button onClick={clearFilters} className="mt-3 text-xs text-teal-600 hover:text-teal-700 font-semibold" data-testid="audit-clear-filters">
                Clear all filters
              </button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Log Table */}
      <Card className="border border-slate-100 shadow-sm overflow-hidden" data-testid="audit-log-table">
        {loading ? (
          <CardContent className="py-6 space-y-3">
            {[1,2,3,4,5].map(i => <Skeleton key={i} className="h-14 rounded-lg" />)}
          </CardContent>
        ) : logs.length === 0 ? (
          <CardContent className="py-16 text-center">
            <Shield className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-sm text-slate-400">{hasFilters ? 'No logs match your filters' : 'No audit logs yet'}</p>
          </CardContent>
        ) : (
          <div className="divide-y divide-slate-100" data-testid="audit-log-list">
            {logs.map((log) => {
              const actionInfo = ACTION_ICONS[log.action_type] || ACTION_ICONS.CREATE;
              const ActionIcon = actionInfo.icon;
              const isExpanded = expandedId === log.id;
              const hasDetails = log.old_value || log.new_value;

              return (
                <div key={log.id} data-testid={`audit-row-${log.id}`}>
                  <div
                    className={`flex items-center gap-4 px-5 py-3.5 hover:bg-slate-50/60 transition-colors ${hasDetails ? 'cursor-pointer' : ''}`}
                    onClick={() => hasDetails && setExpandedId(isExpanded ? null : log.id)}
                  >
                    <div className={`w-8 h-8 rounded-lg ${actionInfo.bg} flex items-center justify-center flex-shrink-0`}>
                      <ActionIcon className={`w-4 h-4 ${actionInfo.color}`} />
                    </div>

                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-navy-900">{log.description}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[11px] text-slate-400">{formatTs(log.timestamp)}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Badge variant="outline" className="text-[9px] h-5 px-1.5 font-semibold border-slate-200">
                        {log.entity_type}
                      </Badge>
                      <Badge className={`text-[9px] h-5 px-1.5 font-bold ${actionInfo.bg} ${actionInfo.color} border-0`}>
                        {actionInfo.label}
                      </Badge>
                    </div>

                    <div className="w-16 text-right flex-shrink-0">
                      <span className="text-[11px] text-slate-400">{log.user_name}</span>
                      <Badge variant="secondary" className="text-[8px] h-4 px-1 ml-1">{log.user_role}</Badge>
                    </div>

                    {hasDetails && (
                      <Eye className={`w-3.5 h-3.5 text-slate-300 flex-shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                    )}
                  </div>

                  {isExpanded && hasDetails && (
                    <div className="px-5 pb-3 pt-0 ml-12" data-testid={`audit-detail-${log.id}`}>
                      <div className="bg-slate-50 rounded-lg p-3 space-y-1">
                        {log.old_value && log.new_value && Object.keys(log.new_value).map(k => (
                          <ValueDiff key={k} label={k} old_val={log.old_value?.[k]} new_val={log.new_value?.[k]} />
                        ))}
                        {log.new_value && !log.old_value && (
                          <div className="text-[11px] text-slate-500">
                            {Object.entries(log.new_value).map(([k, v]) => (
                              <span key={k} className="mr-3"><span className="text-slate-400">{k}:</span> <span className="font-semibold text-teal-700">{typeof v === 'object' ? JSON.stringify(v).slice(0, 40) : String(v)}</span></span>
                            ))}
                          </div>
                        )}
                        {log.old_value && !log.new_value && (
                          <div className="text-[11px] text-slate-500">
                            {Object.entries(log.old_value).map(([k, v]) => (
                              <span key={k} className="mr-3"><span className="text-slate-400">{k}:</span> <span className="font-semibold text-red-500 line-through">{typeof v === 'object' ? JSON.stringify(v).slice(0, 40) : String(v)}</span></span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between" data-testid="audit-pagination">
          <span className="text-xs text-slate-400">
            Page {page} of {totalPages} ({total} total)
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              disabled={page <= 1}
              onClick={() => goPage(page - 1)}
              data-testid="audit-prev-page"
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              const start = Math.max(1, Math.min(page - 2, totalPages - 4));
              const p = start + i;
              if (p > totalPages) return null;
              return (
                <Button
                  key={p}
                  variant={p === page ? 'default' : 'outline'}
                  size="icon"
                  className="h-8 w-8 text-xs"
                  onClick={() => goPage(p)}
                  data-testid={`audit-page-${p}`}
                >
                  {p}
                </Button>
              );
            })}
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              disabled={page >= totalPages}
              onClick={() => goPage(page + 1)}
              data-testid="audit-next-page"
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
