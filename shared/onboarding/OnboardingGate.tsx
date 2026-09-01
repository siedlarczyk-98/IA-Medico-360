/**
 * O onboarding, escrito uma vez e renderizado pelos três apps.
 *
 * POR QUE COMPARTILHADO, E NÃO UM REDIRECT
 * Os três apps são embedados SEPARADAMENTE como iframes na Curseduca (cada um
 * tem seu próprio EmbedAuthPage). Mandar o médico do `calculadoras-app` para o
 * `/onboarding` do `frontend-app` significaria navegar para fora do iframe.
 *
 * POR QUE NÃO TRÊS CÓPIAS
 * Porque a próxima exigência ("agora peça também X") viraria três mudanças e
 * três divergências. É exatamente assim que este repo acabou com três listas de
 * especialidade que não conversam entre si.
 *
 * O QUE ELE NÃO FAZ
 * Não decide o que falta. Isso vem de `onboarding_pendencias`, calculado no
 * servidor. O componente só renderiza a pendência da vez — acrescentar uma nova
 * é mudança de backend, e os três apps herdam.
 *
 * O QUE SOBROU PARA PERGUNTAR
 * Quase nada: nome e especialidade chegam do cadastro (webhook) ou dos grupos
 * `[CFM]` da Curseduca. Sobraram o estágio de carreira — que nenhuma fonte
 * automática distingue (o grupo não separa residente de especialista) — e o
 * aceite dos Termos, que ninguém pode dar pelo titular.
 */

import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import { buscarEspecialidades, buscarPerfil, enviarOnboarding } from './api';
import * as s from './estilos';
import { MED_STATUS_OPCOES, UFS } from './tipos';
import type { DadosOnboarding, Especialidade, Pendencia, Perfil } from './tipos';

interface Props {
  apiBase: string;
  token: string | null;
  children: ReactNode;
  /**
   * `bloquear` — não deixa usar o app enquanto houver pendência (frontend-app).
   * `avisar`   — mostra faixa no topo e deixa passar. Para apps onde barrar é
   *              hostil (uma calculadora de creatinina não deveria depender de
   *              cadastro completo).
   */
  modo?: 'bloquear' | 'avisar';
  /** Chamado com o token novo quando o onboarding conclui. */
  aoConcluir?: (token: string) => void;
}

export function OnboardingGate({ apiBase, token, children, modo = 'bloquear', aoConcluir }: Props) {
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [mostrarFormulario, setMostrarFormulario] = useState(false);

  useEffect(() => {
    if (!token) {
      setCarregando(false);
      return;
    }
    let ativo = true;
    buscarPerfil(apiBase, token)
      .then(p => {
        if (!ativo) return;
        setPerfil(p);
        setMostrarFormulario(p.onboarding_pendencias.length > 0);
      })
      // Falha ao consultar o perfil não pode virar tela branca: o app abre e o
      // gate simplesmente não age. Barrar o acesso por causa de um GET é pior
      // do que deixar o cadastro incompleto por mais uma sessão.
      .catch(() => ativo && setPerfil(null))
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [apiBase, token]);

  const concluir = useCallback(
    (novoToken: string) => {
      setMostrarFormulario(false);
      aoConcluir?.(novoToken);
    },
    [aoConcluir],
  );

  if (carregando || !token || !perfil) return <>{children}</>;

  const pendencias = perfil.onboarding_pendencias;
  if (pendencias.length === 0 || !mostrarFormulario) return <>{children}</>;

  if (modo === 'avisar') {
    return (
      <>
        <FaixaAviso onAbrir={() => setMostrarFormulario(true)} />
        {children}
      </>
    );
  }

  return (
    <Formulario
      apiBase={apiBase}
      token={token}
      perfil={perfil}
      pendencias={pendencias}
      aoConcluir={concluir}
    />
  );
}

function FaixaAviso({ onAbrir }: { onAbrir: () => void }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexWrap: 'wrap',
        padding: '10px 16px',
        background: s.CORES.mint,
        borderBottom: `1px solid ${s.CORES.line2}`,
        fontSize: 13,
        color: s.CORES.petrol,
        fontFamily: s.FONTE,
      }}
    >
      Complete seu perfil para receber conteúdo da sua especialidade.{' '}
      <button
        onClick={onAbrir}
        style={{
          background: s.CORES.petrol,
          border: 'none',
          borderRadius: 999,
          color: '#fff',
          cursor: 'pointer',
          font: 'inherit',
          fontWeight: 700,
          padding: '4px 12px',
        }}
      >
        Completar agora
      </button>
    </div>
  );
}

