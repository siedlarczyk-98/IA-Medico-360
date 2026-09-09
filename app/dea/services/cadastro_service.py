"""
Cadastro e verificação de DEA — a escrita pública do módulo.

Duas operações, e uma regra de promoção que liga as duas.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dea.schemas.dea_schemas import CadastroRequest, VerificacaoRequest
from app.models.dea import (
    Dispositivo,
    Local,
    OrigemEnum,
    ResultadoVerificacaoEnum,
    StatusDispositivoEnum,
    Verificacao,
)
from app.models.models import utcnow

# Casas decimais do arredondamento usado para detectar duplicata. Quatro casas
# são ~11 m — a granularidade de "mesmo prédio".
CASAS_DEDUPE = 4


def arredondar(valor: float) -> float:
    return round(valor, CASAS_DEDUPE)


async def criar(
    db: AsyncSession,
    dados: CadastroRequest,
    *,
    ip_hash: str | None,
    nascer_pendente: bool = True,
) -> tuple[Local, Dispositivo]:
    """Cria local + primeiro dispositivo.

    Os dois juntos porque, do ponto de vista de quem cadastra, é um ato só: "tem
    um DEA ali". A separação em duas tabelas é interna.
    """
    local = Local(
        id=uuid.uuid4(),
        nome=dados.nome.strip(),
        endereco=dados.endereco.strip() if dados.endereco else None,
        cidade=dados.cidade.strip() if dados.cidade else None,
        uf=dados.uf.strip().upper() if dados.uf else None,
        latitude=dados.latitude,
        longitude=dados.longitude,
        lat_arredondada=arredondar(dados.latitude),
        lon_arredondada=arredondar(dados.longitude),
        horario_texto=dados.horario_texto.strip() if dados.horario_texto else None,
        acesso_24h=dados.acesso_24h,
    )
    db.add(local)
    await db.flush()

    dispositivo = Dispositivo(
        id=uuid.uuid4(),
        local_id=local.id,
        descricao_localizacao=(dados.descricao_localizacao.strip() if dados.descricao_localizacao else None),
        acesso=dados.acesso.value,
        # Sempre `pendente`: mesmo um cadastro impecável é a palavra de uma
        # pessoa só. Aparece no mapa imediatamente, marcado como não confirmado.
        status=(StatusDispositivoEnum.PENDENTE.value if nascer_pendente else StatusDispositivoEnum.ATIVO.value),
        origem=OrigemEnum.COLABORATIVO.value,
        criado_por_ip_hash=ip_hash,
    )
    db.add(dispositivo)
    await db.flush()

    return local, dispositivo


async def encontrar_duplicata(db: AsyncSession, *, latitude: float, longitude: float) -> Local | None:
    """Local já cadastrado na mesma célula de ~11 m.

    Serve para o router avisar quem cadastra ("já existe um registro aqui —
    quer confirmar aquele em vez de criar outro?"), não para recusar. Recusar
    seria pior: dois DEAs no mesmo saguão são plausíveis, e perder o segundo é
    perder informação real.
    """
    resultado = await db.execute(
        select(Local)
        .where(Local.lat_arredondada == arredondar(latitude))
        .where(Local.lon_arredondada == arredondar(longitude))
        .limit(1)
    )
    return resultado.scalar_one_or_none()


async def registrar_verificacao(
    db: AsyncSession,
    dispositivo: Dispositivo,
    dados: VerificacaoRequest,
    *,
    ip_hash: str | None,
) -> Dispositivo:
    """Registra uma visita e atualiza os contadores materializados.

    ## A regra de promoção

    Um dispositivo `pendente` vira `ativo` quando alguém **de outra origem**
    confirma. A condição de origem diferente é o que impede o caso trivial de
    fraude: cadastrar um pin falso e confirmá-lo em seguida da mesma máquina.

    Não é uma barreira forte — o `ip_hash` deriva de um IP que hoje pode ser
    forjado (ver `app/dea/services/antivandalismo.py`) — mas é a diferença entre
    exigir alguma intenção e não exigir nenhuma.

    Duas contestações consecutivas mandam o dispositivo para `nao_encontrado`:
    ele **continua no mapa**, marcado, porque "duas pessoas procuraram e não
    acharam" é informação útil para a terceira. Só sai da listagem quando
    alguém o marca como removido de fato.
    """
    verificacao = Verificacao(
        id=uuid.uuid4(),
        dispositivo_id=dispositivo.id,
        resultado=dados.resultado.value,
        observacao=dados.observacao.strip() if dados.observacao else None,
        ip_hash=ip_hash,
    )
    db.add(verificacao)

    agora = utcnow()
    dispositivo.ultima_verificacao_em = agora

    if dados.resultado is ResultadoVerificacaoEnum.ENCONTRADO:
        dispositivo.verificacoes_positivas += 1

        origem_diferente = (
            ip_hash is None or dispositivo.criado_por_ip_hash is None or ip_hash != dispositivo.criado_por_ip_hash
        )
        if dispositivo.status == StatusDispositivoEnum.PENDENTE.value and origem_diferente:
            dispositivo.status = StatusDispositivoEnum.ATIVO.value
        elif dispositivo.status == StatusDispositivoEnum.NAO_ENCONTRADO.value:
            # Alguém achou de novo: pode ter sido reinstalado, ou quem não achou
            # procurou no lugar errado. Volta para pendente, não direto para
            # ativo — o histórico de contestação continua pesando na confiança.
            dispositivo.status = StatusDispositivoEnum.PENDENTE.value

    elif dados.resultado is ResultadoVerificacaoEnum.NAO_ENCONTRADO:
        dispositivo.verificacoes_negativas += 1
        if dispositivo.verificacoes_negativas >= 2:
            dispositivo.status = StatusDispositivoEnum.NAO_ENCONTRADO.value

    else:  # REMOVIDO — alguém afirma que o aparelho não está mais lá.
        dispositivo.verificacoes_negativas += 1
        dispositivo.status = StatusDispositivoEnum.REMOVIDO.value

    await db.flush()
    return dispositivo
