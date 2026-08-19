import { useState } from 'react';

export function DropZoneNoPasta({ onDrop }: { onDrop: () => void }) {
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={e => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); onDrop(); }}
      style={{
        margin: '0 4px 6px',
        padding: '5px 10px',
        borderRadius: 6,
        border: `1.5px dashed ${over ? 'var(--green)' : 'var(--line2)'}`,
        background: over ? 'var(--fill2)' : 'transparent',
        fontSize: 11,
        color: over ? 'var(--green)' : 'var(--pen3)',
        textAlign: 'center',
        transition: 'all 0.1s',
      }}
    >
      Soltar aqui para remover da pasta
    </div>
  );
}
