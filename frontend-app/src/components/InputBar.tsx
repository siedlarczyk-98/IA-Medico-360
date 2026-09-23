import { memo, useRef } from 'react';
import { useIsMobile } from '../hooks/useIsMobile';
import { ACCEPTED_FILE_TYPES } from '../api/uploads';
import { MAX_ANEXOS, useComposer } from '../chat/useComposer';
import { chipNeutral, iconButtonBase } from '../lib/styles';
import { tratarEnterParaEnviar, DICA_ENVIO } from '../lib/enterParaEnviar';

export type Effort = 'rápido' | 'detalhado';
export type OrchestratorMode = 'QUICK_SEARCH' | 'CLINICAL_REASONING' | 'PHARMA_CHECK' | 'PRODUCTIVITY' | 'EXAM_REVIEW' | 'DATA_OCEAN';

export interface Attachment {
  fileId: string;
  name: string;
  fileType: string;  // 'image' | 'pdf' | 'docx' | 'xlsx'
  /** Aviso do backend quando a extração não rendeu texto (PDF digitalizado). */
  warning?: string | null;
}

const MODE_OPTIONS: { key: OrchestratorMode; label: string; shortLabel: string }[] = [
  { key: 'QUICK_SEARCH',       label: 'Busca Rápida',         shortLabel: 'Busca' },
  { key: 'CLINICAL_REASONING', label: 'Raciocínio Clínico',   shortLabel: 'Clínico' },
  { key: 'PHARMA_CHECK',       label: 'Farmacológico',        shortLabel: 'Farmácia' },
  { key: 'PRODUCTIVITY',       label: 'Produtividade',        shortLabel: 'Produt.' },
  { key: 'EXAM_REVIEW',        label: 'Exames',               shortLabel: 'Exames' },
  // Só por escolha explícita: a triagem nunca roteia para cá (é lento e
  // cobrado por uso de ferramenta). Ver MODOS_NAO_TRIADOS no backend.
  { key: 'DATA_OCEAN',         label: 'Data Ocean',           shortLabel: 'Data Ocean' },
];

const FILE_TYPE_ICON: Record<string, string> = {
  pdf: '📄',
  docx: '📝',
  xlsx: '📊',
  image: '🖼',
};

const TEXTAREA_MAX_HEIGHT = 240;            // px — acima disso, rola dentro do textarea em vez de empurrar o botão Enviar para fora

interface Props {
  onSend: (text: string, effort: Effort, attachments?: Attachment[]) => void;
  disabled?: boolean;
  /** Bloqueia só o envio (ex: nenhum modelo selecionado no Agregador) — o texto continua editável. */
  sendBlocked?: boolean;
  placeholder?: string;
  mode?: OrchestratorMode;
  onModeChange?: (mode: OrchestratorMode) => void;
  onAttachmentChange?: (attachments: Attachment[]) => void;
  webSearchEnabled?: boolean;
  onWebSearchToggle?: () => void;
  /**
   * Quando presente, o botão de enviar vira "Parar" e cancela a resposta em
   * andamento. O campo continua editável (use junto com `sendBlocked`, não com
   * `disabled`): o médico rascunha a próxima pergunta enquanto lê a resposta.
   */
  onStop?: () => void;
}

