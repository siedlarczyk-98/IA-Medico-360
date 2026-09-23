/**
 * As regras do campo de pergunta, sem a aparência.
 *
 * Limites de anexo, validação de tamanho, consentimento de imagem, upload em
 * série e o bloqueio de envio durante a extração. O `InputBar` do desktop e o
 * campo da casca mobile desenham coisas diferentes com as MESMAS regras — cada
 * uma delas veio de um problema real, e divergir entre as cascas seria
 * reabri-los numa delas.
 *
 * O estado mora em `rascunho.ts`, não aqui: ver o docblock de lá.
 */

import { extractFile, type ExtractResult } from '../api/uploads';
import type { Attachment, Effort } from '../components/InputBar';
import { alterarRascunho, lerRascunho, useRascunho } from './rascunho';

// Teto por mensagem, espelhando MAX_ANEXOS_POR_MENSAGEM no backend. Repetido
// aqui para avisar o médico ANTES do upload, em vez de deixá-lo anexar cinco
// arquivos e receber 422 no envio.
export const MAX_ANEXOS = 5;

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;   // 5 MB
const MAX_FILE_BYTES = 10 * 1024 * 1024;    // 10 MB
const IMAGE_DLP_ACK_KEY = 'img_dlp_ack';    // consentimento (1x por sessão)

const isImageFile = (file: File) => file.type.startsWith('image/');

interface Opcoes {
  onSend: (text: string, effort: Effort, attachments?: Attachment[]) => void;
  disabled?: boolean;
  sendBlocked?: boolean;
  onAttachmentChange?: (attachments: Attachment[]) => void;
}

export function useComposer({ onSend, disabled, sendBlocked, onAttachmentChange }: Opcoes) {
  const r = useRascunho();

  const filled = r.texto.trim().length > 0 || r.anexos.length > 0;
  // Extração em andamento bloqueia o envio — pelo botão E pelo Enter, que passa
  // por `submit` sem olhar o `disabled` do botão. Sem isto a mensagem saía sem o
  // exame, a resposta clínica vinha sem ele e nada avisava o médico; o arquivo,
  // ao terminar, grudava na pergunta SEGUINTE.
  const extraindo = r.envio === 'loading';
  const podeEnviar = filled && !disabled && !sendBlocked && !extraindo;

  function mudarAnexos(fn: (anexos: Attachment[]) => Attachment[]) {
    alterarRascunho(atual => {
      const anexos = fn(atual.anexos);
      onAttachmentChange?.(anexos);
      return { anexos };
    });
  }

  async function doUpload(files: File[]) {
    alterarRascunho({ envio: 'loading', erroDeEnvio: '' });

    // Em série, não em paralelo: cada imagem dispara uma chamada de visão no
    // backend, e mandar cinco de uma vez castiga o rate limit de /uploads.
    //
    // Cada arquivo é gravado QUANDO CHEGA, e o erro de um não interrompe os
    // outros. Antes os resultados só entravam no estado depois do laço inteiro:
    // um erro no terceiro arquivo descartava os dois que já tinham sido
    // processados (e pagos), e o médico via só "erro", sem saber o que sobrou.
    const falhas: string[] = [];
    for (const file of files) {
      try {
        const result: ExtractResult = await extractFile(file);
        const novo: Attachment = {
          fileId: result.file_id,
          name: result.file_name,
          fileType: result.file_type,
          warning: result.warning,
        };
        mudarAnexos(anexos => [...anexos, novo]);
      } catch (err) {
        const motivo = err instanceof Error ? err.message : 'Erro ao processar arquivo.';
        falhas.push(files.length > 1 ? `"${file.name}": ${motivo}` : motivo);
      }
    }

    if (falhas.length > 0) {
      alterarRascunho({ envio: 'error', erroDeEnvio: falhas.join(' ') });
    } else {
      alterarRascunho({ envio: 'idle' });
    }
  }

  /** Arquivos escolhidos no seletor. Valida tudo antes de subir qualquer um. */
  function adicionarArquivos(files: File[]) {
    if (files.length === 0) return;
    const { anexos } = lerRascunho();

    if (anexos.length + files.length > MAX_ANEXOS) {
      alterarRascunho({ envio: 'error', erroDeEnvio: `Máximo de ${MAX_ANEXOS} arquivos por mensagem.` });
      return;
    }

    // B4: valida tamanho no cliente antes de enviar.
    const grande = files.find(f => f.size > (isImageFile(f) ? MAX_IMAGE_BYTES : MAX_FILE_BYTES));
    if (grande) {
      const limit = isImageFile(grande) ? MAX_IMAGE_BYTES : MAX_FILE_BYTES;
      alterarRascunho({ envio: 'error', erroDeEnvio: `"${grande.name}" é maior que ${Math.round(limit / (1024 * 1024))} MB.` });
      return;
    }

    // S1: imagens não passam pelo filtro de PII (DLP) — pede consentimento 1x por sessão.
    // Basta uma imagem no lote para exigir o aceite; o lote inteiro fica pendente.
    if (files.some(isImageFile) && sessionStorage.getItem(IMAGE_DLP_ACK_KEY) !== '1') {
      alterarRascunho({ imagensPendentes: files });
      return;
    }

    void doUpload(files);
  }

  function confirmarImagens() {
    sessionStorage.setItem(IMAGE_DLP_ACK_KEY, '1');
    const files = lerRascunho().imagensPendentes;
    alterarRascunho({ imagensPendentes: null });
    if (files) void doUpload(files);
  }

  function cancelarImagens() {
    alterarRascunho({ imagensPendentes: null });
  }

  function removerAnexo(fileId: string) {
    mudarAnexos(anexos => anexos.filter(a => a.fileId !== fileId));
    alterarRascunho({ envio: 'idle', erroDeEnvio: '' });
  }

  function descartarErro() {
    alterarRascunho({ envio: 'idle', erroDeEnvio: '' });
  }

  /** Envia e limpa. Devolve `false` quando não havia o que enviar ou estava bloqueado. */
  function submit(): boolean {
    // Lê do store, não do render: o Enter pode chegar antes do re-render que
    // refletiria o último caractere ou o fim de um upload.
    const atual = lerRascunho();
    const cheio = atual.texto.trim().length > 0 || atual.anexos.length > 0;
    if (!cheio || disabled || sendBlocked || atual.envio === 'loading') return false;
    onSend(atual.texto.trim(), atual.esforco, atual.anexos.length > 0 ? atual.anexos : undefined);
    alterarRascunho({ texto: '', anexos: [], envio: 'idle', erroDeEnvio: '' });
    onAttachmentChange?.([]);
    return true;
  }

  return {
    texto: r.texto,
    esforco: r.esforco,
    anexos: r.anexos,
    envio: r.envio,
    erroDeEnvio: r.erroDeEnvio,
    imagensPendentes: r.imagensPendentes,
    filled,
    extraindo,
    podeEnviar,
    lotado: r.anexos.length >= MAX_ANEXOS,
    mudarTexto: (texto: string) => alterarRascunho({ texto }),
    mudarEsforco: (esforco: Effort) => alterarRascunho({ esforco }),
    adicionarArquivos,
    confirmarImagens,
    cancelarImagens,
    removerAnexo,
    descartarErro,
    submit,
  };
}
