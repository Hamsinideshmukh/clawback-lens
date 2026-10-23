from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import upload_limit
from app.core.config import get_settings
from app.core.errors import InvalidInput
from app.db.session import get_db
from app.schemas.case import DocumentDetail, DocumentOut
from app.services import case_service, document_service

router = APIRouter(tags=["documents"])


@router.post(
    "/cases/{case_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(upload_limit)],
)
async def upload_document(case_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> DocumentOut:
    """Stores the file and queues it for the vision pipeline. Poll the
    document until `status` is `completed` or `failed`."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise InvalidInput(f"Documents must be {get_settings().max_upload_mb} MB or smaller")
    case = case_service.get_case(db, case_id)
    document = document_service.submit(
        db, case, file.filename or "document", file.content_type or "application/octet-stream", content
    )
    db.commit()
    return DocumentOut.model_validate(document)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentDetail:
    return DocumentDetail.model_validate(document_service.get(db, document_id))


@router.get("/documents/{document_id}/preview", response_class=Response)
def get_preview(document_id: str, db: Session = Depends(get_db)) -> Response:
    """Deskewed first page; analysis boxes are normalised to this image."""
    return Response(
        document_service.preview_jpeg(db, document_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
