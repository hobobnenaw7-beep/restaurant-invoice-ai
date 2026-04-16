import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { toast } from 'sonner';
import { ChefHat, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function LoginPage() {
  const { login, register } = useAuth();
  const [isSignup, setIsSignup] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ email: '', password: '', name: '', restaurant_name: '' });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (isSignup) {
        await register(form.email, form.password, form.name, form.restaurant_name);
        toast.success('Account created successfully!');
      } else {
        await login(form.email, form.password);
        toast.success('Welcome back!');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      <div className="hidden lg:flex lg:w-1/2 bg-navy-900 items-center justify-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-navy-900" />
        <div className="relative z-10 text-center max-w-md">
          <div className="w-16 h-16 rounded-2xl bg-teal-600 flex items-center justify-center mx-auto mb-8">
            <ChefHat className="w-8 h-8 text-white" />
          </div>
          <h1 className="font-heading text-4xl font-extrabold text-white mb-4 tracking-tight">Restaurant Accountant AI</h1>
          <p className="text-navy-300 text-lg leading-relaxed">Smart financial tracking and analysis for your restaurant. Upload invoices, track spending, and get AI-powered insights.</p>
          <div className="mt-12 grid grid-cols-3 gap-4">
            {['Invoice Scanning', 'Smart Reports', 'AI Assistant'].map((f, i) => (
              <div key={i} className="bg-navy-800/50 rounded-xl p-4 border border-navy-700/50">
                <p className="text-teal-400 text-sm font-semibold">{f}</p>
              </div>
            ))}
          </div>
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
              {isSignup ? 'Create your account' : 'Welcome back'}
            </CardTitle>
            <CardDescription className="text-slate-500">
              {isSignup ? 'Start tracking your restaurant finances' : 'Sign in to your dashboard'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4" data-testid="auth-form">
              {isSignup && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="name" className="text-sm font-medium">Full Name</Label>
                    <Input id="name" data-testid="input-name" value={form.name} onChange={set('name')} placeholder="John Doe" required />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="restaurant" className="text-sm font-medium">Restaurant Name</Label>
                    <Input id="restaurant" data-testid="input-restaurant" value={form.restaurant_name} onChange={set('restaurant_name')} placeholder="My Restaurant" required />
                  </div>
                </>
              )}
              <div className="space-y-2">
                <Label htmlFor="email" className="text-sm font-medium">Email</Label>
                <Input id="email" data-testid="input-email" type="email" value={form.email} onChange={set('email')} placeholder="you@restaurant.com" required />
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="text-sm font-medium">Password</Label>
                  {!isSignup && (
                    <Link to="/forgot-password" className="text-xs text-teal-600 hover:text-teal-700 font-medium transition-colors" data-testid="forgot-password-link">
                      Forgot password?
                    </Link>
                  )}
                </div>
                <Input id="password" data-testid="input-password" type="password" value={form.password} onChange={set('password')} placeholder="Min 6 characters" required minLength={6} />
              </div>
              <Button
                type="submit"
                className="w-full bg-navy-900 hover:bg-navy-800 text-white h-11 font-medium"
                disabled={loading}
                data-testid="auth-submit-btn"
              >
                {loading ? <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> : (
                  <>{isSignup ? 'Create Account' : 'Sign In'}<ArrowRight className="w-4 h-4 ml-2" /></>
                )}
              </Button>
            </form>
            <div className="mt-6 text-center">
              <button
                onClick={() => setIsSignup(!isSignup)}
                className="text-sm text-teal-600 hover:text-teal-700 font-medium transition-colors"
                data-testid="toggle-auth-mode"
              >
                {isSignup ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
