import { useState, useEffect, useRef, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  Send, Loader2, Trash2, TrendingUp, Calendar,
  CalendarDays, BarChart3, CircleDollarSign, ChefHat,
  ArrowRight, ShieldCheck, TriangleAlert
} from 'lucide-react';

const questionCategories = [
  {
    label: 'This Week',
    icon: Calendar,
    color: 'teal',
    questions: [
      "What's my spending this week vs last week?",
      "Show my top 3 expenses this week",
      "How are my weekly sales trending?",
    ],
  },
  {
    label: 'Monthly',
    icon: CalendarDays,
    color: 'blue',
    questions: [
      "Compare this month to last month",
      "Which supplier costs me the most this month?",
      "What's my monthly gross margin?",
    ],
  },
  {
    label: 'Yearly',
    icon: BarChart3,
    color: 'amber',
    questions: [
      "What's my year-to-date profit?",
      "Show my top 5 expense items this year",
      "How have my costs changed over the year?",
    ],
  },
  {
    label: 'Insights',
    icon: TrendingUp,
    color: 'rose',
    questions: [
      "Which items have increased in price recently?",
      "Who is my most cost-effective supplier?",
      "Where can I cut costs without hurting quality?",
    ],
  },
];

const colorMap = {
  teal: { bg: 'bg-teal-50', border: 'border-teal-200', text: 'text-teal-700', icon: 'text-teal-600', hoverBg: 'hover:bg-teal-100', badgeBg: 'bg-teal-100' },
  blue: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', icon: 'text-blue-600', hoverBg: 'hover:bg-blue-100', badgeBg: 'bg-blue-100' },
  amber: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', icon: 'text-amber-600', hoverBg: 'hover:bg-amber-100', badgeBg: 'bg-amber-100' },
  rose: { bg: 'bg-rose-50', border: 'border-rose-200', text: 'text-rose-700', icon: 'text-rose-600', hoverBg: 'hover:bg-rose-100', badgeBg: 'bg-rose-100' },
};

function FormattedMessage({ content }) {
  const parts = useMemo(() => {
    if (!content) return [];
    return content.split('\n').map((line, i) => {
      // Bold: **text**
      const segments = line.split(/(\*\*[^*]+\*\*)/g).map((seg, j) => {
        if (seg.startsWith('**') && seg.endsWith('**')) {
          return <strong key={j} className="font-semibold text-navy-900">{seg.slice(2, -2)}</strong>;
        }
        return <span key={j}>{seg}</span>;
      });

      const trimmed = line.trim();
      // Bullet points
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        return (
          <div key={i} className="flex items-start gap-2 ml-1 py-0.5">
            <span className="w-1 h-1 rounded-full bg-navy-400 mt-2 flex-shrink-0" />
            <span className="flex-1">{segments}</span>
          </div>
        );
      }
      // Numbered lists
      if (/^\d+[.)]\s/.test(trimmed)) {
        const num = trimmed.match(/^(\d+)/)[1];
        return (
          <div key={i} className="flex items-start gap-2 ml-1 py-0.5">
            <span className="text-teal-600 font-semibold text-xs mt-0.5 flex-shrink-0 w-4">{num}.</span>
            <span className="flex-1">{segments}</span>
          </div>
        );
      }
      // Empty line
      if (trimmed === '') return <div key={i} className="h-2" />;
      // Normal paragraph
      return <p key={i} className="py-0.5">{segments}</p>;
    });
  }, [content]);

  return <div className="text-[13px] leading-relaxed text-navy-800">{parts}</div>;
}

