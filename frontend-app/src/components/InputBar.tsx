import { useRef, useState } from 'react';
import { useIsMobile } from '../hooks/useIsMobile';
import { extractFile, ACCEPTED_FILE_TYPES, type ExtractResult } from '../api/uploads';
import { chipNeutral, iconButtonBase } from '../lib/styles';

export type Effort = 'rápido' | 'detalhado';
export type OrchestratorMode = 'QUICK_SEARCH' | 'CLINICAL_REASONING' | 'PHARMA_CHECK' | 'PRODUCTIVITY';

export interface Attachment {
  fileId: string;
  name: string;
  fileType: string;  // 'image' | 'pdf' | 'docx' | 'xlsx'
}

const MODE_OPTIONS: { key: OrchestratorMode; label: string; shortLabel: string }[] = [
  { key: 'QUICK_SEARCH',       label: 'Busca Rápida',         shortLabel: 'Busca' },
  { key: 'CLINICAL_REASONING', label: 'Raciocínio Clínico',   shortLabel: 'Clínico' },
  { key: 'PHARMA_CHECK',       label: 'Farmacológico',        shortLabel: 'Farmácia' },
  { key: 'PRODUCTIVITY',       label: 'Produtividade',        shortLabel: 'Produt.' },
];

const FILE_TYPE_ICON: Record<string, string> = {
  pdf: '📄',
  docx: '📝',
  xlsx: '📊',
  image: '🖼',
};

const TEXTAREA_MAX_HEIGHT = 240;            // px — acima disso, rola dentro do textarea em vez de empurrar o botão Enviar para fora
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;   // 5 MB
const MAX_FILE_BYTES = 10 * 1024 * 1024;    // 10 MB
const IMAGE_DLP_ACK_KEY = 'img_dlp_ack';    // consentimento (1x por sessão)

const isImageFile = (file: File) => file.type.startsWith('image/');

interface Props {
  onSend: (text: string, effort: Effort, attachment?: Attachment) => void;
  disabled?: boolean;
  placeholder?: string;
  mode?: OrchestratorMode;
  onModeChange?: (mode: OrchestratorMode) => void;
  onAttachmentChange?: (attachment: Attachment | null) => void;
  webSearchEnabled?: boolean;
  onWebSearchToggle?: () => void;
}

