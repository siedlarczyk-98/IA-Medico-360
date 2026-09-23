/**
 * Aviso antes de enviar imagem: ela não passa pelo filtro de dados pessoais.
 *
 * O texto mantém a substância do aviso do desktop — imagem NÃO passa pelo DLP
 * e é analisada por serviço externo — e acrescenta o que o protótipo tem de
 * melhor: dizer O QUE procurar na imagem (nome, CPF, prontuário, data de
 * nascimento, rosto) e o que fazer (recortar ou cobrir).
 *
 * Sem "não mostrar de novo neste aparelho" (decisão D2): o aviso vale uma vez
 * por sessão, como no desktop, e o storage do webview da Waid não é confiável
 * para guardar um aceite de LGPD.
 */

import { BottomSheet } from './BottomSheet';
import { Icone } from './Icone';

interface Props {
  arquivos: File[];
  onEnviar: () => void;
  onCancelar: () => void;
}

export function SheetConsentimento({ arquivos, onEnviar, onCancelar }: Props) {
  const imagens = arquivos.filter(f => f.type.startsWith('image/'));
  return (
    <BottomSheet
      titulo="Remova dados do paciente"
      semFechar
      onFechar={onCancelar}
      rodape={
        <>
          <button type="button" className="mv-btn mv-btn-dark mv-full" onClick={onEnviar}>Enviar mesmo assim</button>
          <button type="button" className="mv-btn mv-btn-sec mv-full" onClick={onCancelar}>Cancelar</button>
        </>
      }
    >
      <div className="mv-consent">
        <span className="mv-consent-i"><Icone n="shield" /></span>
        <p>
          Diferente do texto, <strong>imagens não passam pelo filtro automático de dados pessoais</strong> e
          são analisadas por serviços de IA externos.
        </p>
        <p>
          Confira se a imagem não mostra <strong>nome, CPF, prontuário, data de nascimento ou rosto</strong> do
          paciente. Recorte ou cubra essas áreas antes de enviar.
        </p>
        {imagens.map(f => (
          <div key={f.name} className="mv-att mv-att-largo">
            <span className="mv-att-i"><Icone n="image" s={18} /></span>
            <span className="mv-att-t"><b>{f.name}</b><span>Imagem · {(f.size / (1024 * 1024)).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB</span></span>
          </div>
        ))}
      </div>
    </BottomSheet>
  );
}
