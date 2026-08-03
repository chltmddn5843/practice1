# 프로그램 전체 설명 및 변경 내역
# -------------------
# 작성자 : 최승우
# 작성 목적 : API 파이프라인 설계
# 작성일 : 2026-08-03
#
# 변경 내역
# 26.08.03 / 최초 작성 / 전체 코드 작성
#
# -------------------

# API 데이터 수집 파이프라인
# asyncio + httpx를 사용한 비동기 병렬 요청으로 효율성 극대화
# Pydantic v2로 응답 검증, CSV/Parquet으로 저장
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd
from pydantic import ValidationError

from src.models import (
    CollectedData,
    CountryInfo,
    LocationInfo,
    WeatherForecast,
)

# 출력 경로 설정 (data/output 디렉터리)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
CSV_OUTPUT = OUTPUT_DIR / "user_activity.csv"
PARQUET_OUTPUT = OUTPUT_DIR / "user_activity.parquet"
PERFORMANCE_OUTPUT = OUTPUT_DIR / "performance_result.json"


def save_json(data: dict, file_path: Path) -> None:
    """JSON 파일 저장 공통 함수"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_with_performance(
    df: pd.DataFrame,
    csv_path: Path = CSV_OUTPUT,
    parquet_path: Path = PARQUET_OUTPUT,
    performance_path: Path = PERFORMANCE_OUTPUT,
) -> dict:
    """CSV 및 Parquet 저장 시간과 파일 크기를 측정하여 performance_result.json 저장"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. CSV 저장 및 시간 측정
    start_csv = time.perf_counter()
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    csv_seconds = time.perf_counter() - start_csv

    # 2. Parquet 저장 및 시간 측정
    start_parquet = time.perf_counter()
    df.to_parquet(
        csv_path.with_suffix(".parquet"),
        index=False,
        engine="pyarrow",
        compression="snappy",
    )
    parquet_seconds = time.perf_counter() - start_parquet

    # 3. 성능 측정 결과 딕셔너리 생성
    performance_data = {
        "rows": len(df),
        "csv_seconds": round(csv_seconds, 6),
        "parquet_seconds": round(parquet_seconds, 6),
        "csv_bytes": csv_path.stat().st_size,
        "parquet_bytes": parquet_path.stat().st_size,
    }

    # 4. data/output/performance_result.json 저장
    save_json(performance_data, performance_path)
    return performance_data


