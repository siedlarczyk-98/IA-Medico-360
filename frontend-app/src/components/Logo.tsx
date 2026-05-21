export function Logo() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
        <path
          d="M3 26 L3 10 Q3 5 8 5 Q12 5 13 9 L16 22 L19 9 Q20 5 24 5 Q29 5 29 10 L29 26"
          stroke="#0e252d" strokeWidth="3.4" fill="none" strokeLinecap="round" strokeLinejoin="round"
        />
        <circle cx="8" cy="13" r="1.6" fill="#00d17d" />
      </svg>
      <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: -0.2, color: 'var(--ink)' }}>
        Médico<span style={{ color: 'var(--green)', fontWeight: 600 }}>360</span>
      </span>
    </div>
  );
}
