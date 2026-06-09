const suggestions = [
  { icon: 'raciocinio', title: 'Raciocínio clínico', desc: 'Descreva o caso e receba diferenciais, hipóteses e sugestão de conduta — o modo é ativado automaticamente.' },
  { icon: 'farmaco',    title: 'Checagem farmacológica', desc: 'Informe os medicamentos do paciente e tire dúvidas de interações, ajustes de dose e contraindicações.' },
  { icon: 'busca',      title: 'Busca rápida', desc: 'Pergunte posologias, critérios diagnósticos ou referências — resposta direta, sem elaboração.' },
  { icon: 'produtividade', title: 'Produtividade', desc: 'Peça laudos, receitas, encaminhamentos ou resumos de consulta e receba o texto pronto para usar.' },
];

import type { ReactElement } from 'react';

const icons: Record<string, ReactElement> = {
  raciocinio: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M8 1.5 C5 1.5 3.5 3.5 3.5 5.5 C3.5 7 2 7.5 2 9 C2 10.5 3.5 11 3.5 12.5 L3.5 14 L12.5 14 L12.5 12.5 C12.5 11 14 10.5 14 9 C14 7.5 12.5 7 12.5 5.5 C12.5 3.5 11 1.5 8 1.5 Z"
            stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" fill="none" />
    </svg>
  ),
  farmaco: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="5" width="12" height="6" rx="3" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 5 V11" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  ),
  busca: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10.5 10.5 L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  produtividade: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2.5" y="3" width="11" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5 6 H11 M5 8.5 H11 M5 11 H8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
};

function greeting(name: string | null): string {
  const hour = new Date().getHours();
  const period = hour < 12 ? 'Bom dia' : hour < 18 ? 'Boa tarde' : 'Boa noite';
  return name ? `${period}, ${name}.` : `${period}.`;
}

interface Props {
  userName?: string | null;
}

export function EmptyState({ userName }: Props) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 40px' }}>
      <div style={{ width: 720, maxWidth: '100%' }}>
        <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--ink)', letterSpacing: -0.5 }}>
          {greeting(userName ?? null)}
        </div>
        <div style={{ fontSize: 15, color: 'var(--pen2)', marginTop: 6, marginBottom: 28 }}>
          Os cards abaixo mostram o que cada modo faz — basta perguntar em texto livre que eu identifico o modo certo.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {suggestions.map(s => (
            <div
              key={s.icon}
              style={{
                border: '1px solid var(--line2)', borderRadius: 10, padding: '12px 14px',
                background: '#fff', textAlign: 'left',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--petrol)', marginBottom: 6 }}>
                {icons[s.icon]}
                <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.8 }}>
                  {s.title}
                </span>
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--pen)', lineHeight: 1.45 }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
