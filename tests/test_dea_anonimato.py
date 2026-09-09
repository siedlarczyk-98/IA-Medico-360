"""
Hash de IP dos contribuidores anônimos do mapa de DEA.

O que se afirma aqui é uma propriedade de privacidade, não um detalhe de
implementação: o identificador serve para dedupe e rate limit **dentro do dia**,
e deliberadamente não serve para seguir uma origem ao longo do tempo.
"""

from datetime import date

import pytest

from app.dea.services.anonimato import hash_de_ip

SAL = "sal-de-teste-nao-usar-em-producao"
IP = "203.0.113.42"
HOJE = date(2026, 9, 9)


class TestDeterminismo:
    def test_mesmo_ip_no_mesmo_dia_gera_o_mesmo_hash(self):
        # É o que permite reconhecer "mesma origem" para dedupe e rate limit.
        assert hash_de_ip(IP, SAL, HOJE) == hash_de_ip(IP, SAL, HOJE)

    def test_ips_diferentes_geram_hashes_diferentes(self):
        assert hash_de_ip(IP, SAL, HOJE) != hash_de_ip("198.51.100.7", SAL, HOJE)

    def test_formato_e_sha256_hexadecimal(self):
        resultado = hash_de_ip(IP, SAL, HOJE)

        assert len(resultado) == 64
        assert all(c in "0123456789abcdef" for c in resultado)


class TestPrivacidade:
    """As propriedades que justificam o desenho."""

    def test_o_hash_rotaciona_a_cada_dia(self):
        # A propriedade central: o mesmo IP em dias diferentes é indistinguível
        # de dois IPs distintos. Sem isto, o hash seria um identificador estável
        # e o "pseudônimo" viraria histórico de geolocalização por IP.
        assert hash_de_ip(IP, SAL, date(2026, 9, 9)) != hash_de_ip(IP, SAL, date(2026, 9, 10))

    def test_sal_diferente_muda_o_hash(self):
        # Sem sal, `sha256(ip)` é reversível por força bruta: o espaço IPv4
        # inteiro tem ~4 bilhões de entradas e cabe numa GPU.
        assert hash_de_ip(IP, SAL, HOJE) != hash_de_ip(IP, "outro-sal", HOJE)

    def test_o_ip_nao_aparece_no_resultado(self):
        resultado = hash_de_ip(IP, SAL, HOJE)

        assert IP not in resultado
        for octeto in IP.split("."):
            # Um octeto isolado pode coincidir com hexadecimal; o que não pode é
            # o endereço aparecer legível.
            assert IP.replace(".", "") not in resultado
            assert len(octeto) > 0

    def test_hashes_de_dias_consecutivos_nao_sao_correlacionaveis_por_prefixo(self):
        # Um esquema ingênuo (concatenar a data ao final do hash, por exemplo)
        # deixaria os hashes do mesmo IP parecidos entre si.
        a = hash_de_ip(IP, SAL, date(2026, 9, 9))
        b = hash_de_ip(IP, SAL, date(2026, 9, 10))

        prefixo_comum = 0
        for x, y in zip(a, b):
            if x != y:
                break
            prefixo_comum += 1

        assert prefixo_comum < 8


class TestRobustez:
    @pytest.mark.parametrize(
        "entrada",
        ["203.0.113.42", "2001:db8::1", "::1", "127.0.0.1", "desconhecido"],
    )
    def test_aceita_ipv4_ipv6_e_o_marcador_de_origem_desconhecida(self, entrada):
        # `ip_do_request` devolve "desconhecido" quando não há cliente (por
        # exemplo, chamadas internas): o hash não pode explodir nesse caso.
        assert len(hash_de_ip(entrada, SAL, HOJE)) == 64

    def test_sal_vazio_ainda_produz_hash(self):
        # Em produção o sal vazio é barrado no startup (ver `Settings`), mas a
        # função não deve quebrar em desenvolvimento.
        assert len(hash_de_ip(IP, "", HOJE)) == 64
