import { Component } from 'react';
import { Button } from '@/components/ui/button';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export class StableErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[StableErrorBoundary]', error.message, errorInfo.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center" data-testid="error-boundary-fallback">
          <AlertTriangle className="w-8 h-8 text-amber-400 mb-3" />
          <h3 className="text-sm font-semibold text-slate-700 mb-1">Something went wrong</h3>
          <p className="text-xs text-slate-400 mb-4 max-w-xs">A rendering error occurred. Click below to retry.</p>
          <Button onClick={this.handleRetry} variant="outline" size="sm" className="text-xs gap-1.5" data-testid="error-retry-btn">
            <RefreshCw className="w-3 h-3" /> Retry
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
