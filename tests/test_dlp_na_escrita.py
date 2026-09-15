"""
DLP na ESCRITA — o texto clínico não pode chegar ao banco em claro.

Até 2026-09-15 o DLP era unidirecional: mascarava o que ia PARA o provider e
deixava passar o que vinha DELE, além do texto extraído de anexo. Estes testes
travam a direção que faltava.

Três invariantes, nesta ordem de importância:

1. O que é gravado não carrega PII — nem o anexo, nem a resposta do modelo,
   nem o payload do cache semântico (que é servido a OUTROS médicos).
2. O que é gravado e o que é devolvido ao médico são o MESMO valor. Sanitizar só
   num dos dois faria o texto mudar diante dele ao reabrir a conversa.
3. O mascaramento não pode comer termo clínico. É a regressão que mata a
   retomada da conversa — ver `test_retomada_clinica_sobrevive`.
"""

import pytest

from app.middleware.dlp import sanitize_prompt_async

# Sintético, no formato que chega em produção. Nenhum dado real.
CABECALHO_DE_LAUDO = (
    "LABORATÓRIO CENTRAL — HEMOGRAMA COMPLETO\n"
    "Paciente: Joao da Silva\n"
    "CPF: 123.456.789-00\n"
    "Data de nascimento: 12/03/1964\n"
    "Telefone: (11) 99999-0000\n"
    "\n"
    "Hemoglobina 9.1 g/dL — abaixo do valor de referência.\n"
    "Plaquetas 95.000/mm3.\n"
)

FRAGMENTOS_PII = ["Joao da Silva", "123.456.789-00", "99999-0000"]


async def _limpo(texto: str, use_ner: bool = True) -> str:
    return (await sanitize_prompt_async(texto, use_ner=use_ner)).sanitized_text


# ── 1. O anexo era a única porta sem DLP ────────────────────────────────


async def test_texto_de_laudo_perde_a_pii_do_cabecalho():
    """
    O caminho de PDF/DOCX/XLSX gravava `extracted_text` direto do parser.
    Um laudo traz nome, CPF e data de nascimento no cabeçalho, e ficava
    180 dias no banco em claro.
    """
    resultado = await _limpo(CABECALHO_DE_LAUDO)

    for fragmento in FRAGMENTOS_PII:
        assert fragmento not in resultado, f"{fragmento!r} sobreviveu ao DLP"


async def test_o_achado_clinico_do_laudo_sobrevive():
    """
    O contraponto do teste acima: mascarar não pode destruir o exame. Se o DLP
    comer o resultado, o anexo perde a razão de existir.
    """
    resultado = await _limpo(CABECALHO_DE_LAUDO)

    assert "Hemoglobina" in resultado
    assert "9.1" in resultado
    assert "Plaquetas" in resultado


async def test_nome_de_arquivo_perde_o_nome_do_paciente():
    """`laudo_joao_da_silva.pdf` — o nome do arquivo costuma trazer o paciente."""
    resultado = await _limpo("Exame de Joao da Silva.pdf")

    assert "Joao da Silva" not in resultado


# ── 2. Resposta do modelo: gravada e devolvida têm de ser iguais ────────


async def test_resposta_do_modelo_e_sanitizada_sem_ner():
    """
    Na saída do modelo o DLP roda com `use_ner=False`. As regex continuam
    valendo — CPF, telefone, e-mail e data são o que de fato aparece ali.
    """
    resposta = (
        "Conforme os dados do paciente (CPF 123.456.789-00, tel (11) 99999-0000), "
        "a conduta é ajustar a dose."
    )
    resultado = await _limpo(resposta, use_ner=False)

    assert "123.456.789-00" not in resultado
    assert "99999-0000" not in resultado
    assert "ajustar a dose" in resultado


# ── 3. A regressão que mata a conversa ──────────────────────────────────


async def test_retomada_clinica_sobrevive():
    """
    CRITÉRIO DE ACEITAÇÃO DE D1.

    O histórico mascarado realimenta o modelo nos turnos seguintes
    (`conversation_history.py`). Se o mascaramento comer o dado clínico, o
    turno 5 perde o caso do turno 1 e a conversa deixa de fazer sentido.

    O nome do paciente PODE sumir — é irrelevante para a conduta. Idade,
    fármaco, valor de exame e escore NÃO podem.
    """
    turno_1 = (
        "Paciente Joao da Silva, 62 anos, em uso de varfarina, INR 4.8, "
        "escore HAS-BLED 3, com doença de Crohn."
    )

    resultado = await _limpo(turno_1, use_ner=False)

    # O que tem de sumir.
    assert "Joao da Silva" not in resultado

    # O que tem de ficar — sem isto a retomada quebra.
    assert "62 anos" in resultado
    assert "varfarina" in resultado
    assert "INR 4.8" in resultado
    assert "HAS-BLED 3" in resultado
    # Epônimo: nome próprio que é nome de doença. O NER comeria; por isso
    # `use_ner=False` na saída do modelo.
    assert "Crohn" in resultado


@pytest.mark.parametrize(
    "farmaco",
    ["Xarelto", "Eliquis", "Losartana", "Puran T4", "AAS"],
)
async def test_nome_de_farmaco_nao_e_mascarado_na_saida(farmaco):
    """
    Nome comercial de medicamento é nome próprio, e o NER o mascararia como
    `[NOME]`. Isso degradaria `extract_from_interaction`, que extrai os
    medicamentos justamente do texto da resposta.
    """
    resultado = await _limpo(f"Suspender {farmaco} por 5 dias antes do procedimento.", use_ner=False)

    assert farmaco in resultado


# ── 4. O NER continua valendo na ENTRADA ────────────────────────────────


async def test_entrada_do_medico_mantem_o_ner():
    """
    A mudança não pode afrouxar o caminho de entrada: é lá que o médico digita
    o nome do paciente sem palavra-gatilho, e é o furo real de setembro.
    """
    resultado = await _limpo("Maria Aparecida Souza chegou com dor torácica.", use_ner=True)

    assert "Maria Aparecida Souza" not in resultado
    assert "dor torácica" in resultado
