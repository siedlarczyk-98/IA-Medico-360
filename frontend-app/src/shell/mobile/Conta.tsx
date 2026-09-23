/**
 * Conta do médico na casca mobile: perfil, uso da semana, suporte, documentos
 * e (onde faz sentido) sair.
 *
 * Fora da Waid é uma aba (tela cheia); dentro dela, uma folha aberta pelo
 * rodapé da gaveta. O conteúdo é o mesmo.
 *
 * SAIR
 * Some dentro do iframe (site da Waid) e aparece fora dele — a regra de
 * `shared/embed/dentro-do-iframe.ts`: no iframe a identidade vem do handshake a
 * cada abertura, e "sair" não tem efeito real; fora dele (app nativo, URL
 * direta) a sessão pode ter vindo por código de e-mail, e sair é o único jeito
 * de trocar de conta num aparelho compartilhado. O protótipo tirava o Sair do
 * app nativo também; aqui prevaleceu o motivo documentado.
 */

import { useState } from 'react';

import { dentroDoIframe } from '@shared/embed/dentro-do-iframe';
import { DOCUMENTOS } from '@shared/documentos';
import { logout } from '../../lib/auth';
import { abrirSuporte, suporteDisponivel } from '../../lib/intercom';
import { useCurrentUser } from '../../lib/useCurrentUser';
import { useUserUsage } from '../../lib/useUserUsage';
import { ORIGEM_LEGIVEL, usePerfil } from '../../hooks/usePerfil';
import { BottomSheet } from './BottomSheet';
import { Icone } from './Icone';
import { iniciais } from './iniciais';

const DIAS = ['dom.', 'seg.', 'ter.', 'qua.', 'qui.', 'sex.', 'sáb.'];
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

/**
 * "Renova dom., 27/set às 21h". Com a hora: a virada é segunda 00:00 UTC, que
 * no Brasil cai no domingo à noite — sem a hora, "domingo" parecia de manhã.
 */
function renovaEm(d: Date): string {
  return `Renova ${DIAS[d.getDay()]}, ${String(d.getDate()).padStart(2, '0')}/${MESES[d.getMonth()]} às ${d.getHours()}h`;
}

interface Props {
  hospedado: boolean;
  usageTick: number;
  onEditarPerfil: () => void;
}

export function ContaConteudo({ hospedado, usageTick, onEditarPerfil }: Props) {
  const usuario = useCurrentUser();
  const uso = useUserUsage(usageTick);
  // Lido uma vez: o contexto de iframe não muda durante a sessão.
  const [podeSair] = useState(() => !dentroDoIframe());

  return (
    <div className="mv-conta">
      <div className="mv-card">
        <div className="mv-perfil">
          <span className="mv-avatar mv-avatar-g" aria-hidden="true">{iniciais(usuario?.name)}</span>
          <div className="mv-perfil-t">
            <b>{usuario?.name || 'Sua conta'}</b>
            {usuario?.specialty && <span>{usuario.specialty}</span>}
            {usuario?.email && <span className="mv-quebra">{usuario.email}</span>}
          </div>
        </div>
        <button type="button" className="mv-row mv-row-acao" onClick={onEditarPerfil}>
          <Icone n="edit" s={20} />Editar perfil<span className="mv-row-v"><Icone n="chevR" s={18} /></span>
        </button>
      </div>

      {uso.hasLimit && uso.usagePercentage !== null && (
        <div className="mv-card mv-card-pad">
          <div className="mv-uso-topo">
            <span className="mv-sec-l">Uso semanal</span>
            {uso.weekResetAt && <span className="mv-uso-renova">{renovaEm(uso.weekResetAt)}</span>}
          </div>
          <div><b className="mv-uso-n">{Math.round(uso.usagePercentage)}%</b> do limite desta semana</div>
          <div className="mv-barra mv-barra-g" role="progressbar" aria-valuenow={Math.round(uso.usagePercentage)} aria-valuemin={0} aria-valuemax={100} aria-label="Uso semanal">
            <i style={{ width: `${Math.min(100, uso.usagePercentage)}%` }} />
          </div>
        </div>
      )}

      <div className="mv-card">
        {suporteDisponivel() && (
          <button type="button" className="mv-row" onClick={abrirSuporte}>
            <Icone n="help" s={20} />Suporte<span className="mv-row-v">Chat<Icone n="chevR" s={18} /></span>
          </button>
        )}
        {Object.values(DOCUMENTOS).map(d => (
          <a key={d.url} className="mv-row" href={d.url} target="_blank" rel="noopener noreferrer">
            <Icone n="doc" s={20} />{d.label}<span className="mv-row-v"><Icone n="ext" s={18} /></span>
          </a>
        ))}
      </div>

      {podeSair && (
        <div className="mv-card">
          <button type="button" className="mv-row mv-row-perigo" onClick={logout}>
            <Icone n="logout" s={20} />Sair
          </button>
        </div>
      )}

      {hospedado && <p className="mv-conta-rodape">Conectado pela Waid</p>}
    </div>
  );
}