export function InputBar({ onSend, disabled, placeholder, mode = 'QUICK_SEARCH', onModeChange, onAttachmentChange, webSearchEnabled, onWebSearchToggle }: Props) {
  const isMobile = useIsMobile();
  const [value, setValue] = useState('');
  const [effort, setEffort] = useState<Effort>('detalhado');
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [uploadState, setUploadState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [uploadError, setUploadError] = useState('');
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const filled = value.trim().length > 0 || !!attachment;

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value);
    if (textareaRef.current) {
      const el = textareaRef.current;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, TEXTAREA_MAX_HEIGHT) + 'px';
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    // B4: valida tamanho no cliente antes de enviar.
    const limit = isImageFile(file) ? MAX_IMAGE_BYTES : MAX_FILE_BYTES;
    if (file.size > limit) {
      setAttachment(null);
      setUploadState('error');
      setUploadError(`Arquivo maior que ${Math.round(limit / (1024 * 1024))} MB.`);
      return;
    }

    // S1: imagens não passam pelo filtro de PII (DLP) — pede consentimento 1x por sessão.
    if (isImageFile(file) && sessionStorage.getItem(IMAGE_DLP_ACK_KEY) !== '1') {
      setPendingImage(file);
      return;
    }

    void doUpload(file);
  }

  async function doUpload(file: File) {
    setUploadState('loading');
    setUploadError('');
    setAttachment(null);

    try {
      const result: ExtractResult = await extractFile(file);
      const att: Attachment = { fileId: result.file_id, name: result.file_name, fileType: result.file_type };
      setAttachment(att);
      onAttachmentChange?.(att);
      setUploadState('idle');
    } catch (err) {
      setUploadState('error');
      setUploadError(err instanceof Error ? err.message : 'Erro ao processar arquivo.');
    }
  }

  function confirmImageConsent() {
    sessionStorage.setItem(IMAGE_DLP_ACK_KEY, '1');
    const file = pendingImage;
    setPendingImage(null);
    if (file) void doUpload(file);
  }

  function cancelImageConsent() {
    setPendingImage(null);
  }

  function removeAttachment() {
    setAttachment(null);
    onAttachmentChange?.(null);
    setUploadState('idle');
    setUploadError('');
  }

  function submit() {
    if (!filled || disabled) return;
    onSend(value.trim(), effort, attachment ?? undefined);
    setValue('');
    setAttachment(null);
    onAttachmentChange?.(null);
    setUploadState('idle');
    setUploadError('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
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
            <div style={{ fontSize: 13, color: 'var(--pen2)', lineHeight: 1.5, marginBottom: 20 }}>
              Diferente do texto, <strong>imagens não passam pelo filtro automático de dados pessoais (PII)</strong> e
              são analisadas por serviços de IA externos. Evite enviar imagens com nome, CPF, RG ou outros dados que
              identifiquem o paciente. Deseja continuar?
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                onClick={cancelImageConsent}
                style={{
                  height: 34, padding: '0 16px', borderRadius: 8,
                  border: '1px solid var(--line2)', background: 'transparent',
                  color: 'var(--pen2)', fontWeight: 600, fontSize: 12.5, cursor: 'pointer',
                }}
              >
                Cancelar
              </button>
              <button
                onClick={confirmImageConsent}
                style={{
                  height: 34, padding: '0 16px', borderRadius: 8, border: 'none',
                  background: 'var(--petrol)', color: '#fff', fontWeight: 700, fontSize: 12.5, cursor: 'pointer',
                }}
              >
                Entendi, continuar
              </button>
            </div>
          </div>
        </div>
      )}
      <div style={{
        width: 720, maxWidth: '92%',
        border: `1px solid ${filled ? 'var(--petrol)' : 'var(--line)'}`,
        borderRadius: 14, background: '#fff',
        padding: 14, boxShadow: '0 4px 18px rgba(14,37,45,0.05)',
        transition: 'border-color 0.15s',
      }}>
        {/* Seletor de modo — apenas no Orquestrador */}
        {onModeChange && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
            {MODE_OPTIONS.map(opt => {
              const active = mode === opt.key;
              return (
                <button
                  key={opt.key}
                  onClick={() => onModeChange?.(opt.key)}
                  title={opt.label}
                  style={{
                    padding: '4px 11px', fontSize: 11, fontWeight: 600, borderRadius: 8,
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

        {/* Chip de arquivo anexado */}
        {(attachment || uploadState !== 'idle') && (
          <div style={{ marginBottom: 8 }}>
            {uploadState === 'loading' && (
              <div style={chipNeutral}>
                <span style={{ animation: 'pulse 1s infinite' }}>⏳</span>
                Processando arquivo…
              </div>
            )}
            {uploadState === 'error' && (
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '4px 10px', borderRadius: 8,
                background: '#fff5f5', border: '1px solid #fca5a5',
                fontSize: 11.5, color: '#dc2626',
              }}>
                ⚠️ {uploadError}
                <button
                  onClick={removeAttachment}
                  aria-label="Descartar erro"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', padding: 0, fontSize: 13, lineHeight: 1 }}
                >×</button>
              </div>
            )}
            {attachment && uploadState === 'idle' && (
              <div style={chipNeutral}>
                <span>{FILE_TYPE_ICON[attachment.fileType] ?? '📎'}</span>
                <span style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {attachment.name}
                </span>
                <button
                  onClick={removeAttachment}
                  title="Remover arquivo"
                  aria-label="Remover arquivo"
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--pen3)', padding: 0, fontSize: 14, lineHeight: 1,
                  }}
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
            background: 'transparent', fontSize: 13.5, color: 'var(--ink)',
            lineHeight: 1.5, minHeight: 36, maxHeight: TEXTAREA_MAX_HEIGHT,
            overflowY: 'auto',
          }}
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
          {/* Botão de anexo */}
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_FILE_TYPES}
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || uploadState === 'loading'}
            title="Anexar arquivo (PDF, Word, Excel, imagem)"
            aria-label="Anexar arquivo"
            style={{
              ...iconButtonBase,
              width: 30,
              background: attachment ? 'var(--fill2)' : 'transparent',
              color: attachment ? 'var(--petrol)' : 'var(--pen3)',
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
                height: 30, padding: '0 10px', borderRadius: 8,
                border: `1px solid ${webSearchEnabled ? 'var(--petrol)' : 'var(--line2)'}`,
                background: webSearchEnabled ? 'var(--petrol)' : 'transparent',
                color: webSearchEnabled ? '#fff' : 'var(--pen3)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                flexShrink: 0, fontSize: 11, fontWeight: 600,
                transition: 'all 0.12s',
              }}
            >
              🌐 {webSearchEnabled ? 'Web on' : 'Web'}
            </button>
          )}

          {/* Segmented control de esforço */}
          <div style={{
            display: 'flex', borderRadius: 8, overflow: 'hidden',
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
                  padding: '3px 10px', fontSize: 10.5, fontWeight: 600, border: 'none',
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
          {!isMobile && <span style={{ fontSize: 10.5, color: 'var(--pen3)' }}>⌘ + ⏎ enviar</span>}
          <button
            onClick={submit}
            disabled={!filled || disabled}
            style={{
              height: 32, padding: '0 14px', borderRadius: 10, border: 'none',
              background: filled ? 'var(--green)' : 'var(--fill)',
              color: filled ? 'var(--ink)' : 'var(--pen3)',
              fontWeight: 700, fontSize: 12,
              display: 'flex', alignItems: 'center', gap: 6,
              transition: 'background 0.15s, color 0.15s',
            }}
          >
            Enviar
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path d="M3 8 H13 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
