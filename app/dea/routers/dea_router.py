"""
Rotas do localizador de DEA.

**Este router é público de propósito.** Nenhum handler declara
`Depends(get_current_user)`, e é só isso que o torna aberto — não há middleware
de auth global neste projeto (ver `app/api/deps.py`).

Isso merece atenção porque falha para o lado errado: esquecer a dependency num
endpoint futuro que deveria ser protegido não produz erro nenhum, produz um
vazamento silencioso. Por isso existe um teste que afirma exatamente quais
rotas deste módulo respondem sem token — se alguém acrescentar uma rota
administrativa aqui, o teste é o lugar onde a decisão tem que aparecer.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.dea.repositories import locais_repository
from app.dea.schemas.dea_schemas import (
    LIMITE_MAXIMO,
    LIMITE_PADRAO,
    RAIO_MAXIMO_KM,
    RAIO_PADRAO_KM,
    BuscaResponse,
    CadastroRequest,
    CadastroResponse,
    DispositivoOut,
    LocalOut,
    VerificacaoRequest,
    VerificacaoResponse,
)
from app.dea.services import antivandalismo, cadastro_service
from app.dea.services import confianca as confianca_service
from app.dea.services.anonimato import hash_do_request
from app.models.dea import Dispositivo, StatusDispositivoEnum
from app.models.models import utcnow

router = APIRouter(prefix="/dea", tags=["dea"])

# Status que aparecem no mapa. `PENDENTE` entra: é etiqueta de confiança, não
# quarentena — segurar o pin até alguém confirmar mataria a contribuição
# justamente onde ela é mais valiosa, um bairro sem nenhum usuário ativo.
# `REMOVIDO` e `SPAM` ficam de fora, mas as linhas continuam no banco.
STATUS_VISIVEIS = (
    StatusDispositivoEnum.PENDENTE.value,
    StatusDispositivoEnum.ATIVO.value,
    StatusDispositivoEnum.NAO_ENCONTRADO.value,
)


def _limiares(settings: Settings) -> confianca_service.LimiaresConfianca:
    return confianca_service.LimiaresConfianca(
        dias_para_expirar=settings.dea_dias_para_expirar,
        dias_para_recente=settings.dea_dias_para_recente,
        confirmacoes_para_alta=settings.dea_confirmacoes_para_alta,
    )


def _para_saida(
    dispositivo: Dispositivo,
    limiares: confianca_service.LimiaresConfianca,
) -> DispositivoOut:
    agora = utcnow()
    avaliacao = confianca_service.avaliar(
        verificacoes_positivas=dispositivo.verificacoes_positivas,
        verificacoes_negativas=dispositivo.verificacoes_negativas,
        ultima_verificacao_em=dispositivo.ultima_verificacao_em,
        criado_em=dispositivo.criado_em,
        agora=agora,
        limiares=limiares,
    )
    return DispositivoOut(
        id=dispositivo.id,
        descricao_localizacao=dispositivo.descricao_localizacao,
        acesso=dispositivo.acesso,
        foto_url=dispositivo.foto_url,
        status=dispositivo.status,
        confianca=avaliacao.nivel.value,
        confirmacoes=avaliacao.confirmacoes,
        contestacoes=avaliacao.contestacoes,
        dias_desde_ultima_verificacao=avaliacao.dias_desde_ultima_verificacao,
    )


@router.get("/locais", response_model=BuscaResponse)
@limiter.limit("60/minute")
async def buscar_locais(
    request: Request,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    # Os tetos são a defesa contra raspagem: sem eles, `raio_km=20000` devolveria
    # o banco inteiro por uma rota aberta.
    raio_km: float = Query(default=RAIO_PADRAO_KM, gt=0, le=RAIO_MAXIMO_KM),
    limite: int = Query(default=LIMITE_PADRAO, gt=0, le=LIMITE_MAXIMO),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BuscaResponse:
    """Locais com DEA num raio, do mais próximo ao mais distante.

    Público: qualquer pessoa consulta, sem login. Numa emergência não há tempo
    para autenticação, e quem socorre raramente é quem tem a conta.
    """
    if not settings.dea_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Módulo indisponível")

    linhas = await locais_repository.buscar_por_raio(
        db,
        latitude=latitude,
        longitude=longitude,
        raio_km=raio_km,
        limite=limite,
    )
    if not linhas:
        return BuscaResponse(locais=[], total=0, raio_km=raio_km)

    # Uma consulta só para todos os dispositivos dos locais encontrados, em vez
    # de uma por local (N+1 numa rota que roda com o usuário esperando).
    ids = [linha["id"] for linha in linhas]
    resultado = await db.execute(
        select(Dispositivo).where(Dispositivo.local_id.in_(ids)).where(Dispositivo.status.in_(STATUS_VISIVEIS))
    )
    por_local: dict = {}
    for dispositivo in resultado.scalars():
        por_local.setdefault(dispositivo.local_id, []).append(dispositivo)

    limiares = _limiares(settings)
    locais = [
        LocalOut(
            id=linha["id"],
            nome=linha["nome"],
            endereco=linha["endereco"],
            cidade=linha["cidade"],
            uf=linha["uf"],
            latitude=linha["latitude"],
            longitude=linha["longitude"],
            horario_texto=linha["horario_texto"],
            acesso_24h=linha["acesso_24h"],
            distancia_km=round(linha["distancia_km"], 3),
            dispositivos=[_para_saida(d, limiares) for d in por_local.get(linha["id"], [])],
        )
        for linha in linhas
        # Um local cujos dispositivos foram todos removidos não é resultado útil.
        if por_local.get(linha["id"])
    ]

    return BuscaResponse(locais=locais, total=len(locais), raio_km=raio_km)


@router.post("/locais", response_model=CadastroResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def cadastrar_local(
    request: Request,
    body: CadastroRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CadastroResponse:
    """Cadastra um DEA. Público, sem login.

    O registro nasce `pendente` e **aparece no mapa imediatamente**, marcado como
    não confirmado. Segurar o pin até alguém validar mataria a contribuição
    exatamente onde ela é mais valiosa — um bairro onde ainda não há usuários
    para validar coisa alguma.
    """
    if not settings.dea_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Módulo indisponível")

    ip_hash = hash_do_request(request, settings.dea_ip_hash_salt)

    # Honeypot e tempo de preenchimento: respondemos 201 com um id inventado.
    #
    # Não é 400 de propósito. Bot que recebe erro adapta o payload e volta; bot
    # que recebe sucesso vai embora achando que funcionou. E se o sinal for um
    # falso positivo, a pessoa vê a mensagem de sucesso normal — o custo do erro
    # recai sobre nós (perdemos um cadastro), não sobre quem contribuiu de boa-fé.
    if antivandalismo.parece_bot(
        honeypot=body.website,
        segundos_de_preenchimento=body.segundos_de_preenchimento,
    ):
        return CadastroResponse(
            local_id=uuid.uuid4(),
            dispositivo_id=uuid.uuid4(),
            status=StatusDispositivoEnum.PENDENTE.value,
            mensagem="Registro recebido. Obrigado por contribuir.",
        )

    if await antivandalismo.densidade_excedida(
        db,
        latitude=body.latitude,
        longitude=body.longitude,
        maximo_por_hora=settings.dea_densidade_max_por_hora,
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitos cadastros nesta região na última hora. Tente novamente mais tarde.",
        )

    excedido = await antivandalismo.limite_por_origem_excedido(
        "cadastro", ip_hash, settings.dea_max_cadastros_por_hora, 3600
    )
    if excedido:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Limite de cadastros por hora atingido. Tente novamente mais tarde.",
        )
    # `None` = Redis indisponível. Aceita, mas o registro nasce pendente de
    # qualquer forma (o que já é o padrão) — nada se perde e nada entra sem
    # revisão. Ver `antivandalismo.limite_por_origem_excedido`.

    local, dispositivo = await cadastro_service.criar(db, body, ip_hash=ip_hash)
    await db.commit()

    return CadastroResponse(
        local_id=local.id,
        dispositivo_id=dispositivo.id,
        status=dispositivo.status,
        mensagem=(
            "Registro recebido e já visível no mapa como não confirmado. "
            "Ele passa a confirmado quando outra pessoa verificar no local."
        ),
    )


@router.post(
    "/dispositivos/{dispositivo_id}/verificacoes",
    response_model=VerificacaoResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def verificar_dispositivo(
    request: Request,
    dispositivo_id: uuid.UUID,
    body: VerificacaoRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VerificacaoResponse:
    """ "Estou aqui: encontrei / não encontrei." Público, sem login.

    É o motor de manutenção da base — sem um fluxo barato como este, o mapa vira
    um cemitério de pins do ano em que foi lançado.

    Note que **não há limite de densidade aqui**, só por origem: trinta alunos
    confirmando o mesmo DEA durante um curso de ACLS é o comportamento desejado,
    não um ataque.
    """
    if not settings.dea_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Módulo indisponível")

    dispositivo = await db.get(Dispositivo, dispositivo_id)
    if dispositivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo não encontrado")

    ip_hash = hash_do_request(request, settings.dea_ip_hash_salt)

    if antivandalismo.parece_bot(honeypot=body.website, segundos_de_preenchimento=None):
        # Mesmo raciocínio do cadastro: sucesso aparente, nada persistido.
        limiares = _limiares(settings)
        saida = _para_saida(dispositivo, limiares)
        return VerificacaoResponse(
            dispositivo_id=dispositivo.id,
            status=saida.status,
            confianca=saida.confianca,
            confirmacoes=saida.confirmacoes,
            contestacoes=saida.contestacoes,
            mensagem="Verificação registrada. Obrigado.",
        )

    excedido = await antivandalismo.limite_por_origem_excedido(
        "verificacao", ip_hash, settings.dea_max_verificacoes_por_hora, 3600
    )
    if excedido:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Limite de verificações por hora atingido. Tente novamente mais tarde.",
        )

    dispositivo = await cadastro_service.registrar_verificacao(db, dispositivo, body, ip_hash=ip_hash)
    await db.commit()

    saida = _para_saida(dispositivo, _limiares(settings))
    return VerificacaoResponse(
        dispositivo_id=dispositivo.id,
        status=saida.status,
        confianca=saida.confianca,
        confirmacoes=saida.confirmacoes,
        contestacoes=saida.contestacoes,
        mensagem="Verificação registrada. Obrigado por manter o mapa atualizado.",
    )