/**
 * Editar perfil. As regras são as do desktop (`usePerfil`): e-mail somente
 * leitura, especialidade editável só quando o SERVIDOR diz que é — e, quando
 * não é, a tela diz por quê, para o campo cinza não parecer defeito.
 */
export function SheetPerfil({ hospedado, onFechar, onSalvo }: {
  hospedado: boolean;
  onFechar: () => void;
  onSalvo: () => void;
}) {
  const p = usePerfil({ onSuccess: onSalvo, onClose: onFechar });
  const [confirmando, setConfirmando] = useState(false);
  const [nomeConfirmado, setNomeConfirmado] = useState('');

  return (
    <BottomSheet
      titulo="Editar perfil"
      onFechar={onFechar}
      rodape={
        <button type="button" className="mv-btn mv-btn-pri mv-full" disabled={p.loading || p.saving || !p.name.trim()} onClick={() => void p.salvar()}>
          {p.saving ? 'Salvando…' : 'Salvar'}
        </button>
      }
    >
      {p.loading ? <p className="mv-lede">Carregando…</p> : (
        <>
          <label className="mv-fld">
            <span className="mv-fld-l">Nome</span>
            <input className="mv-inp" value={p.name} onChange={e => p.setName(e.target.value)} autoComplete="name" />
          </label>

          <div className="mv-fld">
            <span className="mv-fld-l">Especialidade</span>
            {p.especialidadeEditavel ? (
              <select className="mv-inp" value={p.especialidade} onChange={e => p.setEspecialidade(e.target.value)} aria-label="Especialidade">
                <option value="">Não informada</option>
                {p.especialidades.map(e => <option key={e.slug} value={e.slug}>{e.nome}</option>)}
              </select>
            ) : (
              <>
                <div className="mv-inp mv-inp-ro">{p.especialidadeNome || '—'}</div>
                <small>{ORIGEM_LEGIVEL[p.origemEspecialidade ?? ''] ?? 'Definida pelo seu cadastro.'} Se estiver incorreta, fale com o suporte.</small>
              </>
            )}
          </div>

          <div className="mv-fld">
            <span className="mv-fld-l">E-mail</span>
            <div className="mv-inp mv-inp-ro mv-quebra" data-testid="perfil-email">{p.email}</div>
            <small>{hospedado ? 'Gerenciado pela sua conta Waid.' : 'Para trocar o e-mail, fale com o suporte.'}</small>
          </div>

          {p.crmLabel && (
            <div className="mv-fld">
              <span className="mv-fld-l">Registro</span>
              <div className="mv-inp mv-inp-ro">{p.crmLabel}</div>
            </div>
          )}

          {p.error && <p className="mv-erro-txt" role="alert">{p.error}</p>}

          {/* Excluir a conta é direito do titular (LGPD) e precisa estar ao
              alcance — mas não à mão: pede o nome completo para confirmar. */}
          {confirmando ? (
            <div className="mv-perigo" role="alert">
              <p><b>Excluir conta permanentemente.</b> Esta ação não pode ser desfeita. Digite seu nome completo para confirmar.</p>
              <input className="mv-inp" value={nomeConfirmado} onChange={e => setNomeConfirmado(e.target.value)} placeholder="Seu nome completo" aria-label="Nome completo para confirmar" />
              <div className="mv-perigo-acoes">
                <button type="button" className="mv-btn mv-btn-sec" onClick={() => { setConfirmando(false); setNomeConfirmado(''); }}>Cancelar</button>
                <button type="button" className="mv-btn mv-btn-perigo" disabled={!nomeConfirmado || p.deleting} onClick={() => void p.excluirConta(nomeConfirmado)}>
                  {p.deleting ? 'Excluindo…' : 'Excluir conta'}
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className="mv-btn-texto mv-btn-texto-perigo" onClick={() => setConfirmando(true)}>
              Excluir minha conta
            </button>
          )}
        </>
      )}
    </BottomSheet>
  );
}
