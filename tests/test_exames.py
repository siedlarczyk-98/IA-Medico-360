"""
Sessão de exames (Fase 5 / item 6).

O upload com visão já existia: PDF, DOCX, XLSX e imagem, com as imagens
passando por Claude Haiku. O que faltava era (a) um modo dedicado a DISCUTIR o
exame em vez de responder uma pergunta clínica genérica, (b) mais de um anexo
por mensagem, e (c) o anexo sobreviver no histórico.

O teste de posse cruzada é o mais importante: um `file_id` alheio misturado
entre arquivos próprios não pode passar.
"""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.core.prompts import MODE_SYSTEM_PROMPTS, build_orquestrador_prompt
from app.models.models import FileExtraction, Interaction
from app.services.file_extractor_service import (
    MAX_ANEXOS_POR_MENSAGEM,
    resolve_files_context,
)
from app.services.orquestrador_modes import (
    MODE_MODEL_MAP,
    MODES_REQUIRING_VISION,
    VALID_MODES,
    OrquestradorMode,
    upgrade_mode_for_attachments,
)
from app.services.orquestrador_shared import link_attachments


async def _anexo(db, dono, nome="laudo.pdf", tipo="pdf", texto="Texto do laudo.", imagem=None):
    extraction = FileExtraction(
        user_id=dono.id,
        file_name=nome,
        file_type=tipo,
        extracted_text=texto,
        image_base64=imagem,
        image_media_type="image/png" if imagem else None,
    )
    db.add(extraction)
    await db.flush()
    return extraction


# ── Registro do modo ─────────────────────────────────────────────────────────

def test_modo_de_exame_esta_registrado_em_todo_lugar():
    """Um modo meio-registrado falha em runtime, não no import."""
    assert "EXAM_REVIEW" in VALID_MODES
    assert MODE_MODEL_MAP[OrquestradorMode.EXAM_REVIEW] is not None
    assert "EXAM_REVIEW" in MODE_SYSTEM_PROMPTS


def test_todo_modo_com_llm_tem_prompt_de_sistema():
    """
    Guarda contra a duplicação que sobrou: o mapa de prompts vive em
    core/prompts e o de modelos em orquestrador_modes. Se divergirem, um modo
    responde com prompt de sistema vazio — sem erro nenhum.
    """
    com_modelo = {m for m, modelo in MODE_MODEL_MAP.items() if modelo}
    sem_prompt = com_modelo - MODE_SYSTEM_PROMPTS.keys()
    assert not sem_prompt, f"Modos com modelo mas sem prompt: {sem_prompt}"


def test_prompt_de_exame_manda_debater_e_nao_laudar():
    prompt = build_orquestrador_prompt("EXAM_REVIEW", None)
    assert "NÃO emite laudo" in prompt


def test_modo_de_exame_exige_visao():
    assert OrquestradorMode.EXAM_REVIEW in MODES_REQUIRING_VISION


def test_modo_de_exame_nao_cai_em_provider_sem_visao():
    """Perplexity não vê imagem — cair nele devolveria leitura de exame sem o exame."""
    from app.services.orquestrador_modes import FALLBACK_MODELS

    assert MODE_MODEL_MAP[OrquestradorMode.EXAM_REVIEW] != "sonar-pro"
    assert "sonar-pro" not in FALLBACK_MODELS[OrquestradorMode.EXAM_REVIEW]


# ── Promoção de modo por anexo ───────────────────────────────────────────────

def test_anexo_promove_raciocinio_clinico_para_exame():
    assert upgrade_mode_for_attachments("CLINICAL_REASONING", True) == "EXAM_REVIEW"


def test_sem_anexo_nada_e_promovido():
    assert upgrade_mode_for_attachments("CLINICAL_REASONING", False) == "CLINICAL_REASONING"


def test_anexo_nao_sequestra_pedido_de_produtividade():
    """Anexar um documento e pedir "resuma isto" continua sendo produtividade."""
    assert upgrade_mode_for_attachments("PRODUCTIVITY", True) == "PRODUCTIVITY"


def test_anexo_nao_muda_modo_farmacologico():
    assert upgrade_mode_for_attachments("PHARMA_CHECK", True) == "PHARMA_CHECK"


# ── Vários anexos ────────────────────────────────────────────────────────────
# (asyncio_mode=auto no pytest.ini — os testes async não precisam de marca, e
# uma marca de módulo pegaria também os síncronos acima.)


async def test_varios_anexos_entram_todos_no_prompt(db, user):
    laudo = await _anexo(db, user, "laudo.pdf", "pdf", "Opacidade em lobo superior.")
    labs = await _anexo(db, user, "hemograma.docx", "docx", "Hb 9.2 g/dL.")

    prompt, imagens, extracoes = await resolve_files_context(
        "o que acha?", [laudo.id, labs.id], user.id, db
    )

    assert "Opacidade em lobo superior." in prompt
    assert "Hb 9.2 g/dL." in prompt
    assert prompt.rstrip().endswith("o que acha?")
    assert len(extracoes) == 2
    assert imagens == []


