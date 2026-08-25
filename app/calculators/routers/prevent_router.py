from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.calculators.formulas.cardiologia.prevent import prevent_risk
from app.calculators.schemas.prevent_schemas import PreventCalculateRequest, PreventCalculateResponse
from app.core.limiter import limiter
from app.models.models import User

router = APIRouter(prefix="/prevent", tags=["prevent"])


@router.post("/calculate", response_model=PreventCalculateResponse)
@limiter.limit("60/minute")
async def calculate_prevent(
    request: Request,
    body: PreventCalculateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Escore PREVENT (AHA, Khan et al. 2024) — modelo válido para idade 30–79 e
    IMC ≤ 39,9. Fora dessa faixa, todos os campos vêm `None` (não há coeficiente
    calibrado). Não persiste execução nem audit log — cálculo sem estado.
    """
    if not (30 <= body.idade <= 79) or body.bmi > 39.9:
        return PreventCalculateResponse(ascvd_10a=None, cvd_10a=None, hf_10a=None, ascvd_30a=None, cvd_30a=None)

    kwargs = dict(
        sex=body.sexo,
        age=body.idade,
        tc_mgdl=body.ct_mgdl,
        hdl_mgdl=body.hdl_mgdl,
        sbp=body.sbp_mmhg,
        diabetes=body.diabetes,
        smoker=body.fumante,
        antihtn_use=body.antihtn_use,
        statin_use=body.statin_use,
        egfr=body.egfr,
        bmi=body.bmi,
    )
    ascvd_30a = cvd_30a = None
    if body.idade <= 59:
        ascvd_30a = round(prevent_risk(**kwargs, outcome="ascvd", horizon=30), 1)
        cvd_30a = round(prevent_risk(**kwargs, outcome="cvd", horizon=30), 1)

    return PreventCalculateResponse(
        ascvd_10a=round(prevent_risk(**kwargs, outcome="ascvd", horizon=10), 1),
        cvd_10a=round(prevent_risk(**kwargs, outcome="cvd", horizon=10), 1),
        hf_10a=round(prevent_risk(**kwargs, outcome="hf", horizon=10), 1),
        ascvd_30a=ascvd_30a,
        cvd_30a=cvd_30a,
    )
