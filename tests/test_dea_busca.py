"""
Busca por raio do localizador de DEA.

Cobre duas coisas distintas:

1. **A geometria** — que o Haversine em SQL concorda com o cálculo independente
   em Python, e que a bounding box não corta ninguém que deveria entrar.
2. **A rota pública** — que responde sem autenticação (decisão de produto que
   precisa de trava, porque neste projeto esquecer auth falha *aberto*), e que
   os tetos impedem raspagem.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.dea.repositories.locais_repository import (
    bounding_box,
    distancia_km,
)
from app.models.dea import (
    AcessoEnum,
    Dispositivo,
    Local,
    OrigemEnum,
    StatusDispositivoEnum,
)

# Av. Paulista, altura da Consolação. Origem de todas as buscas dos testes.
PAULISTA = (-23.5613, -46.6565)


def _arredondar(valor: float) -> float:
    """Mesma regra do cadastro: 4 casas ≈ 11 m, granularidade de "mesmo prédio"."""
    return round(valor, 4)


@pytest_asyncio.fixture
async def local_factory(db):
    async def criar(
        *,
        nome: str = "Local de teste",
        latitude: float = PAULISTA[0],
        longitude: float = PAULISTA[1],
        com_dispositivo: bool = True,
        status: str = StatusDispositivoEnum.ATIVO.value,
        positivas: int = 0,
        negativas: int = 0,
    ) -> Local:
        local = Local(
            id=uuid.uuid4(),
            nome=nome,
            latitude=latitude,
            longitude=longitude,
            lat_arredondada=_arredondar(latitude),
            lon_arredondada=_arredondar(longitude),
            acesso_24h=False,
        )
        db.add(local)
        await db.flush()

        if com_dispositivo:
            db.add(
                Dispositivo(
                    id=uuid.uuid4(),
                    local_id=local.id,
                    descricao_localizacao="Térreo, ao lado da recepção",
                    acesso=AcessoEnum.PUBLICO_LIVRE.value,
                    status=status,
                    origem=OrigemEnum.COLABORATIVO.value,
                    verificacoes_positivas=positivas,
                    verificacoes_negativas=negativas,
                )
            )
        await db.flush()
        return local

    return criar


async def _buscar(client, **params):
    base = {"latitude": PAULISTA[0], "longitude": PAULISTA[1]}
    return await client.get("/api/v1/dea/locais", params={**base, **params})


class TestGeometria:
    """A matemática, isolada do banco."""

    def test_bounding_box_contem_o_circulo(self):
        lat, lon = PAULISTA
        lat_min, lat_max, lon_min, lon_max = bounding_box(lat, lon, raio_km=5)

        # Um ponto exatamente a 5 km ao norte tem que caber na caixa.
        norte = lat + 5 / 111.045
        assert lat_min <= norte <= lat_max
        assert lon_min <= lon <= lon_max

    def test_bounding_box_e_mais_larga_em_longitude_perto_do_equador(self):
        # Longitude encolhe com o cosseno da latitude: perto do equador um grau
        # cobre mais quilômetros, então a caixa em graus é mais estreita.
        _, _, lon_min_eq, lon_max_eq = bounding_box(0.0, 0.0, raio_km=10)
        _, _, lon_min_sul, lon_max_sul = bounding_box(-60.0, 0.0, raio_km=10)

        assert (lon_max_eq - lon_min_eq) < (lon_max_sul - lon_min_sul)

    def test_bounding_box_nao_explode_no_polo(self):
        # Sem o piso no cosseno, o delta de longitude tenderia ao infinito.
        _, _, lon_min, lon_max = bounding_box(89.999, 0.0, raio_km=10)
        assert lon_max - lon_min < 360

    def test_distancia_conhecida(self):
        # Paulista → Praça da Sé: ~2,6 km em linha reta.
        km = distancia_km(*PAULISTA, -23.5505, -46.6333)
        assert 2.0 < km < 3.5

    def test_distancia_de_um_ponto_a_ele_mesmo_e_zero(self):
        assert distancia_km(*PAULISTA, *PAULISTA) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.asyncio
class TestBuscaNoBanco:
    async def test_encontra_local_proximo(self, client, local_factory):
        await local_factory(nome="Shopping Paulista")

        resposta = await _buscar(client, raio_km=1)

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["total"] == 1
        assert corpo["locais"][0]["nome"] == "Shopping Paulista"

    async def test_exclui_local_fora_do_raio(self, client, local_factory):
        # Campinas: ~90 km de São Paulo.
        await local_factory(nome="Longe", latitude=-22.9099, longitude=-47.0626)

        resposta = await _buscar(client, raio_km=10)

        assert resposta.json()["total"] == 0

    async def test_ordena_do_mais_proximo_ao_mais_distante(self, client, local_factory):
        await local_factory(nome="Longe", latitude=-23.5900, longitude=-46.6800)
        await local_factory(nome="Perto", latitude=-23.5620, longitude=-46.6570)

        corpo = (await _buscar(client, raio_km=10)).json()

        assert [item["nome"] for item in corpo["locais"]] == ["Perto", "Longe"]
        assert corpo["locais"][0]["distancia_km"] < corpo["locais"][1]["distancia_km"]

    async def test_distancia_do_sql_concorda_com_o_haversine_em_python(self, client, local_factory):
        # A fórmula está escrita duas vezes (SQL e Python). Se divergirem, é aqui
        # que aparece — e a versão Python é a que o cliente usa para ordenar.
        alvo = (-23.5700, -46.6600)
        await local_factory(latitude=alvo[0], longitude=alvo[1])

        corpo = (await _buscar(client, raio_km=25)).json()
        esperado = distancia_km(*PAULISTA, *alvo)

        assert corpo["locais"][0]["distancia_km"] == pytest.approx(esperado, abs=0.01)

    async def test_local_na_borda_do_raio_entra(self, client, local_factory):
        # ~2 km ao norte, buscando num raio de 2,05 km.
        await local_factory(latitude=PAULISTA[0] + 2 / 111.045, longitude=PAULISTA[1])

        assert (await _buscar(client, raio_km=2.05)).json()["total"] == 1
        assert (await _buscar(client, raio_km=1.95)).json()["total"] == 0

    async def test_local_sem_dispositivo_visivel_nao_aparece(self, client, local_factory):
        await local_factory(nome="Removido", status=StatusDispositivoEnum.REMOVIDO.value)

        assert (await _buscar(client, raio_km=5)).json()["total"] == 0

    async def test_dispositivo_pendente_aparece_no_mapa(self, client, local_factory):
        # Decisão de produto: pendente é etiqueta de confiança, não quarentena.
        # Segurar o pin até alguém confirmar mataria a contribuição exatamente
        # onde ela é mais valiosa — um bairro sem usuários.
        await local_factory(nome="Novo", status=StatusDispositivoEnum.PENDENTE.value)

        corpo = (await _buscar(client, raio_km=5)).json()

        assert corpo["total"] == 1
        assert corpo["locais"][0]["dispositivos"][0]["status"] == "pendente"

    async def test_respeita_o_limite_de_resultados(self, client, local_factory):
        for i in range(5):
            await local_factory(nome=f"L{i}", latitude=PAULISTA[0] + i * 0.001)

        corpo = (await _buscar(client, raio_km=10, limite=3)).json()

        assert corpo["total"] == 3

    async def test_resposta_vazia_e_bem_formada(self, client):
        corpo = (await _buscar(client, raio_km=5)).json()

        assert corpo["locais"] == []
        assert corpo["total"] == 0
        assert "192" in corpo["aviso"]


@pytest.mark.asyncio
class TestConfiancaNaResposta:
    async def test_expoe_fatos_crus_e_rotulo_sem_score(self, client, local_factory):
        await local_factory(positivas=3, negativas=1)

        dispositivo = (await _buscar(client, raio_km=5)).json()["locais"][0]["dispositivos"][0]

        assert dispositivo["confirmacoes"] == 3
        assert dispositivo["contestacoes"] == 1
        assert dispositivo["confianca"] in {"alta", "media", "baixa", "contestado"}
        # Nenhum número agregado: viraria porcentagem numa tela de emergência.
        assert "score" not in dispositivo

    async def test_dispositivo_sem_verificacao_nasce_com_confianca_baixa(self, client, local_factory):
        await local_factory()

        dispositivo = (await _buscar(client, raio_km=5)).json()["locais"][0]["dispositivos"][0]

        assert dispositivo["confianca"] == "baixa"
        assert dispositivo["dias_desde_ultima_verificacao"] is None


@pytest.mark.asyncio
class TestRotaPublica:
    """A decisão "público, sem login" travada por teste.

    Neste projeto a autenticação é rota a rota: omitir `get_current_user` já
    torna o endpoint aberto. Isso falha para o lado errado — esquecer a
    dependency num endpoint futuro não dá erro, dá vazamento. Estes testes são o
    lugar onde a decisão precisa aparecer explicitamente.
    """

    async def test_responde_200_sem_nenhum_header_de_autenticacao(self, client):
        resposta = await _buscar(client, raio_km=5)

        assert resposta.status_code == 200
        assert "authorization" not in {k.lower() for k in client.headers}

    async def test_token_invalido_nao_impede_a_consulta(self, client):
        # A rota ignora credenciais em vez de rejeitá-las: numa emergência, quem
        # socorre raramente é quem tem a conta.
        resposta = await client.get(
            "/api/v1/dea/locais",
            params={"latitude": PAULISTA[0], "longitude": PAULISTA[1]},
            headers={"Authorization": "Bearer token-invalido"},
        )
        assert resposta.status_code == 200


@pytest.mark.asyncio
class TestTetosDeSeguranca:
    """Sem estes limites, a rota aberta é o jeito mais barato de raspar a base."""

    async def test_raio_absurdo_e_rejeitado(self, client):
        assert (await _buscar(client, raio_km=20000)).status_code == 422

    async def test_limite_absurdo_e_rejeitado(self, client):
        assert (await _buscar(client, limite=100000)).status_code == 422

    async def test_raio_zero_ou_negativo_e_rejeitado(self, client):
        assert (await _buscar(client, raio_km=0)).status_code == 422
        assert (await _buscar(client, raio_km=-5)).status_code == 422

    @pytest.mark.parametrize(
        ("lat", "lon"),
        [(91, 0), (-91, 0), (0, 181), (0, -181)],
    )
    async def test_coordenada_fora_do_planeta_e_rejeitada(self, client, lat, lon):
        resposta = await client.get("/api/v1/dea/locais", params={"latitude": lat, "longitude": lon})
        assert resposta.status_code == 422

    async def test_coordenada_ausente_e_rejeitada(self, client):
        assert (await client.get("/api/v1/dea/locais")).status_code == 422


@pytest.mark.asyncio
class TestIndicesDeclaradosNoModelo:
    """Os índices existem no banco de teste — que é o ponto de declará-los no
    modelo em vez de criá-los só na migration.

    Se alguém migrar a busca para um índice de expressão ou uma extensão, este
    teste quebra, e é isso que se quer: seria a volta da divergência entre o
    schema testado e o de produção.
    """

    async def test_indice_de_busca_geografica_existe(self, db):
        resultado = await db.execute(
            text("SELECT indexname FROM pg_indexes " "WHERE schemaname = 'dea' AND tablename = 'locais'")
        )
        indices = {linha[0] for linha in resultado}

        assert "ix_dea_locais_lat_lon" in indices
        assert "ix_dea_locais_dedupe" in indices
