from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.calculators.formulas.cardiologia.prevent import prevent_all, prevent_avisos
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
    Escore PREVENT (AHA, Khan et al. 2024) — modelo base, seis desfechos.
    Campos fora da faixa de validade do modelo vêm `None`, seguindo a regra da
    AHA (`AHAprevent::pred_risk_base`), que invalida desfecho a desfecho e não
    em bloco. Não persiste execução nem audit log — cálculo sem estado.
    """
    dados = dict(
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
    riscos = prevent_all(**dados)
    return PreventCalculateResponse(
        # 2 casas, igual ao MDCalc. Os limiares da SBC (5% e 20%) são aplicados no
        # front sobre este valor já arredondado, então a precisão extra muda a
        # classificação em casos de borda — para mais perto do valor verdadeiro.
        **{campo: None if valor is None else round(valor, 2) for campo, valor in riscos.items()},
        avisos=prevent_avisos(**dados),
    )
