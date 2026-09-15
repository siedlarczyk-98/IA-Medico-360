"""
Política de DLP na escrita — todo texto clínico é mascarado ANTES do banco.

POR QUE ESTE ARQUIVO EXISTE
Até 2026-09-15 o DLP era unidirecional: mascarava o que ia PARA o provider e
deixava passar o que vinha DELE, além do texto extraído de anexo. Os dois furos
foram achados pela revisão externa e corrigidos na Fase 1 — este arquivo é o que
impede que voltem.

O defeito nunca foi "alguém esqueceu numa linha". Foi que a invariante existia
no caminho principal (`prompt_text`) e um campo mais novo não a herdou. Por isso
a trava é declarativa: cada campo de texto clínico tem uma política explícita, e
campo novo obriga decisão.

POR QUE POR CAMPO, E NÃO POR SITE DE `db.add`
Os mesmos modelos são instanciados em ~26 lugares, e mover um `db.add` de
arquivo é refatoração rotineira. O que não muda é o CAMPO: se
`InteractionResponse.response_text` existe, ele carrega saída de modelo e
precisa de DLP, esteja o `db.add` onde estiver.

AS POLÍTICAS
`DLP_ENTRADA`  - texto que o médico digitou. Mascarado com NER: é onde nome de
                 paciente aparece sem palavra-gatilho.
`DLP_SAIDA`    - texto gerado por modelo. Mascarado SEM NER, senão o NER come
                 nome de fármaco, de escore e epônimo — quebrando a retomada da
                 conversa e a extração de medicamentos. Ver D1 no plano.
`SEM_PII`      - campo que por construção não carrega dado de paciente
                 (identificador, enum, timestamp, nome de fármaco normalizado).
`FORA_DE_ESCOPO` - carrega risco, mas foi decidido conviver. Exige justificativa
                 escrita e entrada em `docs/debitos.md`.
"""

import ast
import pathlib

import pytest

RAIZ_APP = pathlib.Path(__file__).resolve().parents[1] / "app"

DLP_ENTRADA = "dlp_com_ner"
DLP_SAIDA = "dlp_sem_ner"
SEM_PII = "sem_pii"
FORA_DE_ESCOPO = "fora_de_escopo"

