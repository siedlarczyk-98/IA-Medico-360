import type { ReactNode } from 'react';

interface SpecialtyStyle {
  label: string;
  color: string;
  bg: string;
  icon: ReactNode;
}

const HEART = (color: string) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <path d="M12 21s-7.5-4.9-10-9.6C0.3 8 1.9 4 5.6 3.2 8 2.7 10.4 4 12 6.3 13.6 4 16 2.7 18.4 3.2 22.1 4 23.7 8 22 11.4 19.5 16.1 12 21 12 21z" stroke={color} strokeWidth="1.7" strokeLinejoin="round" />
  </svg>
);

const DROP = (color: string) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <path d="M12 2s7 8.2 7 13a7 7 0 11-14 0c0-4.8 7-13 7-13z" stroke={color} strokeWidth="1.7" strokeLinejoin="round" />
  </svg>
);

const VIRUS = (color: string) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="4.5" stroke={color} strokeWidth="1.7" />
    <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.5 5.5l2 2M16.5 16.5l2 2M18.5 5.5l-2 2M7.5 16.5l-2 2" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
  </svg>
);

const PULSE = (color: string) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <path d="M2 12h4l2-7 4 14 3-9 1.5 2H22" stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const SPECIALTY_MAP: Record<string, SpecialtyStyle> = {
  cardiologia: { label: 'Cardiologia', color: '#b23a48', bg: '#fbeaec', icon: HEART('#b23a48') },
  nefrologia: { label: 'Nefrologia', color: '#1f6f9c', bg: '#e9f3f9', icon: DROP('#1f6f9c') },
  infectologia: { label: 'Infectologia', color: '#00845a', bg: '#e4f7ee', icon: VIRUS('#00845a') },
};

const DEFAULT_STYLE: Omit<SpecialtyStyle, 'label' | 'icon'> = {
  color: '#014751',
  bg: '#f5f7f6',
};

export function getSpecialtyStyle(slug: string): SpecialtyStyle {
  const known = SPECIALTY_MAP[slug];
  if (known) return known;
  return {
    label: slug,
    color: DEFAULT_STYLE.color,
    bg: DEFAULT_STYLE.bg,
    icon: PULSE(DEFAULT_STYLE.color),
  };
}
