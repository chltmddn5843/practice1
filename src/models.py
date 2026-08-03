# 프로그램 전체 설명 및 변경 내역
# -------------------
# 작성자 : 최승우
# 작성일 : 2026-08-03
# 작성 목적
# 1) Pydantic v2를 사용한 API 응답 스키마 정의
# 2) 각 API에서 수집한 데이터를 검증하고 타입 안정성 보장 확인
#
# 변경 내역
# 26.08.03 / 최초 작성 / 전체 코드 작성
#
# -------------------

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ===== Open-Meteo API =====
class HourlyData(BaseModel):
    """시간대별 기온과 강수확률 데이터"""

    time: list[str]
    temperature_2m: list[float]
    precipitation_probability: list[int]


class WeatherForecast(BaseModel):
    """Open-Meteo 날씨 예보 API 응답"""

    model_config = ConfigDict(populate_by_name=True)

    latitude: float
    longitude: float
    timezone: str
    hourly: HourlyData


# ===== Countries.dev API =====
class CountryInfo(BaseModel):
    """국가 기본 정보"""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    code: str = Field(alias="alpha2")
    population: Optional[int] = None
    area: Optional[float] = None
    region: Optional[str] = None


# ===== IP-API =====
class LocationInfo(BaseModel):
    """IP 기반 지역 정보"""

    model_config = ConfigDict(populate_by_name=True)
    status: str
    country: str
    city: str
    lat: float
    lon: float
    isp: str
    timezone: str
    query: str = Field(alias="query")


# ===== 통합 데이터 모델 =====
class CollectedData(BaseModel):
    """수집된 모든 API 데이터를 통합"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    timestamp: datetime
    weather: WeatherForecast
    country: CountryInfo
    location: LocationInfo
