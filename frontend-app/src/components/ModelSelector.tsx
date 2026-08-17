import { useQuery } from '@tanstack/react-query';
import { fetchModels, type AIModel } from '../api/agregador';
import { MODEL_DESCRIPTIONS } from '../lib/modelDescriptions';
import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  selected: string[];
  onChange: (ids: string[]) => void;
  max?: number;
  locked?: boolean;
  hasImageAttached?: boolean;
}


export function ModelSelector({ selected, onChange, max = 4, locked = false, hasImageAttached = false }: Props) {
  const isMobile = useIsMobile();
  const { data: models = [], isLoading: loading } = useQuery<AIModel[]>({
    queryKey: ['agregador-models'],
    queryFn: fetchModels,
    staleTime: 5 * 60_000,
  });

  function toggle(id: string) {
    if (locked) return;
    if (selected.includes(id)) {
      onChange(selected.filter(s => s !== id));
    } else if (selected.length < max) {
      onChange([...selected, id]);
    }
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
        const noVision = hasImageAttached && !m.supports_vision;
        let tooltipText: string | undefined;
        if (locked) tooltipText = 'Para trocar de modelo, inicie uma nova consulta';
        else if (atMax) tooltipText = `Máximo ${max} modelo${max > 1 ? 's' : ''}`;
        else if (noVision) tooltipText = 'Não suporta visão — usará descrição automática da imagem';
        else if (info) tooltipText = info.shortDescription;
        return (
          <button
            key={m.model_id}
            onClick={() => toggle(m.model_id)}
            title={tooltipText}
            style={{
              padding: '4px 10px', borderRadius: 999,
              fontSize: 11, fontWeight: 600,
              border: `1px solid ${active ? 'transparent' : noVision ? '#f59e0b' : 'var(--line2)'}`,
              background: active ? 'var(--mint)' : '#fff',
              color: active ? 'var(--petrol)' : noVision ? '#b45309' : 'var(--pen2)',
              cursor: locked || atMax ? 'not-allowed' : 'pointer',
              opacity: !locked && atMax ? 0.45 : 1,
              transition: 'background 0.12s, color 0.12s',
            }}
          >
            {noVision ? '📝 ' : ''}{m.display_name}
          </button>
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
      {hasImageAttached && selected.some(id => {
        const m = available.find(x => x.model_id === id);
        return m && !m.supports_vision;
      }) && (
        <div style={{
          width: '100%', marginTop: 6,
          padding: '5px 10px', borderRadius: 8,
          background: '#fffbeb', border: '1px solid #fde68a',
          fontSize: 11, color: '#92400e', display: 'flex', alignItems: 'center', gap: 6,
        }}>
          📝 Perplexity não suporta visão — analisará uma descrição automática da imagem gerada por IA, não os pixels reais.
        </div>
      )}
    </div>
  );
}
