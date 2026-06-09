import { useEffect, useState } from 'react';
import { fetchModels, type AIModel } from '../api/agregador';
import { MODEL_DESCRIPTIONS, type AIModelInfo } from '../lib/modelDescriptions';

interface Props {
  selected: string[];
  onChange: (ids: string[]) => void;
}

export function EmptyStateAgregador({ selected, onChange }: Props) {
  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchModels()
      .then(m => setModels(m.filter(x => x.available && x.model_id !== 'gemini-3-flash')))
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

  function getModelInfo(modelId: string): AIModelInfo {
    return MODEL_DESCRIPTIONS[modelId] || {
      icon: '🤖',
      shortDescription: '',
      tags: [],
      idealFor: [],
    };
  }

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '0 40px',
    }}>
      <div style={{ width: 900, maxWidth: '100%' }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', letterSpacing: -0.4 }}>
          Selecione a IA ideal para sua tarefa
        </div>
        <div style={{ fontSize: 14, color: 'var(--pen2)', marginTop: 6, marginBottom: 28 }}>
          Escolha o modelo que melhor se adapta ao seu caso de uso.
        </div>

        {loading ? (
          <div style={{ fontSize: 12, color: 'var(--pen3)' }}>Carregando modelos…</div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
            gap: 14,
          }}>
            {models.map(m => {
              const active = selected.includes(m.model_id);
              const info = getModelInfo(m.model_id);
              return (
                <button
                  key={m.model_id}
                  onClick={() => toggle(m.model_id)}
                  style={{
                    border: `1.5px solid ${active ? 'var(--mint)' : 'var(--line2)'}`,
                    borderRadius: 14,
                    padding: '18px 18px',
                    background: active ? 'rgba(0,209,125,0.08)' : '#fff',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.18s ease',
                    boxShadow: active ? '0 4px 12px rgba(0,209,125,0.18)' : '0 1px 3px rgba(0,0,0,0.08)',
                    position: 'relative',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                  }}
                  onMouseEnter={e => {
                    if (!active) {
                      (e.currentTarget as HTMLElement).style.borderColor = 'var(--petrol)';
                      (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 12px rgba(0,68,77,0.12)';
                    }
                  }}
                  onMouseLeave={e => {
                    if (!active) {
                      (e.currentTarget as HTMLElement).style.borderColor = 'var(--line2)';
                      (e.currentTarget as HTMLElement).style.boxShadow = '0 1px 3px rgba(0,0,0,0.08)';
                    }
                  }}
                >
                  {/* Checkmark para seleção */}
                  {active && (
                    <div style={{
                      position: 'absolute', top: 12, right: 12,
                      width: 20, height: 20, borderRadius: '50%',
                      background: 'var(--mint)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      color: '#fff',
                      fontWeight: 700,
                    }}>
                      ✓
                    </div>
                  )}

                  {/* Header: Icon + Title */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                  }}>
                    <div style={{
                      fontSize: 28,
                      flexShrink: 0,
                    }}>
                      {info.icon}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{
                        fontSize: 13, fontWeight: 700,
                        color: active ? 'var(--petrol)' : 'var(--ink)',
                        marginBottom: 4,
                      }}>
                        {m.display_name}
                      </div>
                      {/* Tags/Badges */}
                      {info.tags.length > 0 && (
                        <div style={{
                          display: 'flex',
                          gap: 5,
                          flexWrap: 'wrap',
                          marginTop: 4,
                        }}>
                          {info.tags.map((tag, idx) => (
                            <span
                              key={idx}
                              style={{
                                fontSize: 10,
                                fontWeight: 600,
                                padding: '2px 7px',
                                borderRadius: 4,
                                background: active ? 'rgba(0,68,77,0.1)' : 'rgba(0,0,0,0.05)',
                                color: active ? 'var(--petrol)' : 'var(--pen3)',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Short Description */}
                  {info.shortDescription && (
                    <div style={{
                      fontSize: 12,
                      color: 'var(--pen2)',
                      lineHeight: 1.4,
                    }}>
                      {info.shortDescription}
                    </div>
                  )}

                  {/* Ideal For Section */}
                  {info.idealFor.length > 0 && (
                    <div style={{ marginTop: 4 }}>
                      <div style={{
                        fontSize: 10.5,
                        fontWeight: 600,
                        color: 'var(--pen3)',
                        marginBottom: 5,
                        textTransform: 'uppercase',
                        letterSpacing: 0.3,
                      }}>
                        Ideal para:
                      </div>
                      <ul style={{
                        margin: 0,
                        padding: 0,
                        listStyle: 'none',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 3,
                      }}>
                        {info.idealFor.map((item, idx) => (
                          <li
                            key={idx}
                            style={{
                              fontSize: 11,
                              color: 'var(--pen2)',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 6,
                            }}
                          >
                            <span style={{
                              display: 'inline-block',
                              width: 4,
                              height: 4,
                              borderRadius: '50%',
                              background: active ? 'var(--mint)' : 'var(--pen3)',
                              flexShrink: 0,
                            }} />
                            {item}
                          </li>
                        ))}
                      </ul>
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
