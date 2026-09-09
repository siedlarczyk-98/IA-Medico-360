"""
Escrita pública do mapa de DEA: cadastro, verificação e antivandalismo.

O que se afirma aqui não é "a rota funciona", é que cada defesa **de fato
barra** o que promete barrar — e, tão importante quanto, que nenhuma delas barra
o caso de uso legítimo. Um antivandalismo que mata a contribuição honesta é pior
que nenhum, porque o mapa vazio não salva ninguém.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.dea.services import antivandalismo
from app.models.dea import Dispositivo, Local, StatusDispositivoEnum

PAULISTA = {"latitude": -23.5613, "longitude": -46.6565}


def _cadastro(**extra) -> dict:
    base = {
        "nome": "Shopping de teste",
        **PAULISTA,
        "descricao_localizacao": "Térreo, ao lado do caixa 3",
        "acesso": "publico_livre",
        # Tempo plausível de preenchimento — sem isto o honeypot de tempo
        # marcaria todo cadastro dos testes como bot.
        "segundos_de_preenchimento": 45.0,
    }
    return {**base, **extra}


@pytest.fixture(autouse=True)
def _zera_rate_limit_do_slowapi():
    """O limiter do slowapi guarda estado em memória do processo, por IP.

    Todos os testes deste arquivo saem do mesmo IP (o cliente ASGI), então sem
    reset o limite de 20/minuto da rota acaba no meio do arquivo e os testes
    seguintes falham por 429 — uma falha que não tem nada a ver com o que eles
    afirmam. O limite em si é exercitado à parte, em `TestLimitePorOrigem`.
    """
    from app.core.limiter import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest_asyncio.fixture(autouse=True)
def _redis_disponivel(monkeypatch):
    """Redis não existe no ambiente de teste (ver `tests/test_health.py`).

    Por padrão fingimos "dentro do limite", para os testes de caminho feliz não
    dependerem de infraestrutura. Os testes de limite sobrescrevem isto.
    """

    async def dentro_do_limite(*_args, **_kwargs):
        return False

    monkeypatch.setattr(antivandalismo, "limite_por_origem_excedido", dentro_do_limite)


async def _contar(db, modelo) -> int:
    return (await db.execute(select(func.count()).select_from(modelo))).scalar()


@pytest.mark.asyncio
class TestCadastro:
    async def test_cadastra_sem_autenticacao(self, client, db):
        resposta = await client.post("/api/v1/dea/locais", json=_cadastro())

        assert resposta.status_code == 201
        assert await _contar(db, Local) == 1
        assert await _contar(db, Dispositivo) == 1

    async def test_registro_nasce_pendente(self, client):
        corpo = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()

        # Nem o cadastro mais bem preenchido nasce confirmado: é a palavra de
        # uma pessoa só.
        assert corpo["status"] == "pendente"

    async def test_aparece_no_mapa_imediatamente(self, client):
        await client.post("/api/v1/dea/locais", json=_cadastro(nome="Recém-cadastrado"))

        busca = await client.get("/api/v1/dea/locais", params={**PAULISTA, "raio_km": 1})

        # A decisão de produto: pendente é etiqueta, não quarentena.
        assert busca.json()["total"] == 1
        assert busca.json()["locais"][0]["nome"] == "Recém-cadastrado"

    async def test_persiste_os_campos_que_importam(self, client, db):
        await client.post(
            "/api/v1/dea/locais",
            json=_cadastro(
                nome="Estação Central",
                horario_texto="Seg-Sáb 10h-22h, Dom 14h-20h",
                acesso_24h=True,
                acesso="balcao_recepcao",
            ),
        )

        local = (await db.execute(select(Local))).scalar_one()
        dispositivo = (await db.execute(select(Dispositivo))).scalar_one()

        assert local.horario_texto == "Seg-Sáb 10h-22h, Dom 14h-20h"
        assert local.acesso_24h is True
        assert dispositivo.acesso == "balcao_recepcao"
        assert dispositivo.descricao_localizacao == "Térreo, ao lado do caixa 3"

    async def test_grava_hash_de_ip_e_nunca_o_ip_em_claro(self, client, db):
        await client.post("/api/v1/dea/locais", json=_cadastro())

        dispositivo = (await db.execute(select(Dispositivo))).scalar_one()

        assert dispositivo.criado_por_ip_hash is not None
        assert len(dispositivo.criado_por_ip_hash) == 64
        # Nenhum formato de IP reconhecível no que foi persistido.
        assert "." not in dispositivo.criado_por_ip_hash
        assert ":" not in dispositivo.criado_por_ip_hash

    async def test_arredondamento_de_dedupe_e_gravado(self, client, db):
        await client.post(
            "/api/v1/dea/locais",
            json=_cadastro(latitude=-23.56131111, longitude=-46.65659999),
        )

        local = (await db.execute(select(Local))).scalar_one()

        assert local.lat_arredondada == pytest.approx(-23.5613)
        assert local.lon_arredondada == pytest.approx(-46.6566)

    @pytest.mark.parametrize(
        "invalido",
        [
            {"nome": "x"},  # curto demais
            {"nome": "a" * 200},  # longo demais
            {"latitude": 91},
            {"longitude": -181},
            {"acesso": "inventado"},
            {"descricao_localizacao": "a" * 600},
        ],
    )
    async def test_rejeita_entrada_invalida(self, client, db, invalido):
        resposta = await client.post("/api/v1/dea/locais", json=_cadastro(**invalido))

        assert resposta.status_code == 422
        assert await _contar(db, Local) == 0

    async def test_nome_e_endereco_sao_normalizados(self, client, db):
        await client.post(
            "/api/v1/dea/locais",
            json=_cadastro(nome="  Shopping  ", endereco="  Av. Paulista  ", uf="sp"),
        )

        local = (await db.execute(select(Local))).scalar_one()

        assert local.nome == "Shopping"
        assert local.endereco == "Av. Paulista"
        assert local.uf == "SP"


@pytest.mark.asyncio
class TestHoneypot:
    """Sinais baratos de automação. A resposta a eles é sucesso aparente."""

    async def test_campo_oculto_preenchido_nao_persiste_nada(self, client, db):
        resposta = await client.post("/api/v1/dea/locais", json=_cadastro(website="http://spam.example"))

        # 201, não 400: bot que recebe erro adapta o payload e volta; bot que
        # recebe sucesso vai embora achando que funcionou.
        assert resposta.status_code == 201
        assert await _contar(db, Local) == 0

    async def test_resposta_do_honeypot_e_indistinguivel_da_real(self, client):
        real = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()
        falsa = (await client.post("/api/v1/dea/locais", json=_cadastro(website="x"))).json()

        # Mesmas chaves e mesmo status: nada no corpo revela a detecção.
        assert real.keys() == falsa.keys()
        assert real["status"] == falsa["status"]

    async def test_preenchimento_rapido_demais_e_tratado_como_bot(self, client, db):
        resposta = await client.post("/api/v1/dea/locais", json=_cadastro(segundos_de_preenchimento=0.4))

        assert resposta.status_code == 201
        assert await _contar(db, Local) == 0

    async def test_preenchimento_humano_passa(self, client, db):
        await client.post("/api/v1/dea/locais", json=_cadastro(segundos_de_preenchimento=12.0))

        assert await _contar(db, Local) == 1

    async def test_ausencia_do_campo_de_tempo_nao_bloqueia(self, client, db):
        # Cliente antigo, ou um curl legítimo, não mandam o campo. Não é sinal
        # de bot — só de que não temos a informação.
        dados = _cadastro()
        del dados["segundos_de_preenchimento"]

        await client.post("/api/v1/dea/locais", json=dados)

        assert await _contar(db, Local) == 1


@pytest.mark.asyncio
class TestDensidadeGeografica:
    """A defesa contra "50 pins numa quadra"."""

    async def test_bloqueia_cadastros_em_rajada_na_mesma_regiao(self, client, db):
        # O limite padrão é 5 por hora num raio de ~1 km.
        for i in range(5):
            resposta = await client.post(
                "/api/v1/dea/locais",
                json=_cadastro(nome=f"Local {i}", latitude=-23.5613 + i * 0.0005),
            )
            assert resposta.status_code == 201

        excedente = await client.post("/api/v1/dea/locais", json=_cadastro(nome="Sexto"))

        assert excedente.status_code == 429
        assert await _contar(db, Local) == 5

    async def test_nao_bloqueia_cadastro_em_regiao_distante(self, client, db):
        for i in range(5):
            await client.post(
                "/api/v1/dea/locais",
                json=_cadastro(nome=f"SP {i}", latitude=-23.5613 + i * 0.0005),
            )

        # Campinas, ~90 km: outra região, contador próprio.
        longe = await client.post(
            "/api/v1/dea/locais",
            json=_cadastro(nome="Campinas", latitude=-22.9099, longitude=-47.0626),
        )

        assert longe.status_code == 201
        assert await _contar(db, Local) == 6


@pytest.mark.asyncio
class TestVerificacao:
    async def test_confirmacao_de_outra_origem_promove_para_ativo(self, client, db):
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()

        # O cliente de teste tem sempre a mesma origem; forçamos uma diferente
        # para exercitar a regra de promoção.
        dispositivo = await db.get(Dispositivo, uuid.UUID(criado["dispositivo_id"]))
        # 64 caracteres, como um sha256 real — a coluna é VARCHAR(64).
        dispositivo.criado_por_ip_hash = "a" * 64
        await db.flush()

        resposta = await client.post(
            f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes",
            json={"resultado": "encontrado"},
        )

        assert resposta.status_code == 201
        assert resposta.json()["status"] == "ativo"
        assert resposta.json()["confirmacoes"] == 1

    async def test_confirmacao_da_MESMA_origem_nao_promove(self, client, db):
        # Impede o caso trivial: plantar um pin falso e confirmá-lo em seguida.
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()

        resposta = await client.post(
            f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes",
            json={"resultado": "encontrado"},
        )

        assert resposta.status_code == 201
        assert resposta.json()["status"] == "pendente"
        # A confirmação é contada — só não promove.
        assert resposta.json()["confirmacoes"] == 1

    async def test_duas_negativas_marcam_como_nao_encontrado(self, client, db):
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()
        url = f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes"

        await client.post(url, json={"resultado": "nao_encontrado"})
        segunda = await client.post(url, json={"resultado": "nao_encontrado"})

        assert segunda.json()["status"] == "nao_encontrado"
        assert segunda.json()["confianca"] == "contestado"

    async def test_dispositivo_nao_encontrado_continua_no_mapa(self, client):
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()
        url = f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes"
        await client.post(url, json={"resultado": "nao_encontrado"})
        await client.post(url, json={"resultado": "nao_encontrado"})

        busca = await client.get("/api/v1/dea/locais", params={**PAULISTA, "raio_km": 1})

        # "Duas pessoas procuraram e não acharam" é informação útil para a
        # terceira — mais útil que o silêncio.
        assert busca.json()["total"] == 1
        assert busca.json()["locais"][0]["dispositivos"][0]["status"] == "nao_encontrado"

    async def test_marcar_como_removido_tira_do_mapa(self, client):
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()

        await client.post(
            f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes",
            json={"resultado": "removido"},
        )
        busca = await client.get("/api/v1/dea/locais", params={**PAULISTA, "raio_km": 1})

        assert busca.json()["total"] == 0

    async def test_nada_e_deletado_do_banco(self, client, db):
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()
        await client.post(
            f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes",
            json={"resultado": "removido"},
        )

        # Some da listagem, permanece na tabela: o histórico de "existiu um DEA
        # aqui" é informação, não lixo.
        assert await _contar(db, Dispositivo) == 1
        assert await _contar(db, Local) == 1

    async def test_dispositivo_inexistente_devolve_404(self, client):
        resposta = await client.post(
            f"/api/v1/dea/dispositivos/{uuid.uuid4()}/verificacoes",
            json={"resultado": "encontrado"},
        )

        assert resposta.status_code == 404

    async def test_resultado_invalido_e_rejeitado(self, client):
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()

        resposta = await client.post(
            f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes",
            json={"resultado": "talvez"},
        )

        assert resposta.status_code == 422

    async def test_honeypot_na_verificacao_nao_altera_contadores(self, client, db):
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()

        resposta = await client.post(
            f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes",
            json={"resultado": "encontrado", "website": "spam"},
        )

        assert resposta.status_code == 201
        dispositivo = await db.get(Dispositivo, uuid.UUID(criado["dispositivo_id"]))
        assert dispositivo.verificacoes_positivas == 0
        assert dispositivo.status == StatusDispositivoEnum.PENDENTE.value

    async def test_verificacoes_nao_contam_para_o_limite_de_densidade(self, client):
        """O caso de uso do ACLS: uma turma inteira confirmando o mesmo DEA.

        Se as verificações caíssem no limite de densidade, o canal de captação
        do produto seria bloqueado como se fosse ataque.
        """
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()
        url = f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes"

        for _ in range(15):
            resposta = await client.post(url, json={"resultado": "encontrado"})
            assert resposta.status_code == 201


@pytest.mark.asyncio
class TestLimitePorOrigem:
    async def test_excedido_devolve_429_e_nao_persiste(self, client, db, monkeypatch):
        async def estourado(*_a, **_k):
            return True

        monkeypatch.setattr(antivandalismo, "limite_por_origem_excedido", estourado)

        resposta = await client.post("/api/v1/dea/locais", json=_cadastro())

        assert resposta.status_code == 429
        assert await _contar(db, Local) == 0

    async def test_redis_indisponivel_aceita_o_cadastro_como_pendente(self, client, db, monkeypatch):
        """Fail-closed suave: não perde a contribuição, não publica sem revisão.

        O `rate_limit_exceeded` do projeto falha *aberto*, que é correto para
        login — derrubar a autenticação por indisponibilidade de cache seria pior
        que o risco. Para escrita anônima o cálculo se inverte, e a saída é
        aceitar marcando como pendente.
        """

        async def redis_fora(*_a, **_k):
            return None

        monkeypatch.setattr(antivandalismo, "limite_por_origem_excedido", redis_fora)

        resposta = await client.post("/api/v1/dea/locais", json=_cadastro())

        assert resposta.status_code == 201
        assert resposta.json()["status"] == "pendente"
        assert await _contar(db, Local) == 1


@pytest.mark.asyncio
class TestEscritaPublica:
    """A decisão de não exigir login, travada por teste."""

    async def test_cadastra_sem_nenhum_header_de_autenticacao(self, client):
        resposta = await client.post("/api/v1/dea/locais", json=_cadastro())

        assert resposta.status_code == 201
        assert "authorization" not in {k.lower() for k in client.headers}

    async def test_verifica_sem_nenhum_header_de_autenticacao(self, client):
        criado = (await client.post("/api/v1/dea/locais", json=_cadastro())).json()

        resposta = await client.post(
            f"/api/v1/dea/dispositivos/{criado['dispositivo_id']}/verificacoes",
            json={"resultado": "encontrado"},
        )

        assert resposta.status_code == 201
