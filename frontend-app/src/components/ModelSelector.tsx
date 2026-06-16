import { useEffect, useState } from 'react';
import { fetchModels, type AIModel } from '../api/agregador';
import { MODEL_DESCRIPTIONS } from '../lib/modelDescriptions';
import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  selected: string[];
  onChange: (ids: string[]) => void;
  max?: number;
  locked?: boolean;
  webSearch?: Record<string, boolean>;
  onWebSearchChange?: (modelId: string, enabled: boolean) => void;
}

const PERPLEXITY_PREFIX = 'sonar';

export function ModelSelector({ selected, onChange, max = 4, locked = false, webSearch = {}, onWebSearchChange }: Props) {
  const isMobile = useIsMobile();
  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchModels()
      .then(setModels)
      .catch(() => setModels([]))
      .finally(() => setLoading(false));
  }, []);

  function toggle(id: string) {
    if (locked) return;
    if (selected.includes(id)) {
      onChange(selected.filter(s => s !== id));
    } else if (selected.length < max) {
      onChange([...selected, id]);
    }
  }

  function toggleWebSearch(e: React.MouseEvent, modelId: string) {
    e.stopPropagation();
    if (locked) return;
    onWebSearchChange?.(modelId, !webSearch[modelId]);
  }

  if (loading) return (
    <div style={{ padding: isMobile ? '12px 20px' : '12px 40px', fontSize: 12, color: 'var(--pen3)' }}>
      Carregando modelos…
    </div>
  );

  const available = models.filter(m => m.available);

  return (
    <div style={{
      padding: isMobile ? '10px 20px 4px' : '10px 40px 4px',
      borderBottom: '1px solid var(--line2)',
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
    }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--pen3)', marginRight: 4 }}>
        MODELOS
      </span>
      {available.map(m => {
        const active = selected.includes(m.model_id);
        const info = MODEL_DESCRIPTIONS[m.model_id];
        const atMax = selected.length >= max && !active;
        const isPerplexity = m.model_id.includes(PERPLEXITY_PREFIX) || m.provider?.toLowerCase() === 'perplexity';
        const wsActive = !!webSearch[m.model_id];
        let tooltipText: string | undefined;
        if (locked) tooltipText = 'Para trocar de modelo, inicie uma nova consulta';
        else if (atMax) tooltipText = `Máximo ${max} modelo${max > 1 ? 's' : ''}`;
        else if (info) tooltipText = info.shortDescription;
        return (
          <div key={m.model_id} style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <button
              onClick={() => toggle(m.model_id)}
              title={tooltipText}
              style={{
                padding: '4px 10px', borderRadius: active && !isPerplexity ? '999px 0 0 999px' : 999,
                fontSize: 11, fontWeight: 600,
                border: `1px solid ${active ? 'transparent' : 'var(--line2)'}`,
                borderRight: active && !isPerplexity ? 'none' : undefined,
                background: active ? 'var(--mint)' : '#fff',
                color: active ? 'var(--petrol)' : 'var(--pen2)',
                cursor: locked || atMax ? 'not-allowed' : 'pointer',
                opacity: !locked && atMax ? 0.45 : 1,
                transition: 'background 0.12s, color 0.12s',
              }}
            >
              {m.display_name}
            </button>
            {active && !isPerplexity && (
              <button
                onClick={(e) => toggleWebSearch(e, m.model_id)}
                title={wsActive ? 'Desativar busca web' : 'Ativar busca web'}
                style={{
                  padding: '4px 7px', borderRadius: '0 999px 999px 0',
                  fontSize: 11,
                  border: `1px solid transparent`,
                  borderLeft: `1px solid ${wsActive ? 'rgba(1,71,81,0.2)' : 'rgba(1,71,81,0.15)'}`,
                  background: wsActive ? 'var(--petrol)' : 'var(--mint)',
                  color: wsActive ? '#fff' : 'var(--petrol)',
                  cursor: locked ? 'not-allowed' : 'pointer',
                  transition: 'background 0.12s, color 0.12s',
                  lineHeight: 1,
                }}
              >
                🌐
              </button>
            )}
          </div>
        );
      })}
      {locked ? (
        <span style={{ fontSize: 10.5, color: 'var(--pen3)', marginLeft: 4, fontStyle: 'italic' }}>
          Para trocar de modelo, inicie uma nova consulta
        </span>
      ) : selected.length > 0 && (
        <span style={{ fontSize: 10.5, color: 'var(--pen3)', marginLeft: 4 }}>
          {selected.length}/4 selecionados
        </span>
      )}
    </div>
  );
}
