import { useState, useEffect, useCallback, useRef, memo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import {
  MessageCircle, X, Send, Mic, MicOff, Loader2,
  Sparkles, TrendingUp, Search, ShoppingCart, Trash2
} from 'lucide-react';

const QUICK_PROMPTS = [
  { label: 'Where should I buy today?', icon: ShoppingCart },
  { label: 'What prices increased this week?', icon: TrendingUp },
  { label: 'Find cheapest supplier for salmon', icon: Search },
];

/* ─── Markdown-lite renderer ─── */
function renderContent(text) {
  if (!text) return null;
  return text.split('\n').map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g).map((seg, j) => {
      if (seg.startsWith('**') && seg.endsWith('**')) {
        return <strong key={j} className="font-bold">{seg.slice(2, -2)}</strong>;
      }
      return seg;
    });
    const isBullet = line.trimStart().startsWith('- ') || line.trimStart().startsWith('• ');
    if (isBullet) {
      return <li key={i} className="ml-3 list-disc list-inside">{parts}</li>;
    }
    return <p key={i} className={line.trim() === '' ? 'h-2' : ''}>{parts}</p>;
  });
}

/* ─── Single Message Bubble ─── */
const ChatBubble = memo(function ChatBubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`} data-testid={`chat-msg-${msg.id}`}>
      <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed ${
        isUser
          ? 'bg-teal-600 text-white rounded-br-md'
          : 'bg-slate-100 text-slate-700 rounded-bl-md'
      }`}>
        {isUser ? msg.content : <div className="space-y-1">{renderContent(msg.content)}</div>}
      </div>
    </div>
  );
});

