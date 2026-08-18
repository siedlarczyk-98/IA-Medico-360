interface IconProps {
  size?: number;
  color?: string;
}

export function IconShieldAlert({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 3l7 3v6c0 4.5-2.9 8.2-7 9-4.1-.8-7-4.5-7-9V6l7-3z" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M12 8v5" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="16" r="0.9" fill={color} />
    </svg>
  );
}

export function IconAlertTriangle({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 4l9.5 16H2.5L12 4z" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M12 10v4" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="17" r="0.9" fill={color} />
    </svg>
  );
}

export function IconHeartPulse({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M20 8.5c0-2.5-2-4.5-4.5-4.5-1.6 0-3 .8-3.5 2-0.5-1.2-1.9-2-3.5-2C6 4 4 6 4 8.5c0 4 4.5 7 8 10 3.5-3 8-6 8-10z" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M5 12h3l1.5-3 2 5 1.5-3H18" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconStethoscope({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M6 4v6a4 4 0 008 0V4" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
      <path d="M14 12v2a5 5 0 01-10 0v-3" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="18" cy="16" r="2.5" stroke={color} strokeWidth="1.7" />
      <path d="M4 4h0M8 4h0" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconUser({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8" r="3.5" stroke={color} strokeWidth="1.7" />
      <path d="M4.5 20c1.4-3.6 4.3-5.5 7.5-5.5s6.1 1.9 7.5 5.5" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconTrendingUp({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M4 16l6-6 4 4 6-7" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15 7h5v5" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconTrendingDown({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M4 8l6 6 4-4 6 7" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15 17h5v-5" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconTarget({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="8" stroke={color} strokeWidth="1.7" />
      <circle cx="12" cy="12" r="4.5" stroke={color} strokeWidth="1.7" />
      <circle cx="12" cy="12" r="1" fill={color} />
    </svg>
  );
}

export function IconPill({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="4" y="10" width="16" height="7" rx="3.5" transform="rotate(-35 12 13.5)" stroke={color} strokeWidth="1.7" />
      <path d="M9.5 12.5l3.5 3.5" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconChevronRight({ size = 16, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M9 5l7 7-7 7" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconRestart({ size = 16, color = 'currentColor' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M4 12a8 8 0 1 1 2.6 5.9" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M4 17v-4h4" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
