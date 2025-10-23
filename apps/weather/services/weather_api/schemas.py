# apps/weather/services/weather_api/schemas.py
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Literal


class LocationSchema(BaseModel):
    """위치 정보 스키마"""

    city: str = Field(min_length=1, max_length=100)
    country_code: str = Field(min_length=2, max_length=2)


class DateRangeSchema(BaseModel):
    """날짜 범위 스키마"""

    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class ForecastOptionsSchema(BaseModel):
    """예보 옵션 스키마"""

    include_hourly: Literal["Y", "N"] = "N"
    units: Literal["metric", "imperial"] = "metric"
    language: str = "ko"
    timezone: str = "Asia/Seoul"


class WeatherForecastRequestSchema(BaseModel):
    """날씨 예보 요청 스키마"""

    model_config = ConfigDict(validate_assignment=True, str_strip_whitespace=True)

    api_key: str
    location: LocationSchema
    date_range: DateRangeSchema
    options: ForecastOptionsSchema
    format: Literal["json", "xml"] = "json"

    def to_api_body(self) -> dict:
        """API 요청 바디로 변환"""
        return {
            "apiKey": self.api_key,
            "location": {
                "city": self.location.city,
                "countryCode": self.location.country_code,
            },
            "dateRange": {
                "start": self.date_range.start,
                "end": self.date_range.end,
            },
            "options": {
                "includeHourly": self.options.include_hourly,
                "units": self.options.units,
                "language": self.options.language,
                "timezone": self.options.timezone,
            },
            "format": self.format,
        }


class WeatherForecastResponseSchema(BaseModel):
    """날씨 예보 응답 스키마"""

    temperature: float = Field(ge=-100, le=100)
    humidity: int = Field(ge=0, le=100)
    condition: str
    forecast_date: str


class CommonAPIResponseSchema(BaseModel):
    """외부 API 공통 응답 스키마"""

    errYn: Literal["Y", "N"]
    errMsg: str = ""
    userTrNo: Optional[str] = None
    hyphenTrNo: Optional[str] = None


class WeatherAPIResponseSchema(BaseModel):
    """전체 API 응답 스키마 (공통 + 데이터)"""

    common: CommonAPIResponseSchema
    data: Optional[WeatherForecastResponseSchema] = None

    @property
    def is_error(self) -> bool:
        """에러 응답 여부 확인"""
        return self.common.errYn == "Y"

    @property
    def error_message(self) -> str:
        """에러 메시지 반환"""
        return self.common.errMsg if self.is_error else ""


# ============================================================
# View Request 스키마 (DRF request.data 검증용)
# ============================================================


class WeatherForecastViewRequestSchema(BaseModel):
    """
    View에서 받는 요청 데이터 스키마

    용도: DRF의 request.data를 검증

    Before (나쁜 예시):
    - request.data.get("city") → 타입 검증 없음, None 가능

    After (좋은 예시):
    - Pydantic으로 검증 → 타입 안전, 자동 검증
    """

    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    city: str = Field(min_length=1, max_length=100, description="도시명")
    country_code: str = Field(min_length=2, max_length=2, description="국가 코드 (2자)")
    start_date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$", description="시작 날짜 (YYYY-MM-DD)"
    )
    end_date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$", description="종료 날짜 (YYYY-MM-DD)"
    )
    include_hourly: bool = False
    units: Literal["metric", "imperial"] = "metric"

    @field_validator("country_code")
    @classmethod
    def country_code_uppercase(cls, v: str) -> str:
        """국가 코드를 대문자로 변환"""
        return v.upper()