export default function ChatPage() {
  const { api } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  const loadMessages = async () => {
    try {
      const res = await api.get('/chat/messages');
      setMessages(res.data);
    } catch { /* ignore */ }
    finally { setLoadingHistory(false); }
  };

  useEffect(() => { loadMessages(); }, []); // eslint-disable-line
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  const send = async (text) => {
    const msg = text || input.trim();
    if (!msg || sending) return;
    setInput('');
    setSending(true);
    const tempId = `temp-${Date.now()}`;
    setMessages(prev => [...prev, { id: tempId, role: 'user', content: msg, created_at: new Date().toISOString() }]);
    try {
      const res = await api.post('/chat', { message: msg });
      setMessages(prev => [
        ...prev.filter(m => m.id !== tempId),
        res.data.user_message,
        res.data.assistant_message,
      ]);
    } catch {
      toast.error('Failed to get a response. Please try again.');
      setMessages(prev => prev.filter(m => m.id !== tempId));
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const clearChat = async () => {
    try {
      await api.delete('/chat/messages');
      setMessages([]);
      toast.success('Conversation cleared');
    } catch {
      toast.error('Could not clear chat');
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <div className="h-[calc(100vh-7.5rem)] flex flex-col max-w-4xl mx-auto" data-testid="chat-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500 to-teal-700 flex items-center justify-center shadow-sm">
            <CircleDollarSign className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight" data-testid="chat-page-title">
              Financial Assistant
            </h1>
            <p className="text-xs text-slate-400 mt-0.5">AI-powered insights for your restaurant</p>
          </div>
        </div>
        {hasMessages && (
          <Button
            variant="outline"
            size="sm"
            onClick={clearChat}
            className="text-xs h-8 border-slate-200 text-slate-500 hover:text-red-600 hover:border-red-200 hover:bg-red-50 transition-colors"
            data-testid="clear-chat-btn"
          >
            <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Clear
          </Button>
        )}
      </div>

      {/* Chat Area */}
      <Card className="flex-1 flex flex-col border border-slate-200/80 shadow-sm overflow-hidden bg-white">
        <ScrollArea className="flex-1">
          <div className="p-4 sm:p-5">
            {loadingHistory ? (
              <div className="space-y-4 py-8">
                {[1, 2, 3].map(i => (
                  <Skeleton
                    key={i}
                    className="h-16 rounded-2xl"
                    style={{ width: i % 2 === 0 ? '65%' : '75%', marginLeft: i % 2 === 0 ? 'auto' : 0 }}
                  />
                ))}
              </div>
            ) : !hasMessages ? (
              /* Empty State — Quick Questions */
              <div className="py-6" data-testid="chat-empty-state">
                <div className="text-center mb-8">
                  <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-teal-50 to-teal-100 flex items-center justify-center mx-auto mb-4 border border-teal-200/50">
                    <ShieldCheck className="w-7 h-7 text-teal-600" />
                  </div>
                  <h3 className="font-heading text-base font-bold text-navy-900 mb-1.5">
                    What would you like to know?
                  </h3>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto">
                    Ask about your purchases, sales, suppliers, or trends. Tap a question below or type your own.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {questionCategories.map((cat) => {
                    const c = colorMap[cat.color];
                    const Icon = cat.icon;
                    return (
                      <div
                        key={cat.label}
                        className={`rounded-xl border ${c.border} ${c.bg} p-3.5 transition-all duration-200`}
                        data-testid={`question-category-${cat.label.toLowerCase().replace(/\s/g, '-')}`}
                      >
                        <div className="flex items-center gap-2 mb-2.5">
                          <div className={`w-6 h-6 rounded-md ${c.badgeBg} flex items-center justify-center`}>
                            <Icon className={`w-3.5 h-3.5 ${c.icon}`} />
                          </div>
                          <span className={`text-xs font-semibold ${c.text}`}>{cat.label}</span>
                        </div>
                        <div className="space-y-1.5">
                          {cat.questions.map((q, qi) => (
                            <button
                              key={qi}
                              onClick={() => send(q)}
                              className={`w-full text-left text-[12px] text-navy-700 bg-white/70 border border-transparent rounded-lg px-3 py-2 ${c.hoverBg} hover:border-current/10 transition-all duration-150 flex items-center justify-between group`}
                              data-testid={`suggested-q-${cat.label.toLowerCase().replace(/\s/g, '-')}-${qi}`}
                            >
                              <span className="flex-1 pr-2">{q}</span>
                              <ArrowRight className="w-3 h-3 text-slate-300 group-hover:text-current group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Messages */
              <div className="space-y-4">
                {messages.map((m, i) => (
                  <div
                    key={m.id || i}
                    className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} chat-bubble`}
                    data-testid={`chat-message-${m.role}-${i}`}
                  >
                    {m.role === 'assistant' && (
                      <div className="w-7 h-7 rounded-lg bg-teal-600 flex items-center justify-center mr-2 mt-1 flex-shrink-0">
                        <ChefHat className="w-3.5 h-3.5 text-white" />
                      </div>
                    )}
                    <div
                      className={`max-w-[78%] rounded-2xl px-4 py-3 ${
                        m.role === 'user'
                          ? 'bg-navy-900 text-white rounded-br-md'
                          : 'bg-slate-50 border border-slate-200/80 rounded-bl-md'
                      }`}
                    >
                      {m.role === 'user' ? (
                        <p className="text-[13px] leading-relaxed">{m.content}</p>
                      ) : (
                        <FormattedMessage content={m.content} />
                      )}
                      <p className={`text-[10px] mt-2 ${m.role === 'user' ? 'text-navy-400' : 'text-slate-400'}`}>
                        {m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                      </p>
                    </div>
                  </div>
                ))}

                {sending && (
                  <div className="flex justify-start chat-bubble" data-testid="chat-thinking-indicator">
                    <div className="w-7 h-7 rounded-lg bg-teal-600 flex items-center justify-center mr-2 mt-1 flex-shrink-0">
                      <ChefHat className="w-3.5 h-3.5 text-white" />
                    </div>
                    <div className="bg-slate-50 border border-slate-200/80 rounded-2xl rounded-bl-md px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                          <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                          <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                        <span className="text-xs text-slate-400 ml-1">Analyzing your data...</span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={scrollRef} />
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Input Bar */}
        <div className="p-3 border-t border-slate-100 bg-white/80 backdrop-blur-sm" data-testid="chat-input-area">
          {hasMessages && !sending && (
            <div className="flex gap-1.5 mb-2 overflow-x-auto pb-1 scrollbar-hide">
              {['How does this week compare?', 'Show monthly breakdown', 'Any price alerts?'].map((q, i) => (
                <button
                  key={i}
                  onClick={() => send(q)}
                  className="flex-shrink-0 text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded-full px-3 py-1 hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700 transition-all duration-150"
                  data-testid={`quick-followup-${i}`}
                >
                  {q}
                </button>
              ))}
            </div>
          )}
          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2">
            <Input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your restaurant finances..."
              className="flex-1 h-11 rounded-xl border-slate-200 bg-slate-50/50 focus:bg-white text-sm transition-colors"
              disabled={sending}
              data-testid="chat-input"
            />
            <Button
              type="submit"
              disabled={sending || !input.trim()}
              className="bg-teal-600 hover:bg-teal-700 text-white h-11 w-11 rounded-xl p-0 transition-colors disabled:opacity-40"
              data-testid="chat-send-btn"
            >
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}
