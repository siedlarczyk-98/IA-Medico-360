"""
Orçamento de contexto por tokens.

Substitui o corte por caracteres (`msg.content[:800]`, últimas 10 mensagens) que
o orquestrador usava. Aquele corte tinha dois problemas: cortava no meio de uma
frase sem aviso, e não tinha relação nenhuma com o limite real do modelo — dez
mensagens curtas cabiam folgadas, dez mensagens longas estouravam.

**A contagem é uma estimativa, não exata.** Não há tokenizador aqui de
propósito: `tiktoken` só vale para OpenAI, e o projeto fala com quatro
provedores. Um tokenizador por provedor seria dependência pesada para uma
decisão que precisa apenas ser razoável.

**Errar para menos aqui é inofensivo.** O orçamento (6000 tokens) está muito
abaixo da janela de qualquer modelo em uso — 200k no Sonnet. Subestimar em 30%
significa enviar 7800 tokens em vez de 6000: nada estoura. O orçamento é
controle de CUSTO e de ruído, não proteção contra limite técnico. Isso
inverte a intuição comum sobre contagem de tokens, e é o motivo de a razão
abaixo ser calibrada pela mediana e não por um percentil pessimista.
"""

from dataclasses import dataclass

# Razão caracteres/token, medida contra dados reais em 2026-08-27.
#
# Fonte: 54 interações com `tokens_in` gravado, isolando as que não tinham
# histórico, anexo nem busca web somados à contagem (ver docs/debitos.md #3).
# Medianas por modelo:
#
#   claude-sonnet-4-6 (raciocínio clínico)  3.17   ← o que carrega o uso clínico
#   claude-sonnet-4-20250514                4.13
#   gpt-5.4-nano                            4.40
#   global                                  3.55
#   pior caso observado                     2.55
#
# O valor segue a mediana do modelo de raciocínio clínico, arredondada para
# baixo: é ele que recebe os textos longos e densos — evolução, exames, siglas —
# que tokenizam pior. Nos demais a estimativa fica folgada, o que só faz enviar
# um pouco menos de contexto do que caberia.
#
# Antes disto o valor era 3.5, descrito no código como "conservador". Não era:
# 3.5 é a mediana GLOBAL, e uma mediana erra metade das vezes para cada lado —
# a medição mostrou subestimativa em 46% dos casos. O número estava razoável, o
# raciocínio declarado sobre ele é que estava errado.
CHARS_PER_TOKEN = 3.2

# Piso por mensagem: mesmo uma resposta de uma palavra custa a marcação de
# papel e os delimitadores que o provedor acrescenta.
TOKEN_OVERHEAD_POR_MENSAGEM = 4

# Orçamento do histórico, em tokens.
#
# NÃO é limite técnico: a janela do Sonnet é 200k, e 6000 cabe trinta vezes lá
# dentro. É uma decisão de PRODUTO — quanto se aceita pagar, por mensagem, para
# o modelo lembrar da conversa.
#
# Subir aumenta custo e o risco de afogar a pergunta atual em contexto antigo;
# descer faz o médico perceber que "ele esqueceu o que eu disse". Não existe
# valor certo a ser descoberto por medição: existe o valor que o dono do
# produto escolhe. 6000 é um ponto de partida, não uma conclusão.
DEFAULT_HISTORY_TOKEN_BUDGET = 6000


# Orçamento SEPARADO para o conteúdo de anexos no histórico, em tokens.
#
# Por que separado, e não um orçamento único maior: um laudo de TC/RM extraído
# de PDF gasta ~2500 tokens, e um laboratorial completo ~4700. Contra o
# orçamento único de 6000, UM exame antigo comia de 42% a 78% do espaço e
# expulsava a conversa — o médico anexava um exame e, três mensagens depois, o
# modelo tinha o exame mas havia esquecido o caso. Somar tudo num teto maior
# encareceria TODA conversa, inclusive as sem anexo, para atender um caso que
# só aparece quando há exame.
#
# O VALOR vem do teto real da extração, não de estimativa. Medido em
# 2026-09-08 com `estimate_tokens` contra os limites de
# `file_extractor_service`:
#
#   MAX_EXTRACTED_CHARS = 50_000  →  ~15.600 tokens por anexo (teto absoluto)
#   prontuário longo (25k chars)  →   ~7.800 tokens
#   laboratorial completo (15k)   →   ~4.700 tokens
#   TC/RM típico (8k)             →   ~2.500 tokens
#   laudo curto (2k)              →     ~630 tokens
#
# 12000 cobre o prontuário longo com folga e dois exames típicos juntos, sem
# alcançar o teto de 15.600 — um anexo no limite da extração ainda é omitido,
# de propósito: 15k tokens de UM arquivo antigo é mais contexto do que vale a
# pena carregar em toda mensagem seguinte.
#
# ATENÇÃO ao mexer: um valor ABAIXO de ~4700 é uma regressão silenciosa. Ele
# derruba anexos que hoje passam pelo orçamento único de 6000, e o sintoma
# aparece como "o modelo parou de ver meu exame" — exatamente o bug que esta
# separação veio consertar. O primeiro valor tentado aqui foi 4000, e fazia
# isso. O teste `test_anexo_que_passava_no_orcamento_unico_continua_passando`
# trava esse piso.
DEFAULT_ATTACHMENT_TOKEN_BUDGET = 12000

