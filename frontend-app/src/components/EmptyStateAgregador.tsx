import { useEffect, useState } from 'react';
import { fetchModels, type AIModel } from '../api/agregador';
import { MODEL_DESCRIPTIONS } from '../lib/modelDescriptions';

interface Props {
  selected: string[];
  onChange: (ids: string[]) => void;
}

export function EmptyStateAgregador({ selected, onChange }: Props) {
  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchModels()
      .then(m => setModels(m.filter(x => x.available)))
      .catch(() => setModels([]))
      .finally(() => setLoading(false));
  }, []);

  function toggle(id: string) {
    if (selected.includes(id)) {
      onChange(selected.filter(s => s !== id));
    } else {
      onChange([id]);
    }
  }

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '0 40px',
    }}>
      <div style={{ width: 720, maxWidth: '100%' }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', letterSpacing: -0.4 }}>
          Selecione a IA ideal para sua tarefa
        </div>
        <div style={{ fontSize: 14, color: 'var(--pen2)', marginTop: 6, marginBottom: 24 }}>
          Selecione um modelo abaixo e faça sua pergunta.
        </div>

        {loading ? (
          <div style={{ fontSize: 12, color: 'var(--pen3)' }}>Carregando modelos…</div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 10,
          }}>
            {models.map(m => {
              const active = selected.includes(m.model_id);
              const desc = MODEL_DESCRIPTIONS[m.model_id];
              return (
                <button
                  key={m.model_id}
                  onClick={() => toggle(m.model_id)}
                  style={{
                    border: `1.5px solid ${active ? 'var(--mint)' : 'var(--line2)'}`,
                    borderRadius: 12,
                    padding: '14px 16px',
                    background: active ? 'rgba(0,209,125,0.06)' : '#fff',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'border-color 0.15s, background 0.15s, box-shadow 0.15s',
                    boxShadow: active ? '0 2px 10px rgba(0,209,125,0.15)' : 'none',
                    position: 'relative',
                  }}
                  onMouseEnter={e => {
                    if (!active) {
                      (e.currentTarget as HTMLElement).style.borderColor = 'var(--petrol)';
                      (e.currentTarget as HTMLElement).style.boxShadow = '0 2px 8px rgba(0,68,77,0.08)';
                    }
                  }}
                  onMouseLeave={e => {
                    if (!active) {
                      (e.currentTarget as HTMLElement).style.borderColor = 'var(--line2)';
                      (e.currentTarget as HTMLElement).style.boxShadow = 'none';
                    }
                  }}
                >
                  {active && (
                    <div style={{
                      position: 'absolute', top: 10, right: 12,
                      width: 8, height: 8, borderRadius: '50%',
                      background: 'var(--mint)',
                    }} />
                  )}
                  <div style={{
                    fontSize: 12.5, fontWeight: 700,
                    color: active ? 'var(--petrol)' : 'var(--ink)',
                    marginBottom: 6,
                  }}>
                    {m.display_name}
                  </div>
                  {desc && (
                    <div style={{
                      fontSize: 11.5, color: 'var(--pen2)', lineHeight: 1.5,
                    }}>
                      {desc}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
