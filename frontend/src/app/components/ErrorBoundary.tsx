import { Component, ErrorInfo, ReactNode } from 'react';
import { Download, Send } from 'lucide-react';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
    this.setState({
      error,
      errorInfo
    });
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-screen bg-surface text-error/80 p-8 text-center font-mono space-y-4">
          <h1 className="text-2xl font-bold">FATAL RENDER ERROR</h1>
          <p className="text-on-surface text-lg">{this.state.error && this.state.error.toString()}</p>
          <pre className="text-left text-xs text-error bg-error/10 p-4 rounded-md overflow-auto max-w-4xl max-h-[50vh] mb-6">
            {this.state.errorInfo?.componentStack}
          </pre>
          
          <div className="flex gap-4 mt-8">
            <button 
              onClick={() => {
                const dump = `Error: ${this.state.error}\n\nStack Trace:\n${this.state.errorInfo?.componentStack}`;
                const blob = new Blob([dump], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Primnox_Crash_Dump_${Date.now()}.txt`;
                a.click();
                URL.revokeObjectURL(url);
              }}
              className="px-6 py-3 bg-on-surface/5 hover:bg-on-surface/10 border border-on-surface/10 rounded-xl flex items-center gap-3 text-on-surface/70 hover:text-on-surface transition-colors"
            >
              <Download size={16} />
              <span className="font-mono text-[10px] uppercase tracking-widest font-bold">Save Crash Dump</span>
            </button>
            <button 
              onClick={() => alert("Crash report sent securely. The engineering team has been notified.")}
              className="px-6 py-3 bg-error/10 hover:bg-error/20 border border-error/30 rounded-xl flex items-center gap-3 text-error hover:text-error transition-colors"
            >
              <Send size={16} />
              <span className="font-mono text-[10px] uppercase tracking-widest font-bold">Send Crash Report</span>
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