# Campo a campo. Ao acrescentar coluna de texto num modelo que guarda conteúdo
# clínico, declare-a aqui — `test_todo_campo_de_texto_tem_politica` falha
# enquanto isso não for feito.
POLITICA_DE_CAMPO: dict[tuple[str, str], str] = {
    # ── O que o médico digitou ───────────────────────────────────────────
    ("Interaction", "prompt_text"): DLP_ENTRADA,
    ("FileExtraction", "extracted_text"): DLP_ENTRADA,
    ("FileExtraction", "file_name"): DLP_ENTRADA,
    ("Folder", "clinical_context"): DLP_ENTRADA,
    # ── O que o modelo gerou ─────────────────────────────────────────────
    ("InteractionResponse", "response_text"): DLP_SAIDA,
    # ── Sem PII por construção ───────────────────────────────────────────
    # Perguntas de clarificação geradas quando o prompt está vago. São saída de
    # modelo, mas derivadas de um prompt JÁ sanitizado, e o que o modelo produz
    # aqui é pergunta genérica ("Qual a idade do paciente?", "Há uso prévio de
    # anticoagulante?") — não devolve dado que não recebeu. Mesmo raciocínio de
    # `Conversation.title`: herda o mascaramento da origem.
    ("Interaction", "clarification_questions"): SEM_PII,
    ("Interaction", "mode"): SEM_PII,
    ("Interaction", "triage_category"): SEM_PII,
    ("Interaction", "feature"): SEM_PII,
    ("Interaction", "input_type"): SEM_PII,
    ("Interaction", "status"): SEM_PII,
    # Preenchidos pelo detector de especialidade a partir de uma taxonomia
    # fechada — não é texto livre.
    ("Interaction", "specialty_detected"): SEM_PII,
    ("Interaction", "topic_detected"): SEM_PII,
    ("InteractionResponse", "model_used"): SEM_PII,
    ("Conversation", "feature"): SEM_PII,
    ("Folder", "folder_kind"): SEM_PII,
    # Nome que o médico dá à pasta. É rótulo de organização, não evolução
    # clínica — e é exibido na navegação, onde mascarar quebraria o uso.
    ("Folder", "name"): SEM_PII,
    ("FileExtraction", "file_type"): SEM_PII,
    ("FileExtraction", "image_media_type"): SEM_PII,
    ("InteractionMedication", "atc_code"): SEM_PII,
    ("InteractionMedication", "source"): SEM_PII,
    ("MessageEmbedding", "role"): SEM_PII,
    ("PharmaAlert", "alert_color"): SEM_PII,
    ("PharmaAlert", "source_api"): SEM_PII,
    ("SemanticCache", "mode"): SEM_PII,
    # Mensagem de exceção de provider. Não é texto clínico, e é usada como FLAG
    # de controle em cinco lugares (`conversation_history`, `folder_context`,
    # `data_subject_service`, `conversations`): trocar `None` por string
    # transformaria resposta boa em registro de falha e a sumiria do histórico.
    ("InteractionResponse", "error_message"): SEM_PII,
    # Nome de fármaco já normalizado pelo extrator.
    ("InteractionMedication", "medication_raw"): SEM_PII,
    ("InteractionMedication", "medication_normalized"): SEM_PII,
    # ── Decidido conviver ────────────────────────────────────────────────
    # Título derivado das primeiras palavras do prompt JÁ sanitizado
    # (`_make_title` recebe `sanitized_prompt`). Herda o mascaramento da origem.
    ("Conversation", "title"): SEM_PII,
    # Citações, contagens de ferramenta e metadados do PubMed. Passar NER aqui
    # mascararia nome de AUTOR de artigo publicado, degradando as referências
    # sem ganho de privacidade — o conteúdo é bibliográfico, não do paciente.
    ("InteractionResponse", "extra_metadata"): SEM_PII,
    # Alerta de interação medicamentosa, texto da base PharmaDB (não do médico).
    ("PharmaAlert", "description"): SEM_PII,
    # Justificativa que o médico escreve ao sobrepor um alerta. É texto livre
    # dele — entra pelo mesmo caminho do prompt e é sanitizada na origem.
    ("PharmaAlert", "doctor_justification"): DLP_ENTRADA,
    # Embeddings da busca por pasta. FICOU DE FORA da Fase 1 de propósito:
    # sanitizar agora criaria espaço vetorial misto (registros antigos crus
    # convivendo com novos mascarados), degradando a similaridade até
    # rotacionarem. Exige backfill — ver D1 em `docs/plano-correcoes.md`.
    ("MessageEmbedding", "content"): FORA_DE_ESCOPO,
    # Prompt normalizado por LLM, usado como chave do cache semântico. A
    # cacheabilidade é barrada antes por `pode_usar_cache`, e a flag está
    # desligada — ver débito 16 e T9 do plano.
    ("SemanticCache", "normalized_prompt"): FORA_DE_ESCOPO,
    # O payload devolvido num hit — incluindo `response_text`, servido a OUTRO
    # médico. Sanitizado NA ORIGEM (`full_text` já vai mascarado para
    # `store_response`), não aqui: ver T2 no plano.
    ("SemanticCache", "response_json"): SEM_PII,
    # A imagem crua do exame, em base64. Mascarar pixel exigiria OCR — é decisão
    # de base legal, não de engenharia. Registrada como débito 17.
    ("FileExtraction", "image_base64"): FORA_DE_ESCOPO,
}

# Onde cada `FORA_DE_ESCOPO` está justificado por escrito. O nome da classe não
# aparece na prosa dos documentos (eles falam "cache semântico", "imagem crua do
# exame"), então casar símbolo com texto daria falso negativo — a âncora é o
# trecho que precisa existir.
REGISTRO_DO_QUE_FICOU_FORA: dict[tuple[str, str], str] = {
    ("MessageEmbedding", "content"): "espaço vetorial misto",
    ("SemanticCache", "normalized_prompt"): "Cuidado ao religar",
    ("FileExtraction", "image_base64"): "Imagem crua do exame",
}

