import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { AlreadyRequestedError, requestCalculators } from '../api/calculators';

interface RequestCalculatorModalProps {
  open: boolean;
  onClose: () => void;
}

export function RequestCalculatorModal({ open, onClose }: RequestCalculatorModalProps) {
  const [items, setItems] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [notify, setNotify] = useState(true);

  const mutation = useMutation({
    mutationFn: (calculators: string[]) => requestCalculators(calculators, notify),
  });

  if (!open) return null;

  function addDraft() {
    const value = draft.trim();
    if (!value) return;
    if (!items.includes(value)) setItems(prev => [...prev, value]);
    setDraft('');
  }

  function removeItem(value: string) {
    setItems(prev => prev.filter(i => i !== value));
  }

  function handleClose() {
    mutation.reset();
    setItems([]);
    setDraft('');
    setNotify(true);
    onClose();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    addDraft();
    const finalItems = draft.trim() && !items.includes(draft.trim()) ? [...items, draft.trim()] : items;
    if (finalItems.length === 0) return;
    mutation.mutate(finalItems);
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(14,37,45,0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
      onClick={handleClose}
    >
      <div
        style={{
          background: '#fff', borderRadius: 16,
          width: '100%', maxWidth: 480,
          maxHeight: '85vh', overflowY: 'auto',
          padding: '24px',
          boxShadow: '0 12px 40px rgba(14,37,45,0.18)',
          display: 'flex', flexDirection: 'column', gap: 16,
        }}
        onClick={e => e.stopPropagation()}
      >
        {mutation.isSuccess ? (
          <>
            <h3 style={{ fontSize: 17, fontWeight: 800, color: 'var(--ink)' }}>Pedido registrado</h3>
            <p style={{ fontSize: 13, color: 'var(--pen2)' }}>
              Obrigado! Sua sugestão entra na priorização das próximas calculadoras.
            </p>
            <button type="button" onClick={handleClose} style={closeBtnStyle}>Fechar</button>
          </>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <h3 style={{ fontSize: 17, fontWeight: 800, color: 'var(--ink)' }}>Solicitar calculadora</h3>
              <p style={{ fontSize: 13, color: 'var(--pen2)', marginTop: 4 }}>
                Qual calculadora clínica você gostaria de ver aqui? Digite o nome e adicione quantas quiser.
              </p>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addDraft();
                  }
                }}
                placeholder="Ex: Escore de Wells, MELD, Glasgow..."
                style={{
                  flex: 1,
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: '1px solid var(--line)',
                  fontSize: 13,
                  color: 'var(--ink)',
                  outline: 'none',
                }}
              />
              <button type="button" onClick={addDraft} style={addBtnStyle}>Adicionar</button>
            </div>

            {items.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {items.map(item => (
                  <span key={item} style={chipStyle}>
                    {item}
                    <button
                      type="button"
                      onClick={() => removeItem(item)}
                      aria-label={`Remover ${item}`}
                      style={chipRemoveStyle}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}

            <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={notify}
                onChange={e => setNotify(e.target.checked)}
                style={{ marginTop: 2, accentColor: 'var(--petrol)' }}
              />
              <span style={{ fontSize: 12, color: 'var(--pen2)' }}>
                Quero ser comunicado quando essa calculadora estiver disponível
              </span>
            </label>

            {mutation.isError && (
              <p style={{ fontSize: 12, color: 'var(--red)' }}>
                {mutation.error instanceof AlreadyRequestedError
                  ? mutation.error.message
                  : 'Não foi possível registrar agora. Tente novamente.'}
              </p>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" onClick={handleClose} style={cancelBtnStyle}>Cancelar</button>
              <button
                type="submit"
                disabled={mutation.isPending || (items.length === 0 && !draft.trim())}
                style={submitBtnStyle}
              >
                {mutation.isPending ? 'Enviando...' : 'Enviar pedido'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

const addBtnStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid var(--line)',
  background: '#fff',
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--ink)',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};

const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 10px',
  borderRadius: 20,
  background: 'var(--fill2)',
  fontSize: 12,
  color: 'var(--ink)',
};

const chipRemoveStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  fontSize: 14,
  lineHeight: 1,
  color: 'var(--pen3)',
  padding: 0,
};

const cancelBtnStyle: React.CSSProperties = {
  padding: '10px 16px',
  borderRadius: 10,
  border: '1px solid var(--line)',
  background: '#fff',
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--pen2)',
  cursor: 'pointer',
};

const submitBtnStyle: React.CSSProperties = {
  padding: '10px 18px',
  borderRadius: 10,
  border: 'none',
  background: 'var(--petrol)',
  fontSize: 13,
  fontWeight: 700,
  color: '#fff',
  cursor: 'pointer',
};

const closeBtnStyle: React.CSSProperties = {
  alignSelf: 'flex-start',
  padding: '10px 16px',
  borderRadius: 10,
  border: '1px solid var(--line)',
  background: '#fff',
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--ink)',
  cursor: 'pointer',
};
