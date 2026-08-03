# API 파이프라인 테스트
# pytest를 사용한 단위 테스트로 각 기능 검증
# mock으로 외부 API 호출을 대체해 테스트 속도 향상

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    CollectedData,
    CountryInfo,
    LocationInfo,
    WeatherForecast,
)
from src.pipeline import APICollector


@pytest.fixture
def sample_weather_response():
    """Open-Meteo API 응답 예시"""
    return {
        "latitude": 37.5665,
        "longitude": 126.9780,
        "timezone": "Asia/Seoul",
        "hourly": {
            "time": ["2024-01-01T00:00", "2024-01-01T01:00", "2024-01-01T02:00"],
            "temperature_2m": [5.2, 4.8, 4.5],
            "precipitation_probability": [10, 15, 20],
        },
    }


@pytest.fixture
def sample_country_response():
    """Countries.dev API 응답 예시"""
    return {
        "data": {
            "name": "South Korea",
            "alpha2": "KR",
            "population": 51784059,
            "area": 100363.0,
            "region": "Asia",
        }
    }


@pytest.fixture
def sample_location_response():
    """IP-API 응답 예시"""
    return {
        "status": "success",
        "country": "United States",
        "city": "Mountain View",
        "lat": 37.4192,
        "lon": -122.0574,
        "isp": "Google LLC",
        "timezone": "America/Los_Angeles",
        "query": "8.8.8.8",
    }


@pytest.fixture
def collector(tmp_path):
    """테스트용 수집기 생성 (임시 디렉터리 사용)"""
    return APICollector(output_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_fetch_weather(collector, sample_weather_response):
    """날씨 API 수집 테스트"""
    mock_response = MagicMock()
    mock_response.json.return_value = sample_weather_response

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = mock_response
        async with __import__("httpx").AsyncClient() as client:
            result = await collector.fetch_weather(client)

    assert isinstance(result, WeatherForecast)
    assert result.latitude == 37.5665
    assert len(result.hourly.time) == 3


@pytest.mark.asyncio
async def test_fetch_country(collector, sample_country_response):
    """국가정보 API 수집 테스트"""
    mock_response = MagicMock()
    mock_response.json.return_value = sample_country_response

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = mock_response
        async with __import__("httpx").AsyncClient() as client:
            result = await collector.fetch_country(client)

    assert isinstance(result, CountryInfo)
    assert result.name == "South Korea"
    assert result.population == 51784059


@pytest.mark.asyncio
async def test_fetch_location(collector, sample_location_response):
    """위치정보 API 수집 테스트"""
    mock_response = MagicMock()
    mock_response.json.return_value = sample_location_response

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = mock_response
        async with __import__("httpx").AsyncClient() as client:
            result = await collector.fetch_location(client)

    assert isinstance(result, LocationInfo)
    assert result.city == "Mountain View"
    assert result.country == "United States"


def test_weather_model_validation():
    """WeatherForecast 모델 검증 테스트"""
    valid_data = {
        "latitude": 37.5665,
        "longitude": 126.9780,
        "timezone": "Asia/Seoul",
        "hourly": {
            "time": ["2024-01-01T00:00"],
            "temperature_2m": [5.2],
            "precipitation_probability": [10],
        },
    }
    weather = WeatherForecast(**valid_data)
    assert weather.latitude == 37.5665


def test_country_model_validation():
    """CountryInfo 모델 검증 테스트"""
    valid_data = {
        "name": "South Korea",
        "alpha2": "KR",
        "population": 51784059,
    }
    country = CountryInfo(**valid_data)
    assert country.name == "South Korea"


def test_save_to_csv(
    collector,
    sample_weather_response,
    sample_country_response,
    sample_location_response,
):
    """CSV 저장 기능 테스트"""
    data = CollectedData(
        timestamp=datetime.now(),
        weather=WeatherForecast(**sample_weather_response),
        country=CountryInfo(**sample_country_response["data"]),
        location=LocationInfo(**sample_location_response),
    )

    filepath = collector.save_to_csv(data, "test.csv")
    assert filepath.exists()
    assert filepath.suffix == ".csv"

    # 파일 내용 검증
    with open(filepath) as f:
        lines = f.readlines()
    assert len(lines) == 4  # 헤더 + 3행


def test_save_to_parquet(
    collector,
    sample_weather_response,
    sample_country_response,
    sample_location_response,
):
    """Parquet 저장 기능 테스트"""
    data = CollectedData(
        timestamp=datetime.now(),
        weather=WeatherForecast(**sample_weather_response),
        country=CountryInfo(**sample_country_response["data"]),
        location=LocationInfo(**sample_location_response),
    )

    filepath = collector.save_to_parquet(data, "test.parquet")
    assert filepath.exists()
    assert filepath.suffix == ".parquet"


def test_save_all(
    collector,
    sample_weather_response,
    sample_country_response,
    sample_location_response,
):
    """CSV와 Parquet 동시 저장 테스트"""
    data = CollectedData(
        timestamp=datetime.now(),
        weather=WeatherForecast(**sample_weather_response),
        country=CountryInfo(**sample_country_response["data"]),
        location=LocationInfo(**sample_location_response),
    )

    result = collector.save_all(data)

    assert "csv" in result
    assert "parquet" in result
    assert Path(result["csv"]["path"]).exists()
    assert Path(result["parquet"]["path"]).exists()

    # 파일 크기 정보 (작은 데이터에서는 Parquet 오버헤드로 CSV가 더 작을 수 있음)
    # 하지만 두 형식 모두 저장되었는지 확인
    assert result["csv"]["size_kb"] > 0
    assert result["parquet"]["size_kb"] > 0
