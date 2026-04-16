import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { ChefHat, ArrowLeft, Mail, CheckCircle, Loader2 } from 'lucide-react';
import api from '@/lib/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setError('');
    setLoading(true);
    try {
      await api.post('/auth/forgot-password', { email: email.trim() });
      setSent(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" data-testid="forgot-password-page">
      <div className="hidden lg:flex lg:w-1/2 bg-navy-900 items-center justify-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-navy-900" />
        <div className="relative z-10 text-center max-w-md">
          <div className="w-16 h-16 rounded-2xl bg-teal-600 flex items-center justify-center mx-auto mb-8">
            <ChefHat className="w-8 h-8 text-white" />
          </div>
          <h1 className="font-heading text-4xl font-extrabold text-white mb-4 tracking-tight">Restaurant Accountant AI</h1>
          <p className="text-navy-300 text-lg leading-relaxed">Reset your password and get back to managing your restaurant finances.</p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 lg:p-12 bg-white">
        <Card className="w-full max-w-md border-0 shadow-none">
          <CardHeader className="space-y-2 pb-6">
            <div className="lg:hidden flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-teal-600 flex items-center justify-center">
                <ChefHat className="w-5 h-5 text-white" />
              </div>
              <span className="font-heading font-bold text-lg">Restaurant Accountant AI</span>
            </div>
            <CardTitle className="font-heading text-2xl font-bold tracking-tight">
              {sent ? 'Check your email' : 'Forgot password?'}
            </CardTitle>
            <CardDescription className="text-slate-500">
              {sent
                ? 'If the account is eligible, a reset link has been sent.'
                : 'Enter your email address and we\'ll send you a link to reset your password.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {sent ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-lg p-4" data-testid="reset-sent-message">
                  <CheckCircle className="w-6 h-6 text-emerald-600 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-emerald-800">Reset link sent</p>
                    <p className="text-xs text-emerald-600 mt-0.5">
                      If <span className="font-mono font-bold">{email}</span> is associated with a Manager account, you'll receive a reset link. The link expires in 15 minutes.
                    </p>
                  </div>
                </div>
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3" data-testid="non-manager-notice">
                  <p className="text-xs text-amber-700">
                    <span className="font-bold">Not a Manager?</span> Password reset is only available for Manager accounts.
                    Accountants, Cashiers, and Staff should contact their Manager for a password reset.
                  </p>
                </div>
                <Link to="/login">
                  <Button variant="outline" className="w-full h-11 mt-2" data-testid="back-to-login-btn">
                    <ArrowLeft className="w-4 h-4 mr-2" /> Back to Sign In
                  </Button>
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4" data-testid="forgot-password-form">
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-sm font-medium">Email address</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input
                      id="email"
                      type="email"
                      className="pl-10 h-11"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@restaurant.com"
                      required
                      data-testid="forgot-email-input"
                    />
                  </div>
                </div>

                <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                  <p className="text-[11px] text-slate-500">
                    Password reset is available for <span className="font-bold text-slate-700">Manager accounts only</span>.
                    Other roles should contact their Manager for assistance.
                  </p>
                </div>

                {error && (
                  <p className="text-xs font-semibold text-red-600 bg-red-50 border border-red-200 px-3 py-2 rounded-md" data-testid="forgot-error">{error}</p>
                )}

                <Button
                  type="submit"
                  className="w-full bg-navy-900 hover:bg-navy-800 text-white h-11 font-medium"
                  disabled={loading || !email.trim()}
                  data-testid="forgot-submit-btn"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Mail className="w-4 h-4 mr-2" />}
                  Send Reset Link
                </Button>

                <Link to="/login">
                  <Button variant="ghost" className="w-full h-10 text-sm text-slate-500 hover:text-slate-700 mt-1" data-testid="back-to-login-link">
                    <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Back to Sign In
                  </Button>
                </Link>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
