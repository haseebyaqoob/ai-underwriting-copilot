from fastapi import HTTPException, status


class InvalidCredentialsError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")


class EmailAlreadyRegisteredError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")


class InvalidOrExpiredTokenError(HTTPException):
    def __init__(self, detail: str = "Session expired. Please sign in again."):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenRoleError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this resource.")


class ApplicationNotFoundError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")


class ApplicationAccessDeniedError(HTTPException):
    
    def __init__(self):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this application.")


class ApplicationStateError(HTTPException):
    

    def __init__(self, detail: str):
        super().__init__(status_code=422, detail=detail)


class DocumentNotFoundError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")


class DocumentAccessDeniedError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this document.")


class DocumentNotReadyError(HTTPException):
    

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document hasn't finished processing yet, so there's nothing to confirm.",
        )


class UnsupportedFileTypeError(HTTPException):
    def __init__(self, detected_type: str | None = None):
        detail = "Unsupported file type."
        if detected_type:
            detail += f" Detected: {detected_type}. Accepted: PDF, JPG, PNG, HEIC."
        super().__init__(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)


class FileTooLargeError(HTTPException):
    def __init__(self, max_mb: int):
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {max_mb}MB limit.",
        )


class DuplicateSingleSlotDocumentError(HTTPException):
   

    def __init__(self, label: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{label} already has a document on file. To replace it, resubmit "
                "with replaces_document_id set to the existing document instead of "
                "uploading a new one."
            ),
        )


class NotFoundError(HTTPException):
    """Generic 404 for cross-cutting resources (e.g. notifications) that
    don't warrant their own dedicated exception class the way
    Application/Document do."""

    def __init__(self, detail: str = "Not found."):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