/* ─── Floating Assistant ─── */
export default function FloatingAssistant() {
  const { api, user } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [listening, setListening] = useState(false);
  const scrollRef = useRef(null);
  const recognitionRef = useRef(null);
  const inputRef = useRef(null);

  // Load chat history when panel opens
  useEffect(() => {
    if (!open || !api) return;
    setLoadingHistory(true);
    api.get('/chat/messages')
      .then(res => setMessages(res.data || []))
      .catch(() => {})
      .finally(() => setLoadingHistory(false));
  }, [open, api]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Cleanup speech recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, []);

  const sendMessage = useCallback(async (text) => {
    const msg = (text || input).trim();
    if (!msg || sending) return;
    setInput('');
    const tempUser = { id: `temp-${Date.now()}`, role: 'user', content: msg };
    setMessages(prev => [...prev, tempUser]);
    setSending(true);

    try {
      const res = await api.post('/chat', { message: msg });
      setMessages(prev => {
        const filtered = prev.filter(m => m.id !== tempUser.id);
        return [...filtered, res.data.user_message, res.data.assistant_message];
      });
    } catch {
      toast.error('Failed to get response');
      setMessages(prev => prev.filter(m => m.id !== tempUser.id));
    } finally {
      setSending(false);
    }
  }, [api, input, sending]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }, [sendMessage]);

  const clearChat = useCallback(async () => {
    try {
      await api.delete('/chat/messages');
      setMessages([]);
    } catch {
      toast.error('Failed to clear chat');
    }
  }, [api]);

  const toggleVoice = useCallback(() => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toast.error('Voice input not supported in this browser');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) {
        setInput(prev => prev ? `${prev} ${transcript}` : transcript);
        inputRef.current?.focus();
      }
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }, [listening]);

  const toggle = useCallback(() => setOpen(prev => !prev), []);

  if (!user) return null;

  return (
    <>
      {/* Chat Panel */}
      {open && (
        <div
          className="fixed bottom-[7.5rem] right-5 w-[380px] max-h-[560px] bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col z-50 overflow-hidden"
          style={{ animation: 'slideUp 0.2s ease-out' }}
          data-testid="ai-chat-panel"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-navy-900 text-white rounded-t-2xl flex-shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-teal-500 flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div>
                <h3 className="text-sm font-bold">AI Assistant</h3>
                <p className="text-[10px] text-slate-300">Your purchasing decision helper</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {messages.length > 0 && (
                <button
                  onClick={clearChat}
                  className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
                  title="Clear chat"
                  data-testid="ai-clear-chat"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
              <button
                onClick={toggle}
                className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
                data-testid="ai-close-btn"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 min-h-0" data-testid="ai-chat-messages">
            {loadingHistory ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
              </div>
            ) : messages.length === 0 ? (
              <div className="text-center py-6">
                <Sparkles className="w-8 h-8 text-teal-500 mx-auto mb-3" />
                <p className="text-sm font-semibold text-navy-900 mb-1">How can I help?</p>
                <p className="text-xs text-slate-400 mb-5">Ask me about your spending, vendors, or prices</p>

                <div className="space-y-2" data-testid="ai-quick-prompts">
                  {QUICK_PROMPTS.map((qp, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(qp.label)}
                      disabled={sending}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border border-slate-150 hover:border-teal-200 hover:bg-teal-50/40 transition-all text-left group"
                      data-testid={`ai-quick-prompt-${i}`}
                    >
                      <div className="w-7 h-7 rounded-lg bg-slate-100 group-hover:bg-teal-100 flex items-center justify-center flex-shrink-0 transition-colors">
                        <qp.icon className="w-3.5 h-3.5 text-slate-500 group-hover:text-teal-600 transition-colors" />
                      </div>
                      <span className="text-xs text-slate-600 group-hover:text-navy-900 transition-colors">{qp.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg) => <ChatBubble key={msg.id} msg={msg} />)
            )}

            {sending && (
              <div className="flex justify-start mb-3">
                <div className="bg-slate-100 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-teal-600" />
                  <span className="text-xs text-slate-500">Analyzing your data...</span>
                </div>
              </div>
            )}
          </div>

          {/* Quick prompts bar (when conversation exists) */}
          {messages.length > 0 && (
            <div className="px-3 py-2 border-t border-slate-100 flex-shrink-0 overflow-x-auto">
              <div className="flex gap-1.5">
                {QUICK_PROMPTS.map((qp, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(qp.label)}
                    disabled={sending}
                    className="flex-shrink-0 px-2.5 py-1 rounded-full text-[10px] font-medium bg-slate-100 text-slate-500 hover:bg-teal-50 hover:text-teal-700 transition-colors whitespace-nowrap disabled:opacity-50"
                    data-testid={`ai-quick-pill-${i}`}
                  >
                    {qp.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="px-3 py-3 border-t border-slate-100 flex-shrink-0">
            <div className="flex items-center gap-2">
              <button
                onClick={toggleVoice}
                className={`flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-colors ${
                  listening
                    ? 'bg-red-100 text-red-600 animate-pulse'
                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                }`}
                title={listening ? 'Stop listening' : 'Voice input'}
                data-testid="ai-voice-btn"
              >
                {listening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>
              <Input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your finances..."
                className="flex-1 h-9 text-sm border-slate-200 rounded-xl focus:border-teal-500 focus:ring-teal-500/20"
                disabled={sending}
                data-testid="ai-chat-input"
              />
              <Button
                onClick={() => sendMessage()}
                disabled={!input.trim() || sending}
                size="icon"
                className="flex-shrink-0 w-9 h-9 rounded-xl bg-teal-600 hover:bg-teal-700 text-white disabled:opacity-40"
                data-testid="ai-send-btn"
              >
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Button */}
      <button
        onClick={toggle}
        className={`fixed bottom-16 right-5 w-14 h-14 rounded-full shadow-xl flex items-center justify-center z-50 transition-all duration-200 ${
          open
            ? 'bg-slate-700 hover:bg-slate-800 scale-90'
            : 'bg-teal-600 hover:bg-teal-700 hover:scale-105'
        }`}
        style={{ boxShadow: open ? undefined : '0 4px 24px rgba(13,148,136,0.35)' }}
        data-testid="ai-float-btn"
      >
        {open ? (
          <X className="w-6 h-6 text-white" />
        ) : (
          <Sparkles className="w-6 h-6 text-white" />
        )}
      </button>

      <style>{`
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </>
  );
}
