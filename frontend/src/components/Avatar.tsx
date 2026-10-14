export function Avatar({ name, size = 'sm', className = '' }: {
  name: string;
  size?: 'sm' | 'md';
  className?: string;
}) {
  const parts = name.trim().split(/\s+/);
  const initials = `${parts[0]?.[0] ?? ''}${parts.length > 1 ? parts[parts.length - 1]?.[0] ?? '' : ''}`.toLocaleUpperCase();
  const tone = (name.codePointAt(0) ?? 0) % 4;
  return <span className={`avatar avatar-${size} avatar-tone-${tone} ${className}`} aria-hidden="true">{initials}</span>;
}
