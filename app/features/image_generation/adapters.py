from fastapi import HTTPException

from image_generation import ImageGenerationError


def image_error_to_http(exc: ImageGenerationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.error_code, "message": str(exc)})
