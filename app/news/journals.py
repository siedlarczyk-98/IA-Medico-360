"""
Registro central dos journals e sua agenda semanal.

ISSN é a chave usada para buscar no PubMed (fonte primária, estável e permitida).

weekday: 0=Segunda ... 6=Domingo (convenção do Python `date.weekday()`)

SOBRE O FALLBACK DE HTML QUE EXISTIA AQUI
A versão original deste módulo carregava, por journal, uma `fallback_url` e um
`fallback_parser` usados quando o PubMed não devolvia itens. O parser era
genérico: tratava qualquer `<a>` com mais de 25 caracteres como artigo, sem
abstract. O redator então escrevia um post inteiro a partir de um título solto
— o cenário de maior risco de alucinação num produto médico.

O fallback foi removido junto com a invariante "sem abstract, sem texto" em
`news_writer_service`. Coletar zero num dia de falha de indexação é melhor que
coletar lixo, e o alarme de `vigilancia_service` avisa quando isso acontece.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class JournalConfig:
    slug: str
    display_name: str
    weekday: int  # dia da semana em que este journal é coletado
    issn: str  # ISSN eletrônico, usado na busca PubMed


JOURNALS: list[JournalConfig] = [
    JournalConfig(slug="lancet", display_name="The Lancet", weekday=0, issn="1474-547X"),
    JournalConfig(slug="jama", display_name="JAMA", weekday=1, issn="1538-3598"),
    JournalConfig(slug="nature_medicine", display_name="Nature Medicine", weekday=2, issn="1546-170X"),
    JournalConfig(slug="nejm", display_name="New England Journal of Medicine", weekday=3, issn="1533-4406"),
    JournalConfig(slug="bmj", display_name="The BMJ", weekday=4, issn="1756-1833"),
]

JOURNALS_BY_SLUG: dict[str, JournalConfig] = {j.slug: j for j in JOURNALS}


def journal_for_today(weekday: int) -> JournalConfig | None:
    """Retorna o journal configurado para o dia da semana informado, se houver."""
    for journal in JOURNALS:
        if journal.weekday == weekday:
            return journal
    return None
