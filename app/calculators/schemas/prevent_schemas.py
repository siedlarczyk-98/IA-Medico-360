from pydantic import BaseModel, Field


class PreventCalculateRequest(BaseModel):
    sexo: str = Field(pattern="^[MF]$")
    idade: int = Field(ge=1, le=120)
    ct_mgdl: float = Field(gt=0)
    hdl_mgdl: float = Field(gt=0)
    sbp_mmhg: float = Field(gt=0)
    bmi: float = Field(gt=0)
    egfr: float = Field(gt=0)
    diabetes: bool = False
    fumante: bool = False
    antihtn_use: bool = False
    statin_use: bool = False


class PreventCalculateResponse(BaseModel):
    """`None` quando fora da faixa válida do modelo (idade 30–79, IMC ≤ 39,9)."""

    ascvd_10a: float | None
    cvd_10a: float | None
    hf_10a: float | None
    ascvd_30a: float | None
    cvd_30a: float | None