function Formulario({
  apiBase,
  token,
  perfil,
  pendencias,
  aoConcluir,
}: {
  apiBase: string;
  token: string;
  perfil: Perfil;
  pendencias: Pendencia[];
  aoConcluir: (token: string) => void;
}) {
  const [nome, setNome] = useState(perfil.name ?? '');
  const [medStatus, setMedStatus] = useState(perfil.med_status ?? '');
  const [crm, setCrm] = useState(perfil.crm ?? '');
  const [uf, setUf] = useState(perfil.crm_state ?? '');
  const [anoIngresso, setAnoIngresso] = useState('');
  const [especialidade, setEspecialidade] = useState(perfil.specialty_slug ?? '');
  const [aceite, setAceite] = useState(false);
  const [especialidades, setEspecialidades] = useState<Especialidade[]>([]);
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);

  const precisa = (p: Pendencia) => pendencias.includes(p);
  const graduando = medStatus === 'graduando';

  // Quem está num grupo `[CFM]` tem CRM, logo não é aluno de graduação; quem
  // tem especialidade registrada também não é generalista. Perguntar mesmo
  // assim é pedir que ele responda o que o registro dele já respondeu — e abre
  // espaço para uma resposta que contradiz o Conselho.
  //
  // Lista vazia = servidor antigo, que não opinava: mostra as quatro.
  const permitidos = perfil.med_status_opcoes ?? [];
  const opcoesCarreira = permitidos.length
    ? MED_STATUS_OPCOES.filter(o => permitidos.includes(o.valor))
    : MED_STATUS_OPCOES;
  // O `med_status` escolhido agora pode revelar campos que o servidor ainda não
  // sabia serem necessários: quem não tinha estágio de carreira definido não
  // recebeu `crm` na lista de pendências, porque não dava para saber se era
  // graduando. A tela resolve isso na hora, sem uma ida ao servidor.
  const pedirCrm = !graduando && (precisa('crm') || (precisa('med_status') && !!medStatus));
  const pedirEspecialidade =
    perfil.specialty_editavel &&
    ['residente', 'especialista'].includes(medStatus) &&
    (precisa('especialidade') || precisa('med_status'));

  useEffect(() => {
    if (!pedirEspecialidade || especialidades.length) return;
    // Lista canônica servida pelo backend. Antes ela era uma constante de 55
    // itens dentro do OnboardingPage.tsx — o único lugar onde existia.
    buscarEspecialidades(apiBase).then(setEspecialidades).catch(() => setEspecialidades([]));
  }, [pedirEspecialidade, especialidades.length, apiBase]);

  const podeEnviar = Boolean(
    medStatus &&
      (!precisa('aceite_termos') || aceite) &&
      (!precisa('nome') || nome.trim().length > 1) &&
      (!pedirCrm || (crm.trim() && uf)) &&
      (!pedirEspecialidade || especialidade) &&
      (!graduando || anoIngresso),
  );

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!podeEnviar || salvando) return;
    setErro('');
    setSalvando(true);
    try {
      const dados: DadosOnboarding = {
        med_status: medStatus,
        // Sempre `true` aqui: o botão só habilita com a caixa marcada quando o
        // aceite é pendência, e o servidor recusa `false` de qualquer forma.
        terms_accepted: true,
        ...(precisa('nome') ? { name: nome.trim() } : {}),
        ...(pedirCrm ? { crm: crm.replace(/\D/g, ''), crm_state: uf } : {}),
        ...(pedirEspecialidade ? { specialty: especialidade } : {}),
        ...(graduando && anoIngresso ? { enrollment_year: Number(anoIngresso) } : {}),
      };
      const resp = await enviarOnboarding(apiBase, token, dados);
      if (resp.onboarding_pendencias.length) {
        // O servidor é quem decide; se ainda falta algo, dizemos o que é em vez
        // de fingir que terminou.
        setErro(`Ainda falta: ${resp.onboarding_pendencias.join(', ')}`);
        return;
      }
      aoConcluir(resp.access_token);
    } catch (err) {
      setErro(err instanceof Error ? err.message : 'Não foi possível salvar.');
    } finally {
      setSalvando(false);
    }
  }

  const primeiroNome = (perfil.name ?? '').trim().split(' ')[0];

  return (
    <div style={s.fundo}>
      {/* Hover e foco não existem em style inline. */}
      <style>{s.CSS_GLOBAL}</style>

      <form style={s.cartao} onSubmit={enviar}>
        <h1 style={s.titulo}>
          {primeiroNome ? `Falta pouco, ${primeiroNome}` : 'Falta pouco'}
        </h1>
        <p style={s.subtitulo}>
          Só o que ainda não sabemos — leva menos de um minuto e vale para todo o Médico&nbsp;360.
        </p>

        {precisa('nome') && (
          <div style={{ marginBottom: 17 }}>
            <label style={s.rotulo} htmlFor="ob-nome">Nome completo</label>
            <input
              id="ob-nome"
              className="m360-ob-campo"
              style={s.campo}
              value={nome}
              onChange={e => setNome(e.target.value)}
              autoComplete="name"
              placeholder="Como devemos te chamar"
            />
          </div>
        )}

        <div style={{ marginBottom: 17 }}>
          <span style={s.rotulo}>Momento da carreira</span>
          <div style={{ display: 'grid', gap: 7 }} role="radiogroup" aria-label="Momento da carreira">
            {opcoesCarreira.map(o => {
              const ativa = medStatus === o.valor;
              return (
                <button
                  key={o.valor}
                  type="button"
                  role="radio"
                  aria-checked={ativa}
                  className="m360-ob-opcao"
                  style={s.opcao(ativa)}
                  onClick={() => setMedStatus(o.valor)}
                >
                  {/* Sem o marcador, os cartões parecem campos desabilitados —
                      era o defeito mais visível da primeira versão. */}
                  <span style={s.marcador(ativa)}>
                    {ativa && <span style={s.marcadorInterno} />}
                  </span>
                  {o.rotulo}
                </button>
              );
            })}
          </div>
        </div>

        {graduando && (
          <div style={{ marginBottom: 17 }}>
            <label style={s.rotulo} htmlFor="ob-ano">Ano de ingresso</label>
            <input
              id="ob-ano"
              className="m360-ob-campo"
              style={s.campo}
              value={anoIngresso}
              onChange={e => setAnoIngresso(e.target.value.replace(/\D/g, '').slice(0, 4))}
              inputMode="numeric"
              placeholder="2022"
            />
          </div>
        )}

        {pedirCrm && (
          <div style={{ marginBottom: 17, display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={s.rotulo} htmlFor="ob-crm">CRM</label>
              <input
                id="ob-crm"
                className="m360-ob-campo"
                style={s.campo}
                value={crm}
                onChange={e => setCrm(e.target.value.replace(/\D/g, ''))}
                inputMode="numeric"
                placeholder="000000"
              />
            </div>
            <div style={{ width: 96 }}>
              <label style={s.rotulo} htmlFor="ob-uf">UF</label>
              <select
                id="ob-uf"
                className="m360-ob-campo"
                style={s.campo}
                value={uf}
                onChange={e => setUf(e.target.value)}
              >
                <option value="">—</option>
                {UFS.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          </div>
        )}

        {pedirEspecialidade && (
          <div style={{ marginBottom: 17 }}>
            <label style={s.rotulo} htmlFor="ob-esp">Especialidade</label>
            <select
              id="ob-esp"
              className="m360-ob-campo"
              style={s.campo}
              value={especialidade}
              onChange={e => setEspecialidade(e.target.value)}
            >
              <option value="">Selecione sua especialidade</option>
              {especialidades.map(esp => (
                <option key={esp.slug} value={esp.slug}>{esp.nome}</option>
              ))}
            </select>
          </div>
        )}

        {precisa('aceite_termos') && (
          <label style={s.aceite}>
            <input
              type="checkbox"
              className="m360-ob-check"
              checked={aceite}
              onChange={e => setAceite(e.target.checked)}
            />
            <span>
              Li e aceito os{' '}
              <a href="/termos" target="_blank" rel="noreferrer" style={s.link}>Termos de Uso</a>
              {' '}e a{' '}
              <a href="/privacidade" target="_blank" rel="noreferrer" style={s.link}>Política de Privacidade</a>.
            </span>
          </label>
        )}

        {erro && <p role="alert" style={s.erro}>{erro}</p>}

        <button
          type="submit"
          className="m360-ob-botao"
          disabled={!podeEnviar || salvando}
          style={s.botao(podeEnviar && !salvando)}
        >
          {salvando ? 'Salvando…' : 'Continuar'}
        </button>
      </form>
    </div>
  );
}