async def test_ordem_dos_anexos_e_preservada(db, user):
    """"Compare o primeiro com o segundo" só faz sentido se a ordem se mantém."""
    primeiro = await _anexo(db, user, "a.pdf", "pdf", "PRIMEIRO EXAME")
    segundo = await _anexo(db, user, "b.pdf", "pdf", "SEGUNDO EXAME")

    prompt, _, _ = await resolve_files_context("compare", [primeiro.id, segundo.id], user.id, db)

    assert prompt.index("PRIMEIRO EXAME") < prompt.index("SEGUNDO EXAME")


async def test_imagem_vai_como_visao_e_documento_como_texto(db, user):
    imagem = await _anexo(db, user, "rx.png", "image", "Radiografia de tórax.", imagem="QUJD")
    laudo = await _anexo(db, user, "laudo.pdf", "pdf", "Laudo do radiologista.")

    prompt, imagens, _ = await resolve_files_context(
        "discuta", [imagem.id, laudo.id], user.id, db
    )

    assert len(imagens) == 1
    assert imagens[0]["base64"] == "QUJD"
    # O nome da imagem entra no texto para o modelo poder se referir a ela.
    assert "rx.png" in prompt
    assert "Laudo do radiologista." in prompt


async def test_sem_visao_a_imagem_vira_descricao_avisada(db, user):
    """O modelo precisa saber que está lendo descrição, não a imagem."""
    imagem = await _anexo(db, user, "rx.png", "image", "Radiografia de tórax.", imagem="QUJD")

    prompt, imagens, _ = await resolve_files_context(
        "discuta", [imagem.id], user.id, db, support_vision=False
    )

    assert imagens == []
    assert "a imagem em si não foi enviada" in prompt
    assert "Radiografia de tórax." in prompt


async def test_teto_de_anexos_por_mensagem(db, user):
    anexos = [await _anexo(db, user, f"{i}.pdf") for i in range(MAX_ANEXOS_POR_MENSAGEM + 1)]

    with pytest.raises(HTTPException) as erro:
        await resolve_files_context("x", [a.id for a in anexos], user.id, db)

    assert erro.value.status_code == 422


async def test_sem_anexo_o_prompt_passa_intacto(db, user):
    prompt, imagens, extracoes = await resolve_files_context("pergunta", [], user.id, db)
    assert (prompt, imagens, extracoes) == ("pergunta", [], [])


# ── Posse ────────────────────────────────────────────────────────────────────

async def test_arquivo_de_outro_usuario_da_404(db, user, user_factory):
    outro = await user_factory()
    alheio = await _anexo(db, outro, "sigiloso.pdf", texto="CONTEUDO SIGILOSO")

    with pytest.raises(HTTPException) as erro:
        await resolve_files_context("x", [alheio.id], user.id, db)

    assert erro.value.status_code == 404


async def test_arquivo_alheio_misturado_entre_proprios_tambem_da_404(db, user, user_factory):
    """O teste que mais importa: a checagem é por arquivo, não por lote."""
    outro = await user_factory()
    proprio = await _anexo(db, user, "meu.pdf")
    alheio = await _anexo(db, outro, "dele.pdf", texto="CONTEUDO SIGILOSO")

    with pytest.raises(HTTPException) as erro:
        await resolve_files_context("x", [proprio.id, alheio.id], user.id, db)

    assert erro.value.status_code == 404


# ── Vínculo com a mensagem ───────────────────────────────────────────────────

