"""기본 파일 Tool의 사용자 수정 가능 오류."""


class BuiltinToolError(ValueError):
    """원문·경로·내부 예외를 노출하지 않는 안정적인 Tool 오류."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"error_code": self.code, "message": self.message}

