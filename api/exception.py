from typing import Optional

from rest_framework import status
from rest_framework.exceptions import APIException


class CustomAPIException(APIException):
    def __init__(
        self, detail: Optional[str] = None, code: Optional[str] = None
    ) -> None:
        if detail is not None:
            self.default_detail = detail

        if code is not None:
            self.default_code = code
        super().__init__(detail=self.default_detail, code=self.default_code)

    def get_response(self) -> dict:
        return {
            "success": False,
            "code": self.default_code,
            "message": self.default_detail,
            "data": {},
        }


class ExternalAPIFailedException(CustomAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "EXTERNAL_API_FAILED"
    default_detail = "External API failed"