export const InputBar = memo(function InputBar({ onSend, disabled, sendBlocked, placeholder, mode = 'QUICK_SEARCH', onModeChange, onAttachmentChange, webSearchEnabled, onWebSearchToggle, onStop }: Props) {
  const isMobile = useIsMobile();
  // Regras e estado do campo vêm de `useComposer` (compartilhado com a casca
  // mobile). Os nomes locais abaixo são os de antes, para o JSX não mudar.
  const composer = useComposer({ onSend, disabled, sendBlocked, onAttachmentChange });
  const {
    texto: value, esforco: effort, anexos: attachments, envio: uploadState,
    erroDeEnvio: uploadError, imagensPendentes: pendingImage, filled, extraindo,
  } = composer;
  const setEffort = composer.mudarEsforco;
  const confirmImageConsent = composer.confirmarImagens;
  const cancelImageConsent = composer.cancelarImagens;
  const removeAttachment = composer.removerAnexo;
  const clearError = composer.descartarErro;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    composer.mudarTexto(e.target.value);
    if (textareaRef.current) {
      const el = textareaRef.current;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, TEXTAREA_MAX_HEIGHT) + 'px';
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    tratarEnterParaEnviar(e, { isMobile, submit });
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = '';
    composer.adicionarArquivos(files);
  }

  function submit() {
    if (composer.submit() && textareaRef.current) textareaRef.current.style.height = 'auto';
  }

  return (
    <div style={{ padding: '14px 0 22px', display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
      {/* S1: modal de consentimento — imagens não passam pelo filtro de PII (DLP) */}
      {pendingImage && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="img-consent-title"
          style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(14,37,45,0.45)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 20,
          }}
        >
          <div style={{
            width: 460, maxWidth: '100%', background: '#fff', borderRadius: 14,
            padding: 24, boxShadow: '0 12px 40px rgba(14,37,45,0.25)',
          }}>
            <div id="img-consent-title" style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 10 }}>
              ⚠️ Atenção: envio de imagem
            </div>
            <div style={{ fontSize: 'var(--texto-apoio)', color: 'var(--pen2)', lineHeight: 1.5, marginBottom: 20 }}>
              Diferente do texto, <strong>imagens não passam pelo filtro automático de dados pessoais (PII)</strong> e
              são analisadas por serviços de IA externos. Evite enviar imagens com nome, CPF, RG ou outros dados que
              identifiquem o paciente. Deseja continuar?
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                onClick={cancelImageConsent}
                style={{
                  minHeight: 'var(--toque-min)', padding: '0 var(--gap-4)', borderRadius: 'var(--raio-1)',
                  border: '1px solid var(--line2)', background: 'transparent',
                  color: 'var(--pen2)', fontWeight: 600, fontSize: 'var(--texto-apoio)', cursor: 'pointer',
                }}
              >
                Cancelar
              </button>
              <button
                onClick={confirmImageConsent}
                style={{
                  minHeight: 'var(--toque-min)', padding: '0 var(--gap-4)', borderRadius: 'var(--raio-1)', border: 'none',
                  background: 'var(--petrol)', color: '#fff', fontWeight: 700, fontSize: 'var(--texto-apoio)', cursor: 'pointer',
                }}
              >
                Entendi, continuar
              </button>
            </div>
          </div>
        </div>
      )}
      <div style={{
        width: 'min(720px, calc(100% - 2 * var(--margem-tela)))',
        border: `1px solid ${filled ? 'var(--petrol)' : 'var(--line)'}`,
        borderRadius: 14, background: '#fff',
        padding: 14, boxShadow: '0 4px 18px rgba(14,37,45,0.05)',
        transition: 'border-color 0.15s',
      }}>
        {/* Seletor de modo — apenas no Orquestrador */}
        {onModeChange && (
          // No celular os seis chips com altura de toque quebravam em duas
          // linhas, e o composer passava a ocupar ~40% da tela — sobrava pouco
          // para ler a resposta. Uma linha com rolagem lateral mantém o alvo
          // de 44px sem roubar altura. As margens negativas deixam os chips
          // correrem até a borda do cartão ao rolar.
          <div
            className={isMobile ? 'rolagem-lateral' : undefined}
            style={isMobile
              ? { display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'nowrap', margin: '0 -14px 10px', padding: '0 14px' }
              : { display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}
          >
            {MODE_OPTIONS.map(opt => {
              const active = mode === opt.key;
              return (
                <button
                  key={opt.key}
                  onClick={() => onModeChange?.(opt.key)}
                  title={opt.label}
                  style={{
                    minHeight: 'var(--toque-min)', padding: 'var(--gap-1) var(--gap-3)', fontSize: 'var(--texto-micro)', fontWeight: 600, borderRadius: 'var(--raio-1)',
                    border: `1px solid ${active ? 'var(--petrol)' : 'var(--line2)'}`,
                    background: active ? 'var(--petrol)' : 'transparent',
                    color: active ? '#fff' : 'var(--pen2)',
                    cursor: 'pointer', transition: 'all 0.12s', whiteSpace: 'nowrap',
                  }}
                >
                  {isMobile ? opt.shortLabel : opt.label}
                </button>
              );
            })}
          </div>
        )}

        {/* Avisos de extração — visíveis, não só em tooltip: o médico precisa
            ver ANTES de enviar que o arquivo não rendeu texto. */}
        {attachments.filter(a => a.warning).map(att => (
          <div
            key={`aviso-${att.fileId}`}
            data-testid="anexo-aviso"
            style={{
              marginBottom: 8, padding: '7px 10px', borderRadius: 8,
              background: '#fffbeb', border: '1px solid #fcd34d',
              fontSize: 'var(--texto-micro)', lineHeight: 'var(--linha-apertada)', color: '#92400e',
            }}
          >
            <strong>{att.name}</strong> — {att.warning}
          </div>
        ))}

        {/* Chips dos arquivos anexados */}
        {(attachments.length > 0 || uploadState !== 'idle') && (
          <div style={{ marginBottom: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {attachments.map(att => (
              <div
                key={att.fileId}
                data-testid="anexo-chip"
                title={att.warning ?? undefined}
                style={att.warning
                  ? { ...chipNeutral, background: '#fffbeb', border: '1px solid #fcd34d', color: '#92400e' }
                  : chipNeutral}
              >
                <span>{att.warning ? '⚠️' : (FILE_TYPE_ICON[att.fileType] ?? '📎')}</span>
                <span style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {att.name}
                </span>
                <button
                  onClick={() => removeAttachment(att.fileId)}
                  title={`Remover ${att.name}`}
                  aria-label={`Remover ${att.name}`}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--pen3)', padding: 0, fontSize: 'var(--texto-apoio)', lineHeight: 1,
                    minHeight: 'var(--toque-min)', minWidth: 'var(--toque-min)',
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  }}
                >×</button>
              </div>
            ))}
            {uploadState === 'loading' && (
              <div style={chipNeutral}>
                <span style={{ animation: 'pulse 1s infinite' }}>⏳</span>
                Processando…
              </div>
            )}
            {uploadState === 'error' && (
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '4px 10px', borderRadius: 8,
                background: '#fff5f5', border: '1px solid #fca5a5',
                fontSize: 'var(--texto-micro)', color: '#dc2626',
              }}>
                ⚠️ {uploadError}
                <button
                  onClick={clearError}
                  aria-label="Descartar erro"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', padding: 0, fontSize: 'var(--texto-micro)', lineHeight: 1, minHeight: 'var(--toque-min)', minWidth: 'var(--toque-min)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
                >×</button>
              </div>
            )}
          </div>
        )}

        <textarea
          ref={textareaRef}
          rows={2}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? 'Digite sua pergunta…'}
          disabled={disabled}
          style={{
            width: '100%', border: 'none', outline: 'none', resize: 'none',
            // 16 px no celular: abaixo disso o iOS dá ZOOM na página ao focar o
            // campo, e o médico precisa desfazer o zoom a cada pergunta.
            background: 'transparent', fontSize: 'var(--texto-campo)', color: 'var(--ink)',
            lineHeight: 1.5, minHeight: 36, maxHeight: TEXTAREA_MAX_HEIGHT,
            overflowY: 'auto',
          }}
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
          {/* Botão de anexo */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_FILE_TYPES}
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || uploadState === 'loading' || attachments.length >= MAX_ANEXOS}
            title={
              attachments.length >= MAX_ANEXOS
                ? `Máximo de ${MAX_ANEXOS} arquivos por mensagem`
                : 'Anexar arquivos (PDF, Word, Excel, imagem)'
            }
            aria-label="Anexar arquivos"
            style={{
              ...iconButtonBase,
              width: 'var(--toque-min)',
              background: attachments.length > 0 ? 'var(--fill2)' : 'transparent',
              color: attachments.length > 0 ? 'var(--petrol)' : 'var(--pen3)',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
            </svg>
          </button>

          {/* Botão de busca web */}
          {onWebSearchToggle && (
            <button
              onClick={onWebSearchToggle}
              title={webSearchEnabled ? 'Desativar busca web' : 'Ativar busca web para resultados atualizados'}
              aria-label={webSearchEnabled ? 'Desativar busca web' : 'Ativar busca web'}
              aria-pressed={webSearchEnabled}
              style={{
                minHeight: 'var(--toque-min)', padding: '0 var(--gap-3)', borderRadius: 'var(--raio-1)',
                border: `1px solid ${webSearchEnabled ? 'var(--petrol)' : 'var(--line2)'}`,
                background: webSearchEnabled ? 'var(--petrol)' : 'transparent',
                color: webSearchEnabled ? '#fff' : 'var(--pen3)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                flexShrink: 0, fontSize: 'var(--texto-micro)', fontWeight: 600,
                transition: 'all 0.12s',
              }}
            >
              🌐 {webSearchEnabled ? 'Web on' : 'Web'}
            </button>
          )}

          {/* Segmented control de esforço */}
          {/* `flexShrink: 0`: o layout encolhia este controle em 320px e o
              `overflow: hidden` cortava o "Detalhado" no meio. */}
          <div style={{
            display: 'flex', borderRadius: 8, overflow: 'hidden', flexShrink: 0,
            border: '1px solid var(--line2)', background: 'var(--fill)',
          }}>
            {(['rápido', 'detalhado'] as Effort[]).map(opt => (
              <button
                key={opt}
                onClick={() => setEffort(opt)}
                title={opt === 'rápido'
                  ? 'Resposta direta e objetiva — ideal para dúvidas rápidas do dia a dia'
                  : 'Resposta completa com raciocínio clínico detalhado — ideal para casos complexos'}
                style={{
                  minHeight: 'var(--toque-min)', padding: isMobile ? '0 var(--gap-2)' : '0 var(--gap-3)', fontSize: 'var(--texto-micro)', fontWeight: 600, border: 'none', whiteSpace: 'nowrap',
                  background: effort === opt ? 'var(--petrol)' : 'transparent',
                  color: effort === opt ? '#fff' : 'var(--pen3)',
                  cursor: 'pointer', textTransform: 'capitalize',
                  transition: 'background 0.12s, color 0.12s',
                }}
              >
                {opt}
              </button>
            ))}
          </div>

          <div style={{ flex: 1 }} />
          {!isMobile && <span style={{ fontSize: 'var(--texto-micro)', color: 'var(--pen3)' }}>{DICA_ENVIO}</span>}
          {onStop ? (
            // Uma resposta leva de 13 a 57 s. Sem "Parar", quem mandou a pergunta
            // errada esperava tudo isso — pagando o modelo — para poder corrigir.
            // No celular Parar e Enviar viram só ícone: com texto, a linha não
            // cabia em 320px e o "Detalhado" ficava escondido atrás do Enviar.
            // O `aria-label` mantém o nome para leitor de tela (e para os testes).
            <button
              onClick={onStop}
              aria-label="Parar"
              style={{
                // Era `height: 32` fixo — no botão que se aperta com pressa.
                minHeight: 'var(--toque-min)', padding: isMobile ? 0 : '0 14px', borderRadius: 10,
                minWidth: 'var(--toque-min)', justifyContent: 'center', flexShrink: 0,
                border: '1px solid var(--line)', background: '#fff', color: 'var(--ink)',
                fontWeight: 700, fontSize: 'var(--texto-apoio)',
                display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              <span aria-hidden="true" style={{ width: isMobile ? 12 : 9, height: isMobile ? 12 : 9, borderRadius: 2, background: 'currentColor' }} />
              {!isMobile && 'Parar'}
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!filled || disabled || sendBlocked || extraindo}
              title={extraindo ? 'Aguarde o processamento do anexo' : undefined}
              aria-label="Enviar"
              style={{
                minHeight: 'var(--toque-min)', padding: isMobile ? 0 : '0 14px', borderRadius: 10, border: 'none',
                minWidth: 'var(--toque-min)', justifyContent: 'center', flexShrink: 0,
                background: filled && !sendBlocked && !extraindo ? 'var(--green)' : 'var(--fill)',
                color: filled && !sendBlocked && !extraindo ? 'var(--ink)' : 'var(--pen3)',
                fontWeight: 700, fontSize: 'var(--texto-apoio)',
                display: 'flex', alignItems: 'center', gap: 6,
                transition: 'background 0.15s, color 0.15s',
              }}
            >
              {!isMobile && 'Enviar'}
              <svg width={isMobile ? 18 : 11} height={isMobile ? 18 : 11} viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M3 8 H13 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