async def _interacao(db, conv, dono):
    interaction = Interaction(
        conversation_id=conv.id,
        user_id=dono.id,
        feature="ORQUESTRADOR",
        mode="EXAM_REVIEW",
        prompt_text="discuta este exame",
        status="completed",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db.add(interaction)
    await db.flush()
    return interaction


async def test_anexos_ficam_vinculados_a_mensagem(db, user, conversation_factory):
    conv = await conversation_factory(user)
    interaction = await _interacao(db, conv, user)
    a = await _anexo(db, user, "a.pdf")
    b = await _anexo(db, user, "b.pdf")

    await link_attachments(db, user.id, interaction.id, [a.id, b.id])
    await db.flush()
    await db.refresh(a)
    await db.refresh(b)

    assert a.interaction_id == interaction.id
    assert b.interaction_id == interaction.id


async def test_vinculo_nao_carimba_arquivo_alheio(db, user, user_factory, conversation_factory):
    """Segunda barreira: mesmo recebendo um id alheio, o UPDATE filtra por dono."""
    outro = await user_factory()
    conv = await conversation_factory(user)
    interaction = await _interacao(db, conv, user)
    alheio = await _anexo(db, outro, "dele.pdf")

    await link_attachments(db, user.id, interaction.id, [alheio.id])
    await db.flush()
    await db.refresh(alheio)

    assert alheio.interaction_id is None


async def test_sem_anexos_o_vinculo_e_no_op(db, user, conversation_factory):
    conv = await conversation_factory(user)
    interaction = await _interacao(db, conv, user)
    await link_attachments(db, user.id, interaction.id, [])
    await link_attachments(db, user.id, interaction.id, None)


async def test_anexos_voltam_ao_reabrir_a_conversa(as_user, db, user, conversation_factory):
    """Era o que se perdia: ao recarregar, sobrava só o texto embutido."""
    conv = await conversation_factory(user)
    interaction = await _interacao(db, conv, user)
    anexo = await _anexo(db, user, "tomografia.png", "image", "TC de tórax.", imagem="QUJD")
    await link_attachments(db, user.id, interaction.id, [anexo.id])
    await db.flush()

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")
    assert resp.status_code == 200

    mensagem_usuario = [m for m in resp.json()["messages"] if m["role"] == "user"][0]
    assert len(mensagem_usuario["attachments"]) == 1
    assert mensagem_usuario["attachments"][0]["file_name"] == "tomografia.png"
    assert mensagem_usuario["attachments"][0]["file_type"] == "image"


async def test_historico_nao_devolve_o_base64_da_imagem(as_user, db, user, conversation_factory):
    """Só metadados: o base64 pesa e o texto extraído já está na mensagem."""
    conv = await conversation_factory(user)
    interaction = await _interacao(db, conv, user)
    anexo = await _anexo(db, user, "rx.png", "image", "RX.", imagem="BASE64SECRETO")
    await link_attachments(db, user.id, interaction.id, [anexo.id])
    await db.flush()

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")

    assert "BASE64SECRETO" not in resp.text


async def test_mensagem_antiga_sem_anexo_vem_com_lista_vazia(as_user, db, user, conversation_factory):
    """Não há backfill — conversas anteriores à migration 001 não têm vínculo."""
    conv = await conversation_factory(user)
    await _interacao(db, conv, user)

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")

    assert [m for m in resp.json()["messages"] if m["role"] == "user"][0]["attachments"] == []


# ── Aviso de extração sem texto ──────────────────────────────────────────────
# Débito #2. Antes, um PDF digitalizado era aceito em silêncio: o médico enviava,
# recebia resposta pobre e não tinha como saber que o exame nunca chegou ao
# modelo.

def test_pdf_sem_texto_gera_aviso():
    from app.services.file_extractor_service import PDF_SEM_TEXTO, aviso_de_extracao

    aviso = aviso_de_extracao(PDF_SEM_TEXTO, "pdf")

    assert aviso is not None
    # O aviso precisa dizer O QUE FAZER, não só que deu errado.
    assert "imagem" in aviso.lower()


def test_arquivo_vazio_gera_aviso():
    from app.services.file_extractor_service import aviso_de_extracao

    assert aviso_de_extracao("", "docx") is not None
    assert aviso_de_extracao("   \n  ", "xlsx") is not None


def test_extracao_bem_sucedida_nao_gera_aviso():
    """Avisar sempre treinaria o médico a ignorar o aviso."""
    from app.services.file_extractor_service import aviso_de_extracao

    assert aviso_de_extracao("Laudo: opacidade em lobo superior direito.", "pdf") is None


def test_imagem_nunca_gera_aviso_de_texto():
    """Imagem não passa por extração de texto — vai como visão."""
    from app.services.file_extractor_service import aviso_de_extracao

    assert aviso_de_extracao("", "image") is None


async def test_upload_de_pdf_escaneado_devolve_aviso(as_user, monkeypatch):
    """Ponta a ponta: o aviso chega ao cliente na resposta do upload."""
    from app.services import file_extractor_service as fes

    monkeypatch.setattr(fes, "extract_pdf", lambda _c: fes.PDF_SEM_TEXTO)
    monkeypatch.setattr(
        "app.api.v1.endpoints.uploads.extract_pdf", lambda _c: fes.PDF_SEM_TEXTO
    )
    monkeypatch.setattr(fes, "signature_matches", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "app.api.v1.endpoints.uploads.signature_matches", lambda *_a, **_k: True
    )

    resp = await as_user.post(
        "/api/v1/uploads/extract",
        files={"file": ("laudo_escaneado.pdf", b"%PDF-1.4 conteudo", "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    # O upload NAO falha: o medico decide se envia mesmo assim.
    assert corpo["file_id"]
    assert corpo["warning"] is not None
    assert "imagem" in corpo["warning"].lower()


async def test_upload_normal_nao_traz_aviso(as_user, monkeypatch):
    from app.services import file_extractor_service as fes

    monkeypatch.setattr(
        "app.api.v1.endpoints.uploads.extract_pdf", lambda _c: "Laudo com texto de verdade."
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.uploads.signature_matches", lambda *_a, **_k: True
    )
    _ = fes

    resp = await as_user.post(
        "/api/v1/uploads/extract",
        files={"file": ("laudo.pdf", b"%PDF-1.4 conteudo", "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["warning"] is None
