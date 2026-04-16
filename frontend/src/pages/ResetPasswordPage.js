import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { ChefHat, ArrowLeft, Lock, CheckCircle, XCircle, Loader2, ShieldCheck } from 'lucide-react';
import api from '@/lib/api';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [verifying, setVerifying] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [tokenError, setTokenError] = useState('');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setVerifying(false);
      setTokenError('No reset token provided.');
      return;
    }
    api.get(`/auth/verify-reset-token?token=${token}`)
      .then(res => {
        if (res.data.valid) {
          setTokenValid(true);
        } else {
          setTokenError(
            res.data.reason === 'expired'
              ? 'This reset link has expired. Please request a new one.'
              : 'This reset link is invalid or has already been used.'
          );
        }
      })
      .catch(() => setTokenError('Unable to verify reset link. Please try again.'))
      .finally(() => setVerifying(false));
  }, [token]);

  const passwordsMatch = password.length >= 6 && password === confirmPassword;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!passwordsMatch) return;
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/auth/reset-password', { token, new_password: password });
      setSuccess(true);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Password reset failed. The link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" data-testid="reset-password-page">
      <div className="hidden lg:flex lg:w-1/2 bg-navy-900 items-center justify-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-navy-900" />
        <div className="relative z-10 text-center max-w-md">
          <div className="w-16 h-16 rounded-2xl bg-teal-600 flex items-center justify-center mx-auto mb-8">
            <ChefHat className="w-8 h-8 text-white" />
          </div>
          <h1 className="font-heading text-4xl font-extrabold text-white mb-4 tracking-tight">Restaurant Accountant AI</h1>
          <p className="text-navy-300 text-lg leading-relaxed">Set your new password and get back to work.</p>
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
              {success ? 'Password reset!' : verifying ? 'Verifying...' : tokenValid ? 'Set new password' : 'Link invalid'}
            </CardTitle>
            <CardDescription className="text-slate-500">
              {success
                ? 'Your password has been updated successfully.'
                : verifying
                  ? 'Checking your reset link...'
                  : tokenValid
                    ? 'Enter your new password below.'
                    : tokenError}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {verifying ? (
              <div className="flex items-center justify-center py-8" data-testid="verifying-spinner">
                <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
              </div>
            ) : success ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-lg p-4" data-testid="reset-success-message">
                  <CheckCircle className="w-6 h-6 text-emerald-600 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-emerald-800">Password updated</p>
                    <p className="text-xs text-emerald-600 mt-0.5">You can now sign in with your new password.</p>
                  </div>
                </div>
                <Link to="/login">
                  <Button className="w-full bg-navy-900 hover:bg-navy-800 text-white h-11 font-medium" data-testid="goto-login-btn">
                    <ArrowLeft className="w-4 h-4 mr-2" /> Sign In
                  </Button>
                </Link>
              </div>
            ) : !tokenValid ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-lg p-4" data-testid="token-invalid-message">
                  <XCircle className="w-6 h-6 text-red-600 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-red-800">Reset link unavailable</p>
                    <p className="text-xs text-red-600 mt-0.5">{tokenError}</p>
                  </div>
                </div>
                <Link to="/forgot-password">
                  <Button variant="outline" className="w-full h-11" data-testid="request-new-link-btn">
                    Request a New Reset Link
                  </Button>
                </Link>
                <Link to="/login">
                  <Button variant="ghost" className="w-full h-10 text-sm text-slate-500" data-testid="back-to-login-btn">
                    <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Back to Sign In
                  </Button>
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4" data-testid="reset-password-form">
                <div className="space-y-2">
                  <Label htmlFor="new-password" className="text-sm font-medium">New Password</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input
                      id="new-password"
                      type="password"
                      className="pl-10 h-11"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Min 6 characters"
                      required
                      minLength={6}
                      data-testid="new-password-input"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirm-password" className="text-sm font-medium">Confirm New Password</Label>
                  <div className="relative">
                    <ShieldCheck className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input
                      id="confirm-password"
                      type="password"
                      className="pl-10 h-11"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Confirm your password"
                      required
                      minLength={6}
                      data-testid="confirm-password-input"
                    />
                  </div>
                  {confirmPassword && password !== confirmPassword && (
                    <p className="text-xs text-red-500 font-medium" data-testid="password-mismatch">Passwords do not match</p>
                  )}
                  {passwordsMatch && (
                    <p className="text-xs text-emerald-600 font-medium flex items-center gap-1" data-testid="password-match">
                      <CheckCircle className="w-3 h-3" /> Passwords match
                    </p>
                  )}
                </div>

                {error && (
                  <p className="text-xs font-semibold text-red-600 bg-red-50 border border-red-200 px-3 py-2 rounded-md" data-testid="reset-error">{error}</p>
                )}

                <Button
                  type="submit"
                  className="w-full bg-navy-900 hover:bg-navy-800 text-white h-11 font-medium"
                  disabled={loading || !passwordsMatch}
                  data-testid="reset-submit-btn"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Lock className="w-4 h-4 mr-2" />}
                  Reset Password
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