# Marcadores que `file_extractor_service.resolve_files_context` escreve ao
# fundir um anexo no prompt. São a única pista, no texto já persistido em
# `prompt_text`, de onde termina o anexo e começa a pergunta do médico.
#
# Acoplamento reconhecido: se aquele formato mudar, a separação aqui deixa de
# reconhecer o anexo. O teste `test_o_formato_do_anexo_casa_com_o_extrator`
# trava os dois lados juntos para que a mudança falhe no teste, e não em
# produção com um exame silenciosamente contado como conversa.
_MARCADORES_DE_ANEXO = ("[Arquivo: ", "[Imagem anexada: ", "[Descrição da imagem ")
_SEPARADOR_ANEXO = "\n\n---\n\n"

# Substitui o conteúdo de um anexo que não coube no orçamento. Precisa ser
# explícito: um anexo que some sem aviso faz o modelo responder como se ele
# nunca tivesse sido enviado, enquanto o médico continua vendo o arquivo na
# tela da conversa.
_AVISO_ANEXO_OMITIDO = (
    "[Anexo enviado nesta mensagem, omitido do contexto por limite de espaço. "
    "Peça ao médico para reenviar se precisar do conteúdo.]"
)


def separar_anexo(content: str) -> tuple[str, str]:
    """Divide um turno em (conteúdo de anexo, pergunta do médico).

    Devolve anexo vazio quando o turno não tem anexo — que é o caso comum.
    """
    if not content.startswith(_MARCADORES_DE_ANEXO):
        return "", content
    anexo, separador, pergunta = content.partition(_SEPARADOR_ANEXO)
    if not separador:
        return "", content
    return anexo, pergunta


@dataclass
class Turn:
    """Uma fala da conversa, já no formato que os providers consomem."""

    role: str  # "user" | "assistant"
    content: str

    def to_message(self) -> dict:
        return {"role": self.role, "content": self.content}


def estimate_tokens(text: str) -> int:
    """Estimativa conservadora do custo em tokens de um texto."""
    if not text:
        return TOKEN_OVERHEAD_POR_MENSAGEM
    return int(len(text) / CHARS_PER_TOKEN) + TOKEN_OVERHEAD_POR_MENSAGEM


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """
    Corta um texto para caber num orçamento, marcando que houve corte.

    A marca importa: sem ela o modelo lê um caso clínico interrompido no meio
    como se fosse o caso inteiro, e pode concluir a partir de dados que na
    verdade existem e não chegaram até ele.
    """
    if max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    marca = " [...trecho anterior omitido por limite de contexto]"
    espaco = int((max_tokens - TOKEN_OVERHEAD_POR_MENSAGEM) * CHARS_PER_TOKEN) - len(marca)
    if espaco <= 0:
        return marca.strip()
    # Mantém o FIM da mensagem: numa evolução clínica, o mais recente costuma
    # ser a conduta e o desfecho, não a identificação do paciente.
    return marca.strip() + " " + text[-espaco:]


def fit_turns_to_budget(
    turns: list[Turn],
    budget_tokens: int = DEFAULT_HISTORY_TOKEN_BUDGET,
) -> list[Turn]:
    """
    Devolve os turnos mais recentes que cabem no orçamento.

    Descarta do mais antigo para o mais recente — numa conversa clínica, o
    turno anterior vale mais que o primeiro. Se o turno mais recente sozinho
    não couber, ele é truncado em vez de descartado: perder a última fala
    esvaziaria o contexto justamente do que mais importa.

    O resultado nunca começa com um turno de assistente. Perplexity e vários
    outros exigem alternância começando por `user`, e um histórico que abre com
    a resposta a uma pergunta ausente é confuso mesmo onde é aceito.
    """
    if not turns or budget_tokens <= 0:
        return []

    selecionados: list[Turn] = []
    restante = budget_tokens

    for turn in reversed(turns):
        custo = estimate_tokens(turn.content)
        if custo <= restante:
            selecionados.append(turn)
            restante -= custo
            continue

        # Não coube. Se ainda não pegamos nada, é o turno mais recente sozinho
        # estourando o orçamento — trunca em vez de sair de mãos vazias.
        if not selecionados:
            cortado = truncate_to_tokens(turn.content, restante)
            if cortado:
                selecionados.append(Turn(role=turn.role, content=cortado))
        break

    selecionados.reverse()

    while selecionados and selecionados[0].role == "assistant":
        selecionados.pop(0)

    if selecionados:
        return selecionados

    # Sobrou nada: o orçamento só dava para a última fala do assistente, que
    # sozinha é inútil (é resposta a uma pergunta que o modelo não vê) e ainda
    # viola a alternância exigida por alguns provedores. Melhor gastar o mesmo
    # orçamento com a última PERGUNTA do médico, que se sustenta sozinha.
    for turn in reversed(turns):
        if turn.role != "user":
            continue
        cortado = truncate_to_tokens(turn.content, budget_tokens)
        return [Turn(role="user", content=cortado)] if cortado else []

    return []


