"""
Médico 360 — Extração de inputs estruturados para calculadoras via IA.
Pré-preenche campos a partir de texto livre (evolução clínica); o médico revisa
antes de calcular. Não substitui a fórmula determinística (engine_type continua "formula").
"""

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http_client import get_client
from app.models.calculators import CalculatorField
from app.models.models import AuditLog

settings = get_settings()
logger = logging.getLogger(__name__)

_NUMERIC_TYPES = {"number", "integer"}


def _build_prompt(fields: list[CalculatorField], text: str) -> str:
    field_lines = []
    for f in fields:
        descriptor = f"- \"{f.key}\" ({f.field_type}): {f.label}"
        if f.unit:
            descriptor += f", unidade: {f.unit}"
        if f.options:
            values = [opt.get("value") for opt in f.options if isinstance(opt, dict)]
            descriptor += f", valores possíveis: {values}"
        field_lines.append(descriptor)

    fields_block = "\n".join(field_lines)
    return f"""Extraia, a partir do texto clínico abaixo, os valores dos seguintes campos estruturados:

{fields_block}

Regras:
- Retorne APENAS um JSON puro no formato {{"chave": valor}}, sem markdown.
- Inclua somente os campos que conseguir inferir com segurança do texto.
- Não invente valores não mencionados ou não dedutíveis do texto.
- Campos do tipo "boolean" devem ser true/false.
- Campos do tipo "number"/"integer" devem ser apenas o número, sem unidade.
- Campos do tipo "select" devem usar exatamente um dos "valores possíveis".

Texto:
{text}"""


def _coerce_value(field: CalculatorField, value):
    """Validação tolerante: retorna o valor convertido, ou None se não for aproveitável."""
    if value is None:
        return None

    if field.field_type in _NUMERIC_TYPES:
        try:
            return int(value) if field.field_type == "integer" else float(value)
        except (TypeError, ValueError):
            return None

    if field.field_type == "boolean":
        return value if isinstance(value, bool) else None

    if field.field_type == "select":
        valid_options = {opt.get("value") for opt in (field.options or []) if isinstance(opt, dict)}
        return value if value in valid_options else None

    if field.field_type == "multiselect":
        if not isinstance(value, list):
            return None
        valid_options = {opt.get("value") for opt in (field.options or []) if isinstance(opt, dict)}
        filtered = [v for v in value if v in valid_options]
        return filtered or None

    if field.field_type == "text":
        return str(value)

    return None


async def extract_calculator_inputs(
    db: AsyncSession,
    *,
    fields: list[CalculatorField],
    text: str,
    user_id: UUID,
) -> tuple[dict, list[str]]:
    """Chama o LLM para sugerir inputs estruturados a partir de texto livre.
    Retorna (suggested_inputs, fields_extracted), tolerando ausência/erro do LLM.
    """
    fields_by_key = {f.key: f for f in fields}
    suggested_inputs: dict = {}

    try:
        client = get_client()
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-5.4-mini",
                "messages": [
                    {"role": "user", "content": _build_prompt(fields, text)},
                ],
                "max_completion_tokens": 800,
                "temperature": 0,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        content = content.replace("```json", "").replace("```", "").strip()

        raw_suggestions = json.loads(content)
        if isinstance(raw_suggestions, dict):
            for key, value in raw_suggestions.items():
                field = fields_by_key.get(key)
                if field is None:
                    continue
                coerced = _coerce_value(field, value)
                if coerced is not None:
                    suggested_inputs[key] = coerced
    except Exception as e:
        logger.warning("Falha ao extrair inputs de calculadora via IA: %s", e)

    db.add(
        AuditLog(
            user_id=user_id,
            action="calculator.extract",
            entity_type="calculator_field_extraction",
            metadata_={"fields_extracted": list(suggested_inputs.keys())},
        )
    )
    await db.commit()

    return suggested_inputs, list(suggested_inputs.keys())