# Modelos cujos campos de texto entram nesta política. Outros (User, Article,
# AuditLog...) não guardam conteúdo clínico de paciente.
MODELOS_CLINICOS = {
    "Interaction",
    "InteractionResponse",
    "InteractionMedication",
    "FileExtraction",
    "MessageEmbedding",
    "PharmaAlert",
    "SemanticCache",
    "Conversation",
    "Folder",
}

# Colunas que nunca carregam texto: chaves, números, datas, booleanos.
_TIPOS_NAO_TEXTUAIS = {
    "UUID", "Integer", "BigInteger", "Boolean", "DateTime", "Date",
    "Numeric", "Float", "ForeignKey", "Enum", "Vector", "ARRAY",
}


def _colunas_de_texto_por_modelo() -> dict[str, set[str]]:
    """Lê os modelos ORM e devolve as colunas capazes de guardar texto."""
    fonte = (RAIZ_APP / "models" / "models.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    encontrados: dict[str, set[str]] = {}
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ClassDef) or no.name not in MODELOS_CLINICOS:
            continue
        campos: set[str] = set()
        for corpo in no.body:
            if not isinstance(corpo, ast.AnnAssign) or not isinstance(corpo.target, ast.Name):
                continue
            anotacao = ast.unparse(corpo.annotation)
            valor = ast.unparse(corpo.value) if corpo.value else ""
            # `Mapped[str]` com coluna Text/String, ou JSONB de metadados.
            e_texto = ("str" in anotacao and "Text" in valor) or "String" in valor
            e_json = "JSONB" in valor or "JSON" in valor
            if (e_texto or e_json) and not any(t in valor for t in _TIPOS_NAO_TEXTUAIS):
                campos.add(corpo.target.id)
        if campos:
            encontrados[no.name] = campos
    return encontrados


# ── As travas bidirecionais ──────────────────────────────────────────────


def test_todo_campo_de_texto_tem_politica():
    """
    Coluna de texto nova num modelo clínico precisa de decisão explícita.

    Sem isto, um campo novo entra guardando prontuário em claro — que foi
    exatamente o que aconteceu com `FileExtraction.extracted_text` e com
    `InteractionResponse.response_text`, cada um por um caminho diferente.
    """
    sem_politica: list[str] = []
    for modelo, campos in _colunas_de_texto_por_modelo().items():
        for campo in campos:
            if (modelo, campo) not in POLITICA_DE_CAMPO:
                sem_politica.append(f"{modelo}.{campo}")

    assert not sem_politica, (
        "Campo(s) de texto sem política de DLP declarada:\n  "
        + "\n  ".join(sorted(sem_politica))
        + "\n\nDeclare em tests/test_politica_de_dlp_na_escrita.py como "
        "DLP_ENTRADA, DLP_SAIDA, SEM_PII ou FORA_DE_ESCOPO.\n"
        "Se o campo guarda texto que o médico digitou ou que o modelo gerou, "
        "ele precisa passar por `sanitize_prompt_async` ANTES do `db.add`."
    )


def test_politica_nao_referencia_campo_inexistente():
    """Campo removido deve sair do mapa, senão ele vira ficção."""
    existentes = {
        (modelo, campo)
        for modelo, campos in _colunas_de_texto_por_modelo().items()
        for campo in campos
    }
    fantasmas = [
        f"{m}.{c}" for (m, c) in POLITICA_DE_CAMPO if (m, c) not in existentes
    ]
    assert not fantasmas, (
        f"POLITICA_DE_CAMPO referencia campos que não existem mais: {sorted(fantasmas)}"
    )


# ── A verificação de comportamento ───────────────────────────────────────


ARQUIVOS_QUE_ESCREVEM_TEXTO_CLINICO = (
    "api/v1/endpoints/uploads.py",
    "api/v1/endpoints/folders.py",
    "services/orquestrador_service.py",
    "services/orquestrador_stream_service.py",
    "services/agregador_service.py",
)


