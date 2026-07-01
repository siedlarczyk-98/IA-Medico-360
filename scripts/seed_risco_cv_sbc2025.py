"""
Seed da calculadora de Risco Cardiovascular — SBC 2025
(Rached et al., Arq Bras Cardiol. 2025;122(9):e20250640).
"""

import asyncio

from app.core.database import async_session_factory
from app.models.calculators import (
    CalculatorDefinition,
    CalculatorField,
    CalculatorVersion,
    Specialty,
)
from sqlalchemy import select


def _field(calculator_id, key, label, field_type, order, **kwargs):
    return CalculatorField(
        calculator_id=calculator_id,
        key=key,
        label=label,
        field_type=field_type,
        display_order=order,
        **kwargs,
    )


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Specialty).where(Specialty.slug == "cardiologia"))
        specialty = result.scalar_one_or_none()
        if specialty is None:
            specialty = Specialty(name="Cardiologia", slug="cardiologia")
            db.add(specialty)
            await db.flush()

        result = await db.execute(
            select(CalculatorDefinition).where(CalculatorDefinition.slug == "risco_cv_sbc2025")
        )
        definition = result.scalar_one_or_none()
        if definition is not None:
            print("Calculadora 'risco_cv_sbc2025' já existe — nada a fazer.")
            return

        definition = CalculatorDefinition(
            specialty_id=specialty.id,
            slug="risco_cv_sbc2025",
            name="Risco Cardiovascular (SBC 2025)",
            description=(
                "Estratificação de risco cardiovascular conforme Diretriz Brasileira de "
                "Dislipidemias e Prevenção da Aterosclerose."
            ),
            engine_type="formula",
            status="active",
        )
        db.add(definition)
        await db.flush()
        cid = definition.id

        fields = [
            # ── Demografia ────────────────────────────────────────────────
            _field(cid, "idade", "Idade", "integer", 1, required=True, unit="anos", min_value=18, max_value=110),
            _field(cid, "sexo", "Sexo biológico", "select", 2, required=True, options=[
                {"value": "F", "label": "Feminino"}, {"value": "M", "label": "Masculino"},
            ]),

            # ── Inputs PREVENT (também usados no algoritmo SBC) ──────────
            # required=False: lidos via .get()/bloco condicional em calculate() — não
            # bloqueiam early-exit do wizard antes do passo PREVENT ser alcançado.
            _field(cid, "ct_mgdl", "Colesterol total", "number", 3, required=False, unit="mg/dL", min_value=50, max_value=500),
            _field(cid, "hdl_mgdl", "HDL-c", "number", 4, required=False, unit="mg/dL", min_value=10, max_value=150),
            _field(cid, "ldl_mgdl", "LDL-c", "number", 5, required=False, unit="mg/dL", min_value=10, max_value=400),
            _field(cid, "sbp_mmhg", "Pressão arterial sistólica", "number", 6, required=False, unit="mmHg", min_value=70, max_value=250),
            _field(cid, "bmi", "IMC", "number", 7, required=False, unit="kg/m²", min_value=10, max_value=70),
            _field(cid, "egfr", "TFGe (eGFR)", "number", 8, required=False, unit="mL/min/1,73m²", min_value=1, max_value=200),
            _field(cid, "fumante", "Tabagismo atual", "boolean", 9, required=False),
            _field(cid, "antihtn_use", "Uso de anti-hipertensivo", "boolean", 10, required=False),
            _field(cid, "statin_use", "Uso de estatina", "boolean", 11, required=False),
            _field(cid, "hipertensao", "Hipertensão arterial (diagnóstico)", "boolean", 12, required=False),

            # ── Passo 1: evento CV aterosclerótico prévio ─────────────────
            _field(cid, "evento_cv_previo", "Evento CV aterosclerótico prévio", "boolean", 13, required=False),
            _field(cid, "tipos_evento_cv", "Tipo(s) de evento CV maior", "multiselect", 14, required=False, options=[
                {"value": "sca_recente_12m", "label": "Síndrome coronária aguda recente (últimos 12 meses)"},
                {"value": "iam_antigo", "label": "Infarto do miocárdio prévio"},
                {"value": "avc_isquemico", "label": "AVC isquêmico prévio"},
                {"value": "dap_sintomatica", "label": "Doença arterial periférica sintomática (ITB < 0,85 ou revasc./amputação prévia)"},
            ]),

            # ── Passo 2: doença aterosclerótica significativa ─────────────
            _field(cid, "doenca_aterosclerotica_significativa", "DCVAt sintomática / revascularização prévia / obstrução ≥ 50%", "boolean", 15, required=False),
            _field(cid, "cac_ua", "Escore de cálcio coronário (CAC)", "number", 16, required=False, unit="UA", min_value=0, max_value=5000),
            _field(cid, "cac_percentil_gt75", "CAC em percentil > 75 para sexo/idade", "boolean", 17, required=False),

            # ── Passo 4: marcadores adicionais ─────────────────────────────
            _field(cid, "placa_carotidea_lt50", "Placa carotídea < 50%", "boolean", 18, required=False),
            _field(cid, "placa_angiotc_lt50", "Placa na angiotomografia de coronárias < 50%", "boolean", 19, required=False),
            _field(cid, "aaa_conhecido", "Aneurisma de aorta abdominal (AAA)", "boolean", 20, required=False),
            _field(cid, "lpa_mgdl", "Lipoproteína(a)", "number", 21, required=False, unit="mg/dL", min_value=0, max_value=500),
            _field(cid, "lpa_nmol", "Lipoproteína(a) (alternativa)", "number", 22, required=False, unit="nmol/L", min_value=0, max_value=1500),
            _field(cid, "hipercolesterolemia_familiar", "Hipercolesterolemia familiar", "boolean", 23, required=False),

            # ── Diabetes (Passo 3 / sub-árvore) ────────────────────────────
            _field(cid, "diabetes", "Diabetes mellitus", "boolean", 24, required=False),
            _field(cid, "tipo_dm", "Tipo de diabetes", "select", 25, required=False, options=[
                {"value": "dm1", "label": "Tipo 1"}, {"value": "dm2", "label": "Tipo 2"},
            ]),
            _field(cid, "duracao_dm_anos", "Duração do diabetes", "integer", 26, required=False, unit="anos", min_value=0, max_value=80),
            _field(cid, "dm1_diagnosticado_apos_18_anos", "DM1 diagnosticado após os 18 anos", "boolean", 27, required=False),
            _field(cid, "albuminuria_mg_g", "Albuminúria (RAC)", "number", 28, required=False, unit="mg/g", min_value=0, max_value=10000),
            _field(cid, "historia_familiar_dac_prematura", "História familiar de doença arterial coronária prematura", "boolean", 29, required=False),
            _field(cid, "sindrome_metabolica", "Síndrome metabólica (critério IDF)", "boolean", 30, required=False),
            _field(cid, "neuropatia_autonoma_incipiente", "Neuropatia autonômica cardiovascular incipiente", "boolean", 31, required=False),
            _field(cid, "neuropatia_autonoma_instalada", "Neuropatia autonômica cardiovascular instalada (2 testes TAC alterados)", "boolean", 32, required=False),
            _field(cid, "retinopatia_np_leve", "Retinopatia diabética não proliferativa leve", "boolean", 33, required=False),
            _field(cid, "retinopatia_avancada", "Retinopatia diabética moderada-severa/severa/proliferativa ou em progressão", "boolean", 34, required=False),

            # ── Critério de risco extremo (Tabela 4.2) ─────────────────────
            _field(cid, "cirurgia_revasc_previa_fora_evento", "Revascularização miocárdica/ICP prévia fora do(s) evento(s) maior(es)", "boolean", 35, required=False),
            _field(cid, "ldl_persistente_ge100_max_tto", "LDL-c persistentemente ≥ 100 mg/dL apesar de estatina máxima + ezetimiba", "boolean", 36, required=False),
            _field(cid, "evento_agudo_lt2anos", "Evento agudo aterosclerótico há menos de 2 anos", "boolean", 37, required=False),

            # ── Fatores agravantes (Seção 5 / Tabela 4.3) ──────────────────
            _field(cid, "historia_familiar_cv_prematura", "História familiar de DCV prematura (1º grau, <55a homem / <65a mulher)", "boolean", 38, required=False),
            _field(cid, "adiposidade_com_param_alterado", "Adiposidade (IMC ≥30 + parâmetro antropométrico alterado)", "boolean", 39, required=False),
            _field(cid, "esteatose_hepatica", "Esteatose hepática (especialmente formas graves/com fibrose)", "boolean", 40, required=False),
            _field(cid, "doenca_inflamatoria_cronica", "Condição inflamatória crônica (AR, psoríase, LES, DII, HIV)", "boolean", 41, required=False),
            _field(cid, "transplante_orgao_solido", "Transplante de órgão sólido", "boolean", 42, required=False),
            _field(cid, "fatores_femininos", "Fatores específicos femininos (menarca precoce/tardia, distúrbio hipertensivo gestacional, parto prematuro, RCIU, abortos ≥3, menopausa precoce)", "boolean", 43, required=False),
            _field(cid, "pcr_us_mgL", "Proteína C-reativa ultrassensível", "number", 44, required=False, unit="mg/L", min_value=0, max_value=50),
        ]
        db.add_all(fields)

        version = CalculatorVersion(
            calculator_id=cid,
            version_number=1,
            formula_key="risco_cv_sbc2025_v1",
            clinical_reference=(
                "Rached et al., Arq Bras Cardiol. 2025;122(9):e20250640 (SBC 2025) — "
                "Algoritmo de estratificação (Tabela 4.1/Figura 4.1, Tabelas 4.2–4.8). "
                "Escore PREVENT: Khan et al., Circulation 2024 (Tabelas S12A/S12F)."
            ),
            is_active=True,
        )
        db.add(version)

        await db.commit()
        print("Seed de 'risco_cv_sbc2025' concluído.")


if __name__ == "__main__":
    asyncio.run(main())
