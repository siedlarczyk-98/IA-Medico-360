"""
Engine genérico de execução de calculadoras (RN-CALC-BACK-001).
Único ponto que decide como uma calculadora é executada, com base em `engine_type`
(RN-CALC-BACK-004).
"""

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators.engine.validation import CalculatorValidationError, validate_inputs
from app.calculators.formulas import load_all_formulas
from app.calculators.registry import get_formula
from app.calculators.repositories import calculators_repository as repo
from app.models.calculators import CalculatorExecution
from app.models.models import AuditLog

logger = logging.getLogger(__name__)


async def execute_calculator(
    db: AsyncSession,
    *,
    slug: str,
    inputs: dict,
    user_id: UUID,
    company_id: UUID | None,
    dry_run: bool = False,
) -> CalculatorExecution:
    definition = await repo.get_definition_or_404(db, slug)

    version = await repo.get_active_version(db, definition.id)
    if version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Calculadora '{slug}' não possui versão ativa")

    try:
        validated_inputs = validate_inputs(definition.fields, inputs)
    except CalculatorValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors)

    if definition.engine_type == "orchestrator":
        result, interpretation, interaction_id = await _delegate_to_orchestrator(
            definition=definition, version=version, inputs=validated_inputs
        )
    else:
        # Idempotente: o registry ja e populado no lifespan da app, este load
        # cobre apenas contextos sem lifespan (testes, scripts).
        load_all_formulas()
        try:
            formula_fn = get_formula(version.formula_key)
        except KeyError:
            logger.error(
                "formula_key '%s' da versao ativa de '%s' nao esta registrada",
                version.formula_key,
                slug,
            )
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                f"Calculadora '{slug}' está mal configurada",
            )
        try:
            outcome = formula_fn(validated_inputs)
        except HTTPException:
            raise
        except (KeyError, TypeError, ValueError, ZeroDivisionError, ArithmeticError) as exc:
            # Campos opcionais (ver migration 016) e faixas configuradas por seed
            # podem deixar a formula sem um input que ela acessa direto. Responde
            # 422 em vez de vazar um 500 com traceback.
            logger.warning(
                "Falha ao executar formula '%s' de '%s': %s", version.formula_key, slug, exc
            )
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                [{"loc": ["inputs"], "msg": "Inputs insuficientes ou inválidos para esta calculadora"}],
            )
        result = outcome["result"]
        interpretation = outcome.get("interpretation")
        interaction_id = None

    if dry_run:
        # Chamada intermediária (checagem de early-exit do wizard): não persiste
        # execução nem consome cota de uso, mas continua auditada — sem isso o
        # dry_run seria um caminho de cálculo clínico sem rastro (RN-CALC-SCHEMA-005).
        db.add(
            AuditLog(
                user_id=user_id,
                interaction_id=interaction_id,
                action="calculator_execute_dry_run",
                entity_type="calculator_definition",
                entity_id=definition.id,
                metadata_={
                    "slug": slug,
                    "version_id": str(version.id),
                    "input_keys": sorted(validated_inputs.keys()),
                },
            )
        )
        await db.commit()
        return CalculatorExecution(
            calculator_id=definition.id,
            version_id=version.id,
            user_id=user_id,
            company_id=company_id,
            interaction_id=interaction_id,
            inputs=validated_inputs,
            result=result,
            interpretation=interpretation,
        )

    execution = CalculatorExecution(
        calculator_id=definition.id,
        version_id=version.id,
        user_id=user_id,
        company_id=company_id,
        interaction_id=interaction_id,
        inputs=validated_inputs,
        result=result,
        interpretation=interpretation,
    )
    db.add(execution)
    await db.flush()

    db.add(
        AuditLog(
            user_id=user_id,
            interaction_id=interaction_id,
            action="calculator_execute",
            entity_type="calculator_execution",
            entity_id=execution.id,
            metadata_={"slug": slug, "version_id": str(version.id)},
        )
    )

    await db.commit()
    await db.refresh(execution)
    return execution


async def _delegate_to_orchestrator(*, definition, version, inputs) -> tuple[dict, str | None, UUID | None]:
    """Gancho para calculadoras `orchestrator` (RN-CALC-BACK-004). Fora de escopo na Fase 1."""
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Execução via Orquestrador ainda não implementada",
    )
