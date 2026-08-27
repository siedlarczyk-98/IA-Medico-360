import type { ReactElement } from 'react';
import { useIsMobile } from '../hooks/useIsMobile';
import type { OrchestratorMode } from './InputBar';

const suggestions: { icon: string; key: OrchestratorMode; title: string; desc: string }[] = [
  { icon: 'busca',         key: 'QUICK_SEARCH',       title: 'Busca rápida',            desc: 'Pergunte qualquer coisa — posologia, protocolo, critério diagnóstico. Resposta direta, sem elaboração.' },
  { icon: 'raciocinio',   key: 'CLINICAL_REASONING', title: 'Raciocínio clínico',      desc: 'Descreva o caso e receba hipóteses, exames e conduta validados em diretrizes.' },
  { icon: 'farmaco',      key: 'PHARMA_CHECK',       title: 'Checagem farmacológica',  desc: 'Interações, bulas, receituário e genéricos — dados oficiais vindos da ANVISA em tempo real.' },
  { icon: 'produtividade', key: 'PRODUCTIVITY',       title: 'Produtividade',           desc: 'Laudos, emails, receitas, resumos e qualquer tarefa administrativa — sem restrições clínicas.' },
  { icon: 'exames',       key: 'EXAM_REVIEW',        title: 'Exames',                  desc: 'Anexe laudo, imagem ou resultado laboratorial e discuta os achados — até 5 arquivos por mensagem.' },
];

const icons: Record<string, ReactElement> = {
  exames: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2.5" y="2" width="11" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="8" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5 11.5 H11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),

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
  selectedMode?: OrchestratorMode;
  onModeSelect?: (mode: OrchestratorMode) => void;
}

export function EmptyState({ userName, selectedMode, onModeSelect }: Props) {
  const isMobile = useIsMobile();
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: isMobile ? '0 20px' : '0 40px' }}>
      <div style={{ width: 720, maxWidth: '100%' }}>
        <div style={{ fontSize: isMobile ? 22 : 28, fontWeight: 700, color: 'var(--ink)', letterSpacing: -0.5 }}>
          {greeting(userName ?? null)}
        </div>
        <div style={{ fontSize: 14, color: 'var(--pen2)', marginTop: 6, marginBottom: 28 }}>
          Selecione o modo abaixo e faça sua pergunta.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 10 }}>
          {suggestions.map(s => {
            const active = selectedMode === s.key;
            return (
              <button
                key={s.icon}
                onClick={() => onModeSelect?.(s.key)}
                style={{
                  border: `1.5px solid ${active ? 'var(--petrol)' : 'var(--line2)'}`,
                  borderRadius: 10, padding: '12px 14px',
                  background: active ? 'var(--mint)' : '#fff',
                  textAlign: 'left', cursor: 'pointer',
                  transition: 'border-color 0.15s, background 0.15s',
                  outline: 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--petrol)', marginBottom: 6 }}>
                  {icons[s.icon]}
                  <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.8 }}>
                    {s.title}
                  </span>
                  {active && (
                    <span style={{ marginLeft: 'auto', fontSize: 10, fontWeight: 700, color: 'var(--petrol)', background: 'rgba(1,71,81,0.1)', borderRadius: 4, padding: '2px 6px' }}>
                      selecionado
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--pen)', lineHeight: 1.45 }}>{s.desc}</div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
