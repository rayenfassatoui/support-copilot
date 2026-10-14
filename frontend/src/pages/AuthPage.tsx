import { useState, type FormEvent } from 'react';
import { ArrowRight, LockKeyhole, Mail, ShieldCheck } from 'lucide-react';
import { useAuth } from '../auth';
import { getAuthClient } from '../auth-client';
import './workspace.css';

type AuthMode = 'signin' | 'signup' | 'verify' | 'forgot' | 'reset';
const titles: Record<AuthMode, string> = { signin: 'Welcome back.', signup: 'Create your account.', verify: 'Check your inbox.', forgot: 'Reset your password.', reset: 'Choose a new password.' };

export function AuthPage() {
  const auth = useAuth();
  const [mode, setMode] = useState<AuthMode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [otp, setOtp] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  function changeMode(next: AuthMode) { setMode(next); setError(''); setNotice(''); setPassword(''); setOtp(''); }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true); setError(''); setNotice('');
    try {
      const client = await getAuthClient();
      const address = email.trim();
      if (mode === 'signup') {
        const result = await client.signUp.email({ name: name.trim(), email: address, password });
        if (result.error) throw new Error(result.error.message ?? 'Account creation failed.');
        setPassword(''); setMode('verify'); setNotice('Enter the verification code sent to your email. Workspace access requires administrator authorization.');
      } else if (mode === 'signin') {
        const result = await client.signIn.email({ email: address, password });
        if (result.error) {
          if (result.error.code === 'EMAIL_NOT_VERIFIED') { setMode('verify'); setNotice('Verify your email to continue. You can request a new code below.'); return; }
          throw new Error(result.error.message ?? 'Sign-in failed.');
        }
        setPassword(''); await auth.refresh();
      } else if (mode === 'verify') {
        const result = await client.emailOtp.verifyEmail({ email: address, otp: otp.trim() });
        if (result.error) throw new Error(result.error.message ?? 'Verification failed.');
        setOtp(''); setMode('signin'); setNotice('Email verified. Sign in to your workspace.'); await auth.refresh();
      } else if (mode === 'forgot') {
        const result = await client.emailOtp.requestPasswordReset({ email: address });
        if (result.error) throw new Error(result.error.message ?? 'Could not request a reset code.');
        setMode('reset'); setNotice('If this account exists, a reset code has been sent.');
      } else {
        const result = await client.emailOtp.resetPassword({ email: address, otp: otp.trim(), password });
        if (result.error) throw new Error(result.error.message ?? 'Password reset failed.');
        setPassword(''); setOtp(''); setMode('signin'); setNotice('Password updated. Sign in with your new password.');
      }
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Authentication could not be completed.'); }
    finally { setPending(false); }
  }
  async function resend() {
    if (pending || !email.trim()) return;
    setPending(true); setError('');
    try {
      const client = await getAuthClient();
      const result = await client.emailOtp.sendVerificationOtp({ email: email.trim(), type: 'email-verification' });
      if (result.error) throw new Error(result.error.message ?? 'Could not send the code.');
      setNotice('A new verification code has been requested.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not send the code.'); }
    finally { setPending(false); }
  }

  return <main className="auth-layout">
    <div className="auth-introduction"><div className="brand"><span className="brand-mark" aria-hidden="true"><span /><span /><span /></span><span>Support<span className="brand-secondary">Copilot</span></span></div><h1>Good support starts<br />with a clear workspace.</h1><p>Requests, evidence and thoughtful replies.<br />Your team stays in control.</p><div className="auth-assurance"><ShieldCheck size={18} aria-hidden="true" />Authenticated team access · Human-reviewed AI</div></div>
    <section className="panel auth-card" aria-labelledby="auth-heading">
      <span className="auth-symbol" aria-hidden="true"><LockKeyhole size={23} /></span>
      {auth.email ? <>
        <h2 id="auth-heading">Workspace access</h2><p className="muted">Signed in as <strong>{auth.email}</strong></p>
        {auth.error && <p className="notice notice-error" role="alert">{auth.error}</p>}
        <p>An administrator must authorize your verified email before you can view customer requests.</p>
        <div className="form-actions"><button className="button" onClick={() => { void auth.refresh(); }}>Check access again</button><button className="button button-secondary" onClick={() => { void auth.signOut().catch(failure => setError(failure.message)); }}>Use another account</button></div>
        {error && <p role="alert" className="notice notice-error">{error}</p>}
      </> : <>
        <h2 id="auth-heading">{titles[mode]}</h2><p className="muted">{mode === 'signin' ? 'Sign in to your support workspace.' : mode === 'signup' ? 'Use the email authorized by your administrator.' : 'Authentication emails are delivered by Neon Auth.'}</p>
        {(error || auth.error) && <p className="notice notice-error" role="alert">{error || auth.error}</p>}
        {notice && <p className="notice notice-success" role="status">{notice}</p>}
        <form onSubmit={submit}>
          <fieldset className="form-fields" disabled={pending}><legend className="sr-only">Account details</legend>
            {mode === 'signup' && <div className="field"><label htmlFor="auth-name">Full name</label><input id="auth-name" value={name} onChange={event => setName(event.target.value)} required maxLength={200} autoComplete="name" /></div>}
            <div className="field"><label htmlFor="auth-email">Email address</label><input id="auth-email" type="email" value={email} onChange={event => setEmail(event.target.value)} required autoComplete="email" spellCheck={false} /></div>
            {(mode === 'verify' || mode === 'reset') && <div className="field"><label htmlFor="auth-code">Email code</label><input id="auth-code" value={otp} onChange={event => setOtp(event.target.value)} required inputMode="numeric" autoComplete="one-time-code" maxLength={10} /></div>}
            {(mode === 'signin' || mode === 'signup' || mode === 'reset') && <div className="field"><label htmlFor="auth-password">{mode === 'reset' ? 'New password' : 'Password'}</label><input id="auth-password" type="password" value={password} onChange={event => setPassword(event.target.value)} required minLength={mode === 'signin' ? undefined : 12} maxLength={128} autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} />{mode !== 'signin' && <p className="field-help">At least 12 characters.</p>}</div>}
            <button type="submit" className="button auth-submit">{pending ? 'Please wait…' : mode === 'signin' ? 'Sign in' : mode === 'signup' ? 'Create account' : mode === 'verify' ? 'Verify email' : mode === 'forgot' ? 'Send reset code' : 'Update password'}<ArrowRight size={16} aria-hidden="true" /></button>
          </fieldset>
        </form>
        <div className="auth-links">
          {mode === 'signin' ? <><button className="button button-quiet" disabled={pending} onClick={() => changeMode('signup')}>Create account</button><button className="button button-quiet" disabled={pending} onClick={() => changeMode('forgot')}>Forgot password?</button></> : <button className="button button-quiet" disabled={pending} onClick={() => changeMode('signin')}>Back to sign in</button>}
          {mode === 'verify' && <button className="button button-quiet" disabled={pending || !email.trim()} onClick={() => { void resend(); }}><Mail size={15} aria-hidden="true" />Send another code</button>}
        </div>
        {auth.error && <button className="button button-secondary" disabled={pending} onClick={() => { void auth.refresh(); }}>Retry connection</button>}
      </>}
    </section>
  </main>;
}
