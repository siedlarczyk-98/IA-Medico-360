import { useEffect, useState } from 'react';
import { fetchModels, type AIModel } from '../api/agregador';

interface Props {
  selected: string[];
  onChange: (ids: string[]) => void;
  max?: number;
}

export function ModelSelector({ selected, onChange, max = 4 }: Props) {
  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchModels()
      .then(setModels)
      .catch(() => setModels([]))
      .finally(() => setLoading(false));
  }, []);

  function toggle(id: string) {
    if (selected.includes(id)) {
      onChange(selected.filter(s => s !== id));
    } else if (selected.length < max) {
      onChange([...selected, id]);
    }
  }

  if (loading) return (
    <div style={{ padding: '12px 40px', fontSize: 12, color: 'var(--pen3)' }}>
      Carregando modelos…
    </div>
  );

  const available = models.filter(m => m.available);

  return (
    <div style={{
      padding: '10px 40px 4px',
      borderBottom: '1px solid var(--line2)',
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
    }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--pen3)', marginRight: 4 }}>
        MODELOS
      </span>
      {available.map(m => {
        const active = selected.includes(m.model_id);
        return (
          <button
            key={m.model_id}
            onClick={() => toggle(m.model_id)}
            title={selected.length >= max && !active ? `Máximo ${max} modelo${max > 1 ? 's' : ''}` : undefined}
            style={{
              padding: '4px 10px', borderRadius: 999, fontSize: 11, fontWeight: 600,
              border: `1px solid ${active ? 'transparent' : 'var(--line2)'}`,
              background: active ? 'var(--mint)' : '#fff',
              color: active ? 'var(--petrol)' : 'var(--pen2)',
              cursor: selected.length >= max && !active ? 'not-allowed' : 'pointer',
              opacity: selected.length >= max && !active ? 0.45 : 1,
              transition: 'background 0.12s, color 0.12s',
            }}
          >
            {m.display_name}
          </button>
        );
      })}
      {selected.length > 0 && (
        <span style={{ fontSize: 10.5, color: 'var(--pen3)', marginLeft: 4 }}>
          {selected.length}/4 selecionados
        </span>
      )}
    </div>
  );
}
