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


class PreventAviso(BaseModel):
    """Por que um conjunto de desfechos não foi calculado."""

    codigo: str
    mensagem: str
    desfechos: list[str]


class PreventCalculateResponse(BaseModel):
    """
    Os dez campos do modelo base (cinco desfechos x dois horizontes). `None`
    segue a regra da AHA, que invalida
    desfecho a desfecho: idade fora de 30–79 derruba tudo; idade > 59 derruba só
    os 30 anos; CT/HDL fora de faixa derrubam os desfechos que usam lipídios
    (todos menos IC); IMC fora de 18,5–39,9 derruba só os de IC; PAS ou TFGe
    fora de faixa derrubam tudo.
    """

    cvd_10a: float | None
    ascvd_10a: float | None
    chd_10a: float | None
    stroke_10a: float | None
    hf_10a: float | None
    cvd_30a: float | None
    ascvd_30a: float | None
    chd_30a: float | None
    stroke_30a: float | None
    hf_30a: float | None
    avisos: list[PreventAviso] = []