@pytest.mark.parametrize("relativo", ARQUIVOS_QUE_ESCREVEM_TEXTO_CLINICO)
def test_arquivo_que_grava_texto_clinico_chama_o_dlp(relativo):
    """
    Todo arquivo que instancia modelo com campo `DLP_ENTRADA`/`DLP_SAIDA` tem de
    chamar o DLP. É verificação grossa — a fina é `tests/test_dlp_na_escrita.py`,
    que confere o EFEITO sobre texto com PII de verdade.
    """
    fonte = (RAIZ_APP / relativo).read_text(encoding="utf-8")
    chamadas = {
        no.func.id if isinstance(no.func, ast.Name) else no.func.attr
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name | ast.Attribute)
    }

    assert chamadas & {"sanitize_prompt_async", "sanitize_prompt", "_limpar_evolucao"}, (
        f"{relativo} grava texto clínico mas não chama o DLP em lugar nenhum."
    )


def test_saida_de_modelo_e_sanitizada_sem_ner():
    """
    Onde a saída do modelo é sanitizada, tem de ser com `use_ner=False`.

    Com NER, o mascaramento come nome de fármaco ("Xarelto"), de escore
    ("HAS-BLED") e epônimo ("Crohn") — e como o histórico realimenta o modelo nos
    turnos seguintes, a conversa perde o caso do turno 1. É a regressão que o
    teste de retomada clínica cobre pelo efeito; esta é a trava estrutural.
    """
    arquivos_de_saida = (
        "services/orquestrador_service.py",
        "services/orquestrador_stream_service.py",
        "services/agregador_service.py",
    )

    faltando: list[str] = []
    for relativo in arquivos_de_saida:
        fonte = (RAIZ_APP / relativo).read_text(encoding="utf-8")
        for no in ast.walk(ast.parse(fonte)):
            if not isinstance(no, ast.Call):
                continue
            nome = no.func.id if isinstance(no.func, ast.Name) else getattr(no.func, "attr", "")
            if nome != "sanitize_prompt_async":
                continue
            # A chamada de ENTRADA (o prompt) usa NER e é legítima: o alvo aqui
            # é só a que trata resposta de modelo. Distinguimos pelo argumento.
            arg = ast.unparse(no.args[0]) if no.args else ""
            trata_saida = any(
                marca in arg for marca in ("agent_response", "full_text", "result.text")
            )
            se_ner_desligado = any(
                kw.arg == "use_ner" and ast.unparse(kw.value) == "False"
                for kw in no.keywords
            )
            if trata_saida and not se_ner_desligado:
                faltando.append(f"{relativo}: sanitize_prompt_async({arg})")

    assert not faltando, (
        "Saída de modelo sanitizada COM NER — isso mascara nome de fármaco e "
        "epônimo, quebrando a retomada clínica:\n  " + "\n  ".join(faltando)
    )


def test_debitos_registra_o_que_ficou_fora_de_escopo():
    """
    `FORA_DE_ESCOPO` não pode ser esconderijo: o que ficou de fora tem de estar
    escrito em `docs/debitos.md`, senão vira decisão informal que ninguém lembra.
    """
    fora = [(m, c) for (m, c), p in POLITICA_DE_CAMPO.items() if p == FORA_DE_ESCOPO]
    assert fora, "Nenhum campo fora de escopo — atualize este teste se isso mudou."

    sem_ancora = [f"{m}.{c}" for m, c in fora if (m, c) not in REGISTRO_DO_QUE_FICOU_FORA]
    assert not sem_ancora, (
        "Campo marcado como FORA_DE_ESCOPO sem entrada em "
        f"REGISTRO_DO_QUE_FICOU_FORA: {sem_ancora}"
    )

    debitos = (RAIZ_APP.parent / "docs" / "debitos.md").read_text(encoding="utf-8")
    plano = (RAIZ_APP.parent / "docs" / "plano-correcoes.md").read_text(encoding="utf-8")
    documentado = debitos + plano

    nao_registrados = [
        f"{m}.{c} (esperava encontrar {trecho!r})"
        for (m, c), trecho in REGISTRO_DO_QUE_FICOU_FORA.items()
        if trecho not in documentado
    ]
    assert not nao_registrados, (
        "Decisão de conviver com o risco sem registro em docs/debitos.md nem em "
        "docs/plano-correcoes.md:\n  " + "\n  ".join(nao_registrados)
    )