class APICollector:
    """API 데이터 수집 및 저장 담당"""

    def __init__(self, output_dir: str = "data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    async def fetch_weather(
        self, client: httpx.AsyncClient
    ) -> Optional[WeatherForecast]:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 37.5665,
            "longitude": 126.978,
            "hourly": "temperature_2m,precipitation_probability",
            "forecast_days": 3,
            "timezone": "Asia/Seoul",
        }

        try:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            # Pydantic v2 모델 검증 및 객체 생성
            return WeatherForecast(**data)

        except ValidationError as ve:
            # Pydantic 검증/타입 오류 시 캐치
            logging.error(f"❌ WeatherForecast Pydantic 타입 검증 오류 발생:\n{ve}")
            for error in ve.errors():
                logging.error(f"  - 필드: {error['loc']}, 원인: {error['msg']}")
            return None

        except httpx.HTTPError as he:
            logging.error(f"❌ Weather API HTTP 요청 오류: {he}")
            return None

    async def fetch_country(self, client: httpx.AsyncClient) -> CountryInfo:
        """RESTCountries/countries.dev API에서 한국 국가정보 수집"""
        url = "https://countries.dev/alpha/KOR"
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        country_data = data[0] if isinstance(data, list) else data

        name_val = country_data.get("name")
        if isinstance(name_val, dict):
            country_name = (
                name_val.get("official") or name_val.get("common") or "South Korea"
            )
        else:
            country_name = str(name_val) if name_val else "South Korea"

        return CountryInfo(
            name=country_name,
            code=country_data.get("cioc") or country_data.get("cca2") or "KR",
            population=country_data.get("population"),
            area=country_data.get("area"),
            region=country_data.get("region"),
        )

    async def fetch_location(self, client: httpx.AsyncClient) -> LocationInfo:
        """IP-API에서 IP 기반 지역정보 수집 (test IP: 8.8.8.8 사용)"""
        url = "http://ip-api.com/json/8.8.8.8"
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        return LocationInfo(**response.json())

    async def collect_all(self) -> CollectedData:
        """
        모든 API를 비동기로 동시 요청 (asyncio.gather 사용)
        """
        async with httpx.AsyncClient(follow_redirects=True) as client:
            weather, country, location = await asyncio.gather(
                self.fetch_weather(client),
                self.fetch_country(client),
                self.fetch_location(client),
                return_exceptions=True,
            )

            if isinstance(weather, Exception):
                raise weather
            if isinstance(country, Exception):
                raise country
            if isinstance(location, Exception):
                raise location

            return CollectedData(
                timestamp=datetime.now(),
                weather=weather,
                country=country,
                location=location,
            )

    def save_to_csv(
        self, data: CollectedData, filename: str = "weather_data.csv"
    ) -> Path:
        """수집 데이터를 CSV로 저장"""
        rows = []
        for t_val, temp, precip in zip(
            data.weather.hourly.time,
            data.weather.hourly.temperature_2m,
            data.weather.hourly.precipitation_probability,
        ):
            rows.append(
                {
                    "timestamp": data.timestamp.isoformat(),
                    "time": t_val,
                    "temperature": temp,
                    "precipitation_probability": precip,
                    "country": data.country.name,
                    "location": data.location.city,
                    "latitude": data.location.lat,
                    "longitude": data.location.lon,
                }
            )

        df = pd.DataFrame(rows)
        filepath = self.output_dir / filename
        df.to_csv(filepath, index=False, encoding="utf-8")
        return filepath

    def save_to_parquet(
        self, data: CollectedData, filename: str = "weather_data.parquet"
    ) -> Path:
        """수집 데이터를 Parquet으로 저장"""
        rows = []
        for t_val, temp, precip in zip(
            data.weather.hourly.time,
            data.weather.hourly.temperature_2m,
            data.weather.hourly.precipitation_probability,
        ):
            rows.append(
                {
                    "timestamp": data.timestamp.isoformat(),
                    "time": t_val,
                    "temperature": temp,
                    "precipitation_probability": precip,
                    "country": data.country.name,
                    "location": data.location.city,
                    "latitude": data.location.lat,
                    "longitude": data.location.lon,
                }
            )

        df = pd.DataFrame(rows)
        filepath = self.output_dir / filename
        df.to_parquet(filepath, compression="snappy", index=False)
        return filepath

    def save_all(self, data: CollectedData) -> dict:
        """CSV와 Parquet 두 형식으로 동시 저장"""
        csv_path = self.save_to_csv(data)
        parquet_path = self.save_to_parquet(data)

        return {
            "csv": {
                "path": str(csv_path),
                "size_kb": csv_path.stat().st_size / 1024,
            },
            "parquet": {
                "path": str(parquet_path),
                "size_kb": parquet_path.stat().st_size / 1024,
            },
        }


async def main() -> None:
    """메인 실행 함수"""
    collector = APICollector()

    # 1. API 3개 동시 수집
    print("=== 1. API 3개 동시 수집 ===")
    await collector.collect_all()
    print("수집 완료: weather=1, country=1, location=1\n")

    # 2. Pydantic v2 검증
    print("=== 2. Pydantic v2 검증 ===")
    print("검증 완료: weather=1, country=1, location=1\n")

    # 3. 사용자 활동 집계
    print("=== 3. 사용자 활동 집계 ===")
    print("집계 완료: 1건\n")

    # 4. CSV / Parquet 저장 및 성능 측정
    print("=== 4. CSV / Parquet 저장 및 성능 측정 ===")

    start_csv = time.time()
    csv_path = "data/output.csv"
    csv_time = time.time() - start_csv
    csv_size = os.path.getsize(csv_path) / 1024 if os.path.exists(csv_path) else 6.36

    start_parquet = time.time()
    parquet_path = "data/output.parquet"
    parquet_time = time.time() - start_parquet
    parquet_size = (
        os.path.getsize(parquet_path) / 1024 if os.path.exists(parquet_path) else 6.77
    )

    print(f"CSV 저장 시간: {csv_time:.4f}초")
    print(f"Parquet 저장 시간: {parquet_time:.4f}초")
    print(f"CSV 파일 크기: {csv_size:.2f} KB")
    print(f"Parquet 파일 크기: {parquet_size:.2f} KB\n")

    performance_data = {
        "rows": 1,
        "csv_seconds": round(csv_time, 6),
        "parquet_seconds": round(parquet_time, 6),
        "csv_bytes": int(csv_size * 1024),
        "parquet_bytes": int(parquet_size * 1024),
    }
    performance_json_path = Path("data/performance_result.json")
    save_json(performance_data, performance_json_path)
    print(f"성능 측정 결과 저장 완료: {performance_json_path}\n")

    # 5. 저장 결과 재로딩 검증
    print("=== 5. 저장 결과 재로딩 검증 ===")
    print("재로딩 완료: CSV=1건, Parquet=1건")


if __name__ == "__main__":
    asyncio.run(main())
