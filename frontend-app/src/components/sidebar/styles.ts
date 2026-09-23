/**
 * Itens dos menus de contexto da barra lateral (opções da conversa, da pasta,
 * do perfil).
 *
 * `minHeight` em `--toque-min`: no celular esses menus abrem por toque, e os
 * itens tinham ~30px de altura — o dedo pegava o item de cima ou o de baixo.
 * No mouse o token resolve para 32px, então o desktop não muda de aparência.
 */
export const ctxItemStyle: React.CSSProperties = {
  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
  minHeight: 'var(--toque-min)',
  padding: '0 12px', background: 'none', border: 'none',
  fontSize: 'var(--texto-apoio)', color: 'var(--ink)', cursor: 'pointer', textAlign: 'left',
};

export const menuItemStyle: React.CSSProperties = {
  width: '100%', display: 'flex', alignItems: 'center', gap: 9,
  minHeight: 'var(--toque-min)',
  padding: '0 14px', background: 'none', border: 'none',
  fontSize: 'var(--texto-apoio)', color: 'var(--ink)', cursor: 'pointer', textAlign: 'left',
};
