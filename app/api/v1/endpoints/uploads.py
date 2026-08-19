import logging
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.models import FileExtraction, User
from app.services.file_extractor_service import (
    ALLOWED_CONTENT_TYPES,
    MAX_EXTRACTED_CHARS,
    MAX_FILE_BYTES,
    MAX_IMAGE_BYTES,
    FileValidationError,
    extract_docx,
    extract_excel,
    extract_image,
    extract_pdf,
    signature_matches,
)
from app.services.pricing import calculate_cost
from app.services.usage_service import check_limit, record_cost

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["Uploads"])


class ExtractResponse(BaseModel):
    file_id: UUID
    file_name: str
    file_type: str


@router.post("/extract", response_model=ExtractResponse)
@limiter.limit("20/minute")
async def extract_file(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe um arquivo, extrai o texto e salva no banco.
    Retorna um file_id que o frontend passa ao Orquestrador/Agregador.
    O backend injeta o contexto do arquivo no prompt internamente,
    evitando que o limite de 4000 chars do campo prompt seja excedido.
    """
    await check_limit(db, user)

    content_type = (file.content_type or "").split(";")[0].strip()

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Tipo de arquivo não suportado: '{content_type}'. "
                "Use PDF, DOCX, XLSX, JPEG, PNG ou WEBP."
            ),
        )

    content = await file.read()

    is_image = ALLOWED_CONTENT_TYPES[content_type] == "image"
    size_limit = MAX_IMAGE_BYTES if is_image else MAX_FILE_BYTES
    if len(content) > size_limit:
        limit_mb = size_limit // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Arquivo maior que {limit_mb} MB.")

    file_kind = ALLOWED_CONTENT_TYPES[content_type]

    # Valida a assinatura real do arquivo (magic bytes) contra o tipo declarado pelo cliente,
    # que não é confiável.
    if not signature_matches(content, file_kind, content_type):
        raise HTTPException(
            status_code=415,
            detail="O conteúdo do arquivo não corresponde ao tipo declarado.",
        )

    image_b64: str | None = None
    image_mime: str | None = None

    # Parsers de documento são síncronos e CPU-bound — rodam em thread para não
    # bloquear o event loop.
    try:
        if file_kind == "pdf":
            text = await anyio.to_thread.run_sync(extract_pdf, content)
        elif file_kind == "docx":
            text = await anyio.to_thread.run_sync(extract_docx, content)
        elif file_kind == "xlsx":
            text = await anyio.to_thread.run_sync(extract_excel, content)
        else:
            img = await extract_image(content, content_type)
            text = img["description"]
            image_b64 = img["base64"]
            image_mime = img["media_type"]

            haiku_cost = await calculate_cost(
                db, "claude-haiku-4-5-20251001", img["tokens_in"], img["tokens_out"]
            )
            await record_cost(db, user.id, haiku_cost)
    except FileValidationError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except Exception as e:
        # Arquivo danificado é comportamento normal de usuário: download
        # interrompido, PDF truncado, planilha meio salva. Antes disso subia como
        # 500 — o médico via "Erro interno do servidor" e não sabia que o problema
        # era o arquivo dele, e o Sentry enchia de ruído.
        #
        # O `except` é amplo de propósito: cada parser levanta exceção da sua
        # própria biblioteca (PdfminerException, InvalidFileException, PackageNotFound...)
        # e enumerá-las seria uma lista que envelhece a cada upgrade. Fica em
        # `warning`, não `error`: é problema do arquivo, não da aplicação.
        logger.warning(
            "Falha ao extrair %s: %s: %s", file_kind, type(e).__name__, e,
            extra={"file_kind": file_kind, "erro": type(e).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Não consegui ler este arquivo — ele parece danificado ou incompleto. "
                "Tente abrir no seu computador para conferir, ou reenvie."
            ),
        ) from e

    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS] + "\n\n[... conteúdo truncado — arquivo muito extenso]"

    extraction = FileExtraction(
        user_id=user.id,
        file_name=file.filename or "arquivo",
        file_type=file_kind,
        extracted_text=text,
        image_base64=image_b64,
        image_media_type=image_mime,
    )
    db.add(extraction)
    await db.commit()
    await db.refresh(extraction)

    return ExtractResponse(
        file_id=extraction.id,
        file_name=extraction.file_name,
        file_type=extraction.file_type,
    )
