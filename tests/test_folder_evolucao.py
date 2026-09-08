"""
Evolução clínica da pasta: o contexto que o médico DECLARA.

Diferente do contexto por similaridade em `test_folder_context.py`, que é
material de apoio e pode ser de outro paciente: isto é escrito pelo médico
sobre o paciente daquela pasta, e entra na íntegra em toda mensagem dela.

O que este arquivo protege, em ordem de importância:

1. Renomear uma pasta NÃO apaga a evolução. O `PUT /folders/{id}` era um
   endpoint de rename puro, e a versão atual do frontend manda só `{"name":...}`.
   Se o campo ausente virasse NULL, o médico perderia a evolução do paciente ao
   corrigir um typo no nome da pasta — sem aviso e sem confirmação.
2. Evolução de pasta alheia não é legível nem gravável.
3. O texto tem teto: ele é enviado em TODA mensagem, então o tamanho é custo
   recorrente.
"""

import pytest

from app.api.v1.endpoints.folders import MAX_CHARS_EVOLUCAO
from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


EVOLUCAO = "Jorge, 58a, HAS + DM2. Losartana 50mg 12/12h. Alergia a dipirona."


# ── Criação ──────────────────────────────────────────────────────────────────

async def test_cria_pasta_com_evolucao(client, user):
    resp = await client.post(
        "/api/v1/folders",
        json={"name": "Paciente Jorge", "clinical_context": EVOLUCAO},
        headers=auth_headers(user),
    )

    assert resp.status_code == 201
    assert resp.json()["clinical_context"] == EVOLUCAO


async def test_cria_pasta_sem_evolucao_continua_funcionando(client, user):
    """Uma pasta pode ser só organização por tema — o campo é opcional."""
    resp = await client.post(
        "/api/v1/folders",
        json={"name": "Cardiologia"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 201
    assert resp.json()["clinical_context"] is None


async def test_evolucao_so_de_espacos_vira_nulo(client, user):
    """Guardar "" e None como estados diferentes não significaria nada para
    quem lê, e daria dois valores para o mesmo "não há evolução"."""
    resp = await client.post(
        "/api/v1/folders",
        json={"name": "Pasta", "clinical_context": "   \n  "},
        headers=auth_headers(user),
    )

    assert resp.json()["clinical_context"] is None


async def test_evolucao_acima_do_teto_e_recusada_com_422(client, user):
    """O texto vai em toda mensagem da pasta: o tamanho é custo recorrente.

    E a recusa é 422 explicativo, não 500 do driver — por isso o limite está na
    API e não na coluna, que é TEXT.
    """
    resp = await client.post(
        "/api/v1/folders",
        json={"name": "Pasta", "clinical_context": "x" * (MAX_CHARS_EVOLUCAO + 1)},
        headers=auth_headers(user),
    )

    assert resp.status_code == 422


# ── Edição ───────────────────────────────────────────────────────────────────

async def test_renomear_sem_mandar_evolucao_nao_a_apaga(client, user, folder_factory):
    """O teste mais importante deste arquivo.

    O frontend atual manda apenas `{"name": ...}` neste endpoint. Se o campo
    ausente fosse tratado como "apagar", corrigir um typo no nome da pasta
    destruiria a evolução do paciente — silenciosamente.
    """
    pasta = await folder_factory(user, name="Jorge", clinical_context=EVOLUCAO)

    resp = await client.put(
        f"/api/v1/folders/{pasta.id}",
        json={"name": "Jorge Silva"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 200
    assert resp.json()["name"] == "Jorge Silva"
    assert resp.json()["clinical_context"] == EVOLUCAO, (
        "renomear a pasta apagou a evolução do paciente"
    )


async def test_edita_a_evolucao(client, user, folder_factory):
    pasta = await folder_factory(user, name="Jorge", clinical_context=EVOLUCAO)
    novo = EVOLUCAO + " Iniciada metformina 850mg."

    resp = await client.put(
        f"/api/v1/folders/{pasta.id}",
        json={"name": "Jorge", "clinical_context": novo},
        headers=auth_headers(user),
    )

    assert resp.json()["clinical_context"] == novo


async def test_string_vazia_limpa_a_evolucao_de_proposito(client, user, folder_factory):
    """Ausente = não mexa; vazio = limpar. O médico precisa conseguir apagar."""
    pasta = await folder_factory(user, name="Jorge", clinical_context=EVOLUCAO)

    resp = await client.put(
        f"/api/v1/folders/{pasta.id}",
        json={"name": "Jorge", "clinical_context": ""},
        headers=auth_headers(user),
    )

    assert resp.json()["clinical_context"] is None


# ── Isolamento ───────────────────────────────────────────────────────────────

async def test_nao_le_evolucao_de_pasta_alheia(client, user_factory, folder_factory):
    dono = await user_factory(email="dono-evo@teste.com")
    intruso = await user_factory(email="intruso-evo@teste.com")
    await folder_factory(dono, name="Paciente", clinical_context="SEGREDO CLINICO")

    resp = await client.get("/api/v1/folders", headers=auth_headers(intruso))

    assert resp.status_code == 200
    assert "SEGREDO" not in resp.text


async def test_nao_escreve_evolucao_em_pasta_alheia(client, user_factory, folder_factory):
    dono = await user_factory(email="dono-evo2@teste.com")
    intruso = await user_factory(email="intruso-evo2@teste.com")
    pasta = await folder_factory(dono, name="Paciente", clinical_context=EVOLUCAO)

    resp = await client.put(
        f"/api/v1/folders/{pasta.id}",
        json={"name": "invadida", "clinical_context": "texto do intruso"},
        headers=auth_headers(intruso),
    )

    assert resp.status_code == 404


# ── Tipo da pasta ────────────────────────────────────────────────────────────

async def test_cria_pasta_geral(client, user):
    resp = await client.post(
        "/api/v1/folders",
        json={"name": "Artigos para ler", "folder_kind": "general",
              "clinical_context": "Revisar guidelines de 2026"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 201
    assert resp.json()["folder_kind"] == "general"


async def test_pasta_nasce_clinica_por_padrao(client, user):
    """As pastas da 009 foram criadas quando o campo era descrito como evolução
    de paciente — o default preserva o sentido do que já está gravado."""
    resp = await client.post(
        "/api/v1/folders", json={"name": "Sem tipo"}, headers=auth_headers(user)
    )

    assert resp.json()["folder_kind"] == "clinical"


async def test_tipo_invalido_e_recusado(client, user):
    resp = await client.post(
        "/api/v1/folders",
        json={"name": "Pasta", "folder_kind": "qualquer_coisa"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 422


async def test_renomear_sem_mandar_tipo_nao_reclassifica(client, user, folder_factory):
    """Mesma regra do `clinical_context`: um cliente que só renomeia não pode
    reclassificar a pasta sem querer."""
    pasta = await folder_factory(user, name="Estudos")
    pasta.folder_kind = "general"

    resp = await client.put(
        f"/api/v1/folders/{pasta.id}",
        json={"name": "Estudos 2026"},
        headers=auth_headers(user),
    )

    assert resp.json()["folder_kind"] == "general", (
        "renomear reclassificou a pasta como clínica"
    )


async def test_muda_o_tipo_da_pasta(client, user, folder_factory):
    pasta = await folder_factory(user, name="Pasta", clinical_context=EVOLUCAO)

    resp = await client.put(
        f"/api/v1/folders/{pasta.id}",
        json={"name": "Pasta", "folder_kind": "general"},
        headers=auth_headers(user),
    )

    assert resp.json()["folder_kind"] == "general"
