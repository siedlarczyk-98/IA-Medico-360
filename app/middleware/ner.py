"""
Médico 360 — Detecção de nomes próprios por NER (spaCy pt_core_news_sm).

Complementa as heurísticas de regex do DLP, que só mascaram nomes precedidos de
palavra-gatilho ("paciente X", "Dr. Y"). O NER pega o caso que a regex não cobre:
"João Silva, 45 anos, hipertenso" — nome solto no início da frase.

POR QUE HÁ FILTROS EM CIMA DO MODELO
------------------------------------
O modelo é treinado em corpus jornalístico, não clínico, e marca como PER uma
quantidade grande de terminologia médica. Medido neste projeto:

    "Doença de Chagas"    -> PER        "Mal de Parkinson"  -> PER
    "Síndrome de Down"    -> PER        "Manobra de Valsalva" -> PER
    "hipertenso"          -> PER        "Crohn" / "Romberg" -> PER

Como o DLP não tem passo de re-identificação (o texto mascarado vai ao LLM e a
resposta volta com o placeholder), um falso positivo apaga o termo clínico em
definitivo e degrada a resposta. Por isso um span PER só é aceito se passar por
todos os filtros de `_is_person`, calibrados sobre os erros acima.
"""

import logging
import re

logger = logging.getLogger(__name__)

MODEL_NAME = "pt_core_news_sm"

_nlp = None
_load_failed = False

# Núcleos de epônimo: "<termo clínico> de <Nome>" quase nunca é uma pessoa no
# contexto de uso — é uma doença, escala, manobra ou sinal.
_EPONIMO_NUCLEOS = (
    r"doen[çc]a|s[íi]ndrome|mal|manobra|sinal|escala|teste|prova|[íi]ndice|"
    r"crit[ée]rios?|classifica[çc][ãa]o|escore|score|reflexo|t[ée]cnica|m[ée]todo|"
    r"fen[ôo]meno|tr[íi]ade|les[ãa]o|tumor|c[ée]lulas?|corp[úu]sculo|ndice|"
    r"posi[çc][ãa]o|incid[êe]ncia|proje[çc][ãa]o|linha|[âa]ngulo|ponto|regra|lei"
)

# O span devolvido pelo modelo já vem com o núcleo colado ("Doença de Chagas").
_SPAN_EPONIMO = re.compile(rf"^(?:{_EPONIMO_NUCLEOS})\b", re.IGNORECASE)

# Ou o núcleo ficou logo antes do span ("sinal de" + "Blumberg").
_ANTES_EPONIMO = re.compile(
    rf"(?:{_EPONIMO_NUCLEOS})\s+(?:de|da|do|dos|das)\s+$", re.IGNORECASE
)

# Epônimos que aparecem sem núcleo à frente ("paciente com Chagas crônica").
# Só precisa cobrir os multi-token, já que spans de um token são rejeitados.
_EPONIMOS = {
    "wernicke korsakoff", "creutzfeldt jakob", "charcot marie tooth",
    "ehlers danlos", "guillain barré", "guillain barre", "henoch schonlein",
    "henoch schönlein", "peutz jeghers", "sturge weber", "von willebrand",
    "osgood schlatter", "legg calve perthes", "prader willi", "klippel trenaunay",
    "rendu osler weber", "churg strauss", "goodpasture", "albert einstein",
}

_TITULOS = {"dr", "dra", "doutor", "doutora", "prof", "professor", "professora", "sr", "sra"}

# Token com cara de nome próprio: maiúscula seguida de minúsculas ("Silva").
# Exclui siglas ("NYHA", "II") e palavras comuns ("estadio").
_TOKEN_NOME = re.compile(r"\b[A-ZÀ-Ÿ][a-zà-ÿ]{1,}\b")

# Posologia logo após o span: "Losartana Potássica 50mg" é medicamento, não pessoa.
_APOS_DOSE = re.compile(
    r"^\s*\d+[\d.,]*\s*(?:mg|mcg|µg|g|kg|ml|mL|l|UI|ui|%|mEq|mmol|cp|comp|gts|amp)\b",
    re.IGNORECASE,
)


def _load():
    """Carrega o modelo uma vez. Falha de carga desliga o NER sem derrubar o DLP."""
    global _nlp, _load_failed
    if _nlp is not None or _load_failed:
        return _nlp
    try:
        import spacy

        # Só o NER é necessário; desligar o resto do pipeline corta a latência.
        _nlp = spacy.load(MODEL_NAME, disable=["lemmatizer", "attribute_ruler"])
    except Exception as e:
        _load_failed = True
        logger.error(
            "NER indisponível (%s): nomes sem palavra-gatilho não serão mascarados. %s",
            MODEL_NAME,
            e,
        )
    return _nlp


def warmup() -> bool:
    """Pré-carrega o modelo no startup, para a 1ª requisição não pagar o custo."""
    return _load() is not None


def _normalizar(texto: str) -> str:
    return re.sub(r"[^a-zà-ÿ]+", " ", texto.lower()).strip()


def _is_person(span, text: str) -> bool:
    """Filtra os falsos positivos clínicos descritos no docstring do módulo."""
    termo = span.text.strip()

    # 1. Nome próprio começa com maiúscula — descarta "hipertenso", "diabético".
    if not termo[:1].isupper():
        return False

    # 2. Construção de epônimo, com o núcleo dentro do span ou logo antes.
    if _SPAN_EPONIMO.match(termo):
        return False
    if _ANTES_EPONIMO.search(text[max(0, span.start_char - 40) : span.start_char]):
        return False

    # 3. Seguido de posologia => é medicamento.
    if _APOS_DOSE.match(text[span.end_char : span.end_char + 24]):
        return False

    # 4. Epônimos consagrados que aparecem sem núcleo à frente.
    palavras = [p for p in _normalizar(termo).split() if p not in _TITULOS]
    if " ".join(palavras) in _EPONIMOS:
        return False

    # 5. Exige ao menos dois tokens no formato de nome próprio (maiúscula + minúsculas).
    #    Descarta de uma vez:
    #      - token isolado, ambíguo demais ("Crohn", "Romberg", "Glasgow") — o caso
    #        legítimo de primeiro nome sozinho já é coberto pelas regex de gatilho;
    #      - siglas e estadiamentos ("NYHA III", "Hodgkin estadio II"), onde os
    #        tokens são caixa-alta ou minúsculos, não capitalizados.
    tokens_nome = [t for t in _TOKEN_NOME.findall(termo) if _normalizar(t) not in _TITULOS]
    if len(tokens_nome) < 2:
        return False

    return True


def find_person_spans(text: str) -> list[tuple[int, int]]:
    """Offsets (início, fim) de nomes de pessoa. Lista vazia se o NER indisponível."""
    nlp = _load()
    if nlp is None or not text.strip():
        return []

    try:
        doc = nlp(text)
    except Exception as e:
        logger.warning("NER falhou, seguindo apenas com as regex do DLP: %s", e)
        return []

    return [
        (ent.start_char, ent.end_char)
        for ent in doc.ents
        if ent.label_ == "PER" and _is_person(ent, text)
    ]
