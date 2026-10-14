import { useEffect, useRef, useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { ArrowLeft, BookOpen, ChartNoAxesCombined, ChevronRight, CircleHelp, Inbox, Layers2, LogOut, Mail, Menu, Plus, Settings2, ShieldCheck, Sparkles, Workflow, X } from 'lucide-react';
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { KnowledgePage } from './pages/KnowledgePage';
import { TicketCreatePage } from './pages/TicketCreatePage';
import { TicketsPage } from './pages/TicketsPage';
import { useAuth } from './auth';
import { AuthPage } from './pages/AuthPage';
import { SettingsPage } from './pages/SettingsPage';
import { Loading } from './components/Feedback';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { AutomationPage } from './pages/AutomationPage';
import { MailboxPage } from './pages/MailboxPage';
import { CustomerFeedbackPage } from './pages/CustomerFeedbackPage';
import { CommandPalette } from './components/CommandPalette';
import { SlaAlerts } from './components/SlaAlerts';
import { useDraftRegistry } from './drafts';
import './pages/workspace.css';
import './pages/operations.css';

function WorkspaceNavigation({ onNavigate }: { onNavigate?: () => void }) {
  const { member } = useAuth();
  return (
    <>
      <Link className="brand" to="/tickets" aria-label="Support Copilot — tickets" onClick={onNavigate}>
        <span className="brand-mark" aria-hidden="true"><span /><span /><span /></span>
        <span>Support<span className="brand-secondary">Copilot</span></span>
      </Link>
      <div className="workspace-identity"><span className="workspace-icon" aria-hidden="true">a</span><span><strong>AcmeCloud</strong><span>Support workspace</span></span></div>
      <p className="nav-section-label">Workspace</p>
      <nav className="primary-nav" aria-label="Main navigation">
        <NavLink to="/tickets" onClick={onNavigate}><Inbox size={18} aria-hidden="true" /><span>Tickets</span><ChevronRight className="nav-active-mark" size={14} aria-hidden="true" /></NavLink>
        <NavLink to="/knowledge" onClick={onNavigate}><BookOpen size={18} aria-hidden="true" /><span>Knowledge base</span><ChevronRight className="nav-active-mark" size={14} aria-hidden="true" /></NavLink>
        <NavLink to="/analytics" onClick={onNavigate}><ChartNoAxesCombined size={18} aria-hidden="true" /><span>Analytics</span><ChevronRight className="nav-active-mark" size={14} aria-hidden="true" /></NavLink>
        {member?.role === 'admin' && <><NavLink to="/mailbox" onClick={onNavigate}><Mail size={18} aria-hidden="true" /><span>Support mailbox</span><ChevronRight className="nav-active-mark" size={14} aria-hidden="true" /></NavLink><NavLink to="/automation" onClick={onNavigate}><Workflow size={18} aria-hidden="true" /><span>Automation</span><ChevronRight className="nav-active-mark" size={14} aria-hidden="true" /></NavLink></>}
        {member?.role === 'admin' && <NavLink to="/settings" onClick={onNavigate}><Settings2 size={18} aria-hidden="true" /><span>Settings</span><ChevronRight className="nav-active-mark" size={14} aria-hidden="true" /></NavLink>}
      </nav>
      <Link className="button sidebar-create" to="/tickets/new" onClick={onNavigate}><Plus size={16} aria-hidden="true" />New ticket</Link>
      <div className="sidebar-bottom">
        <div className="review-guidance"><ShieldCheck size={18} aria-hidden="true" /><div><strong>You're in control.</strong><p>AI drafts and recommends.<br />Nothing is sent automatically.</p></div></div>
        <div className="sidebar-environment"><span className="environment-dot" aria-hidden="true" /><span>Support workspace</span><span className="environment-tag">Human-reviewed</span></div>
      </div>
    </>
  );
}

export function App() {
  const { member, loading } = useAuth();
  const { pathname } = useLocation();
  if (pathname === '/feedback') return <CustomerFeedbackPage />;
  if (loading) return <main className="auth-loading"><Loading>Checking your session…</Loading></main>;
  return member ? <Workspace /> : <AuthPage />;
}

function Workspace() {
  const auth = useAuth();
  const drafts = useDraftRegistry();
  const [accountError, setAccountError] = useState('');
  const { pathname } = useLocation();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigating = useRef(false);
  const page = pathname === '/knowledge' ? 'Knowledge base'
    : pathname === '/settings' ? 'Workspace settings'
      : pathname === '/analytics' ? 'Service analytics'
        : pathname === '/mailbox' ? 'Support mailbox'
          : pathname === '/automation' ? 'Automation'
      : pathname === '/tickets/new' ? 'New ticket'
        : pathname === '/tickets' || pathname === '/' ? 'Tickets'
          : pathname.startsWith('/tickets/') ? 'Ticket details' : 'Page not found';

  useEffect(() => {
    document.title = `${page} · Support Copilot`;
    document.getElementById('main-content')?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [pathname, page]);

  function closeForNavigation() {
    navigating.current = true;
    setNavigationOpen(false);
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <aside className="app-sidebar" aria-label="Workspace sidebar"><WorkspaceNavigation /></aside>
      <div className="workspace-surface">
        <header className="workspace-topbar">
          <div className="workspace-breadcrumbs">
            <Dialog.Root open={navigationOpen} onOpenChange={(open) => { if (open) navigating.current = false; setNavigationOpen(open); }}>
              <Dialog.Trigger className="icon-button mobile-navigation-trigger" aria-label="Open navigation"><Menu size={20} aria-hidden="true" /></Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Backdrop className="dialog-backdrop" />
                <Dialog.Popup className="navigation-drawer" finalFocus={() => navigating.current ? document.getElementById('main-content') : true}>
                  <Dialog.Title className="sr-only">Workspace navigation</Dialog.Title>
                  <Dialog.Description className="sr-only">Navigate tickets and the knowledge base.</Dialog.Description>
                  <Dialog.Close className="icon-button navigation-close" aria-label="Close navigation"><X size={20} aria-hidden="true" /></Dialog.Close>
                  <WorkspaceNavigation onNavigate={closeForNavigation} />
                </Dialog.Popup>
              </Dialog.Portal>
            </Dialog.Root>
            <Link to="/tickets" className="breadcrumb-workspace">AcmeCloud</Link><ChevronRight size={13} aria-hidden="true" /><span aria-current="page">{page}</span>
          </div>
          <div className="workspace-utilities">
            <CommandPalette /><SlaAlerts />
            <span className="review-label"><ShieldCheck size={14} aria-hidden="true" />Human-reviewed AI</span>
            <div className="account-controls"><span className="account-role" title={auth.member?.email}>{auth.member?.role === 'admin' ? 'Admin' : 'Agent'}</span><button type="button" className="icon-button" aria-label="Sign out" onClick={() => { setAccountError(''); void drafts.flushAll().then(async () => { await auth.signOut(); drafts.queues.clear(); drafts.changed(); }).catch(error => setAccountError(error.message)); }}><LogOut size={17} aria-hidden="true" /></button></div>
            <Dialog.Root>
              <Dialog.Trigger className="icon-button" aria-label="About this workspace"><CircleHelp size={18} aria-hidden="true" /></Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Backdrop className="dialog-backdrop" />
                <Dialog.Popup className="dialog-popup workspace-about">
                  <div className="dialog-header"><div><span className="dialog-symbol" aria-hidden="true"><Layers2 size={24} /></span><Dialog.Title>A copilot, not autopilot.</Dialog.Title><Dialog.Description>One place to manage requests, review AI advice and inspect its sources.</Dialog.Description></div><Dialog.Close className="icon-button dialog-close" aria-label="Close workspace information"><X size={18} aria-hidden="true" /></Dialog.Close></div>
                  <ul className="workspace-principles">
                    <li><BookOpen size={20} aria-hidden="true" /><div><h3>Start with the evidence</h3><p>Open the original knowledge document behind a citation. If there is no supported answer, handle the request manually.</p></div></li>
                    <li><Sparkles size={20} aria-hidden="true" /><div><h3>Review before you act</h3><p>AI classifies, drafts and recommends. You decide what to copy and when to escalate. Nothing is sent automatically.</p></div></li>
                    <li><ShieldCheck size={20} aria-hidden="true" /><div><h3>Protect customer data</h3><p>Use synthetic or explicitly authorized content. AI providers may retain inputs; never include passwords, API keys or sensitive personal data.</p></div></li>
                  </ul>
                  <Dialog.Close className="button">Back to work</Dialog.Close>
                </Dialog.Popup>
              </Dialog.Portal>
            </Dialog.Root>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          {accountError && <p className="notice notice-error" role="alert">{accountError}</p>}
          <Routes>
            <Route path="/" element={<Navigate to="/tickets" replace />} />
            <Route path="/tickets" element={<TicketsPage />} />
            <Route path="/tickets/new" element={<TicketCreatePage />} />
            <Route path="/tickets/:id" element={<TicketsPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/mailbox" element={<MailboxPage />} />
            <Route path="/automation" element={<AutomationPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </main>
        <footer className="app-footer"><span><ShieldCheck size={13} aria-hidden="true" />AI assists. You decide.</span><span>Private notes stay internal.</span></footer>
      </div>
    </div>
  );
}

function NotFoundPage() {
  return <section className="not-found"><span className="not-found-code">404</span><h1>This page isn't here.</h1><p>Return to the workspace to pick up where you left off.</p><Link className="button" to="/tickets"><ArrowLeft size={16} aria-hidden="true" />Back to tickets</Link></section>;
}
