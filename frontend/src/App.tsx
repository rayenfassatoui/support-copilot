import { useEffect } from 'react';
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { KnowledgePage } from './pages/KnowledgePage';
import { TicketCreatePage } from './pages/TicketCreatePage';
import { TicketDetailPage } from './pages/TicketDetailPage';
import { TicketsPage } from './pages/TicketsPage';

export function App() {
  const { pathname } = useLocation();
  useEffect(() => {
    const page = pathname === '/knowledge' ? 'Knowledge Base'
      : pathname === '/tickets/new' ? 'New ticket'
        : pathname === '/tickets' || pathname === '/' ? 'Tickets'
          : pathname.startsWith('/tickets/') ? 'Ticket details' : 'Page not found';
    document.title = `${page} · Support Copilot`;
    document.getElementById('main-content')?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [pathname]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="app-header">
        <div className="header-content">
          <Link className="brand" to="/tickets" aria-label="Support Copilot — tickets"><span className="brand-mark" aria-hidden="true">SC</span><span>Support Copilot</span></Link>
          <nav className="primary-nav" aria-label="Main navigation"><NavLink to="/tickets">Tickets</NavLink><NavLink to="/knowledge">Knowledge Base</NavLink></nav>
          <span className="review-label">Human review required</span>
        </div>
      </header>
      <main id="main-content" className="main-content" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Navigate to="/tickets" replace />} />
          <Route path="/tickets" element={<TicketsPage />} />
          <Route path="/tickets/new" element={<TicketCreatePage />} />
          <Route path="/tickets/:id" element={<TicketDetailPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
      <footer className="app-footer"><p>Local support demo · Use synthetic customer data and fictional policies.</p><p>AI recommends and drafts. An agent decides; nothing is sent automatically.</p></footer>
    </div>
  );
}

function NotFoundPage() {
  return <section className="panel not-found"><p className="eyebrow">404</p><h1>Page not found</h1><p>This route does not exist. Return to the ticket workspace to continue.</p><Link className="button" to="/tickets">Back to tickets</Link></section>;
}
