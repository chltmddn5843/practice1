# API 데이터 수집 파이프라인
# asyncio + httpx를 사용한 비동기 병렬 요청으로 효율성 극대화
# Pydantic v2로 응답 검증, CSV/Parquet으로 저장

import asyncio
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd

from src.models import (
    CollectedData,
    CountryInfo,
    LocationInfo,
    WeatherForecast,
)


class APICollector:
    """API 데이터 수집 및 저장 담당"""

    def __init__(self, output_dir: str = "data"):
        """
        출력 디렉터리 초기화

        Args:
            output_dir: 데이터 저장 경로
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    async def fetch_weather(self, client: httpx.AsyncClient) -> WeatherForecast:
        """
        Open-Meteo API에서 서울 3일 날씨 데이터 수집
        비동기 요청으로 블로킹 없이 동시 처리 가능
        """
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 37.5665,
            "longitude": 126.9780,
            "hourly": "temperature_2m,precipitation_probability",
            "forecast_days": 3,
            "timezone": "Asia/Seoul",
        }
        response = await client.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        return WeatherForecast(**response.json())

    async def fetch_country(self, client: httpx.AsyncClient) -> CountryInfo:
        """
        RESTCountries API에서 한국 국가정보 수집
        Countries.dev 대신 공개 API 사용
        """
        url = "https://restcountries.com/v3.1/alpha/kor"
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        # API 응답은 배열 형식
        country_data = data[0] if isinstance(data, list) else data
        common_name = country_data.get("name", {}).get("common", "South Korea")
        official_name = country_data.get("name", {}).get(
            "official", "Republic of Korea"
        )

        return CountryInfo(
            name=official_name or common_name,
            code=country_data.get("cca2", "KR"),
            population=country_data.get("population"),
            area=country_data.get("area"),
            region=country_data.get("region"),
        )

    async def fetch_location(self, client: httpx.AsyncClient) -> LocationInfo:
        """
        IP-API에서 IP 기반 지역정보 수집
        test IP(8.8.8.8) 사용
        """
        url = "http://ip-api.com/json/8.8.8.8"
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        return LocationInfo(**response.json())

    async def collect_all(self) -> CollectedData:
        """
        모든 API를 비동기로 동시 요청
        asyncio.gather()로 병렬 처리: 순차 요청보다 훨씬 빠름
        """
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # 세 개 API를 동시에 호출
            weather, country, location = await asyncio.gather(
                self.fetch_weather(client),
                self.fetch_country(client),
                self.fetch_location(client),
                return_exceptions=True,
            )

            # 예외 처리
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

    def save_to_csv(self, data: CollectedData, filename: str = "weather_data.csv"):
        """
        수집 데이터를 CSV로 저장
        CSV는 텍스트 기반으로 가독성 좋음
        """
        # 시간대별 데이터를 flatten해서 행 단위로 변환
        rows = []
        for time, temp, precip in zip(
            data.weather.hourly.time,
            data.weather.hourly.temperature_2m,
            data.weather.hourly.precipitation_probability,
        ):
            rows.append(
                {
                    "timestamp": data.timestamp.isoformat(),
                    "time": time,
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
    ):
        """
        수집 데이터를 Parquet으로 저장
        Parquet은 이진 형식으로 압축률과 성능 우수
        대용량 데이터 처리에 적합
        """
        # 시간대별 데이터를 flatten해서 행 단위로 변환
        rows = []
        for time, temp, precip in zip(
            data.weather.hourly.time,
            data.weather.hourly.temperature_2m,
            data.weather.hourly.precipitation_probability,
        ):
            rows.append(
                {
                    "timestamp": data.timestamp.isoformat(),
                    "time": time,
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
        """
        CSV와 Parquet 두 형식으로 동시 저장
        파일 크기와 성능 비교 가능
        """
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


async def main():
    """메인 실행 함수"""
    collector = APICollector()

    print("🔄 API 데이터 수집 중...")
    data = await collector.collect_all()

    print("✅ 데이터 수집 완료")
    print(f"   - 타임스탬프: {data.timestamp}")
    print(f"   - 국가: {data.country.name}")
    print(f"   - 도시: {data.location.city}")
    print(f"   - 수집된 시간대 수: {len(data.weather.hourly.time)}")

    print("\n💾 데이터 저장 중...")
    result = collector.save_all(data)

    print("✅ 저장 완료")
    print(f"   CSV: {result['csv']['path']} ({result['csv']['size_kb']:.2f} KB)")
    print(
        f"   Parquet: {result['parquet']['path']}"
        f" ({result['parquet']['size_kb']:.2f} KB)"
    )

    # 저장 크기 비교
    csv_size = result["csv"]["size_kb"]
    parquet_size = result["parquet"]["size_kb"]
    compression_ratio = (1 - parquet_size / csv_size) * 100
    print(f"\n📊 압축 효율: Parquet이 CSV 대비 {compression_ratio:.1f}% 더 작음")


if __name__ == "__main__":
    asyncio.run(main())