def turns_to_messages(turns: list[Turn]) -> list[dict]:
    """Converte para a lista de dicts que os providers recebem."""
    return [t.to_message() for t in turns]


def fit_turns_with_attachment_budget(
    turns: list[Turn],
    budget_tokens: int = DEFAULT_HISTORY_TOKEN_BUDGET,
    attachment_budget_tokens: int = DEFAULT_ATTACHMENT_TOKEN_BUDGET,
) -> list[Turn]:
    """
    Ajusta os turnos com orçamentos SEPARADOS para conversa e para anexos.

    O problema que isto resolve: com um orçamento único, o texto de um exame
    anexado disputava espaço com a conversa e costumava ganhar por tamanho. Um
    laudo de TC/RM (~2500 tokens) ocupava 42% do orçamento de 6000, e um
    laboratorial completo (~4700) ocupava 78% — o exame ficava, a discussão do
    caso era descartada, e o médico via o modelo "esquecer" o que ele tinha
    acabado de dizer.

    Aqui cada turno é dividido em (anexo, pergunta). As perguntas e respostas
    concorrem pelo orçamento de conversa; os anexos, pelo seu próprio. Um exame
    grande passa a comer o orçamento de anexos — não o da conversa.

    Os anexos são preservados do mais recente para o mais antigo: quando o
    espaço acaba, o exame que se perde é o mais velho, não o que o médico
    acabou de mandar. Um anexo que não cabe é REMOVIDO com um aviso no lugar,
    nunca truncado em silêncio — meio hemograma parece um hemograma inteiro, e
    o modelo concluiria a partir de valores que não chegaram até ele.
    """
    if not turns:
        return []

    # 1. Separa cada turno em anexo e conversa, guardando a posição.
    anexos: dict[int, str] = {}
    conversa: list[Turn] = []
    for idx, turn in enumerate(turns):
        anexo, pergunta = separar_anexo(turn.content)
        if anexo:
            anexos[idx] = anexo
        conversa.append(Turn(role=turn.role, content=pergunta))

    # 2. A conversa é ajustada sozinha, pela regra que já existia. Sem os
    #    anexos no meio, o orçamento volta a medir o que ele diz medir.
    #    O casamento é por posição — o conteúdo já foi alterado pela separação
    #    e não serve de chave.
    conversa_ajustada = fit_turns_to_budget(conversa, budget_tokens)
    mantidos = _indices_mantidos(conversa, conversa_ajustada)

    if not anexos:
        return conversa_ajustada

    # 3. Os anexos dos turnos sobreviventes disputam o orçamento próprio, do
    #    mais recente para o mais antigo.
    restante = attachment_budget_tokens
    anexos_cabem: dict[int, str] = {}
    for idx in sorted((i for i in anexos if i in mantidos), reverse=True):
        custo = estimate_tokens(anexos[idx])
        if custo <= restante:
            anexos_cabem[idx] = anexos[idx]
            restante -= custo

    # 4. Remonta, recolocando o anexo antes da pergunta do turno a que pertence.
    resultado: list[Turn] = []
    for pos, idx in enumerate(sorted(mantidos)):
        turn = conversa_ajustada[pos]
        if idx not in anexos:
            resultado.append(turn)
            continue

        if idx in anexos_cabem:
            corpo = anexos_cabem[idx] + _SEPARADOR_ANEXO + turn.content
        else:
            # O aviso é o ponto: sem ele o modelo lê a pergunta como se o exame
            # nunca tivesse existido e responde com confiança indevida. Com
            # ele, sabe que houve um anexo que não alcança e pode dizer isso.
            corpo = _AVISO_ANEXO_OMITIDO + _SEPARADOR_ANEXO + turn.content
        resultado.append(Turn(role=turn.role, content=corpo))

    return resultado


def _indices_mantidos(originais: list[Turn], ajustados: list[Turn]) -> list[int]:
    """Posições de `originais` que sobreviveram ao corte por orçamento.

    `fit_turns_to_budget` só descarta do início e, no máximo, trunca o primeiro
    que sobra — então os mantidos são sempre um sufixo contíguo. Casar por
    conteúdo falharia justamente no turno truncado, que é o que mais importa.
    """
    if not ajustados:
        return []
    return list(range(len(originais) - len(ajustados), len(originais)))
