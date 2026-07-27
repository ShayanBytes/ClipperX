import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';

class StartupBoundary extends React.Component<React.PropsWithChildren, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: React.ErrorInfo) { console.error('ClipperX startup error', error, info); }
  render() {
    if (this.state.error) {
      return <main className="startup-error"><div><strong>ClipperX could not start</strong><p>{this.state.error.message}</p><small>Open the browser console for the full error, then restart with <code>npm run dev</code>.</small></div></main>;
    }
    return this.props.children;
  }
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');
ReactDOM.createRoot(root).render(<React.StrictMode><StartupBoundary><App /></StartupBoundary></React.StrictMode>);
