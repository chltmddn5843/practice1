# API 데이터 수집 파이프라인 

서울 날씨, 국가정보, IP 기반 위치정보를 비동기로 수집하는 데이터 파이프라인 프로젝트

## 개요

**3개 API 병렬 수집:**

- **Open-Meteo**: 서울 3일 시간대별 기온·강수확률 (72시간)
- **RESTCountries**: 한국 국가정보 (인구, 면적, 지역)
- **IP-API**: IP 기반 지역정보 (8.8.8.8 기준)

**저장 형식:**

- CSV (가독성, 6.36 KB)
- Parquet (압축, 6.77 KB)

## 핵심 학습 내용

### 1. 비동기 API 요청의 효율성

```python
# asyncio.gather()로 3개 API를 동시 호출 (순차 요청 대비 훨씬 빠름)
weather, country, location = await asyncio.gather(
    fetch_weather(client),
    fetch_country(client),
    fetch_location(client),
    return_exceptions=True
)
```

**학습**: 블로킹 없이 여러 I/O 작업을 동시에 처리 → 전체 실행 시간 단축

### 2. Pydantic v2 마이그레이션

```python
# v1: class Config 방식 (deprecated)
# v2: ConfigDict 방식 (권장)
model_config = ConfigDict(populate_by_name=True)
```

**학습**: Pydantic v2는 더 명시적이고 IDE 지원 향상, `model_config`로 통일

### 3. 데이터 검증의 중요성

- Pydantic으로 API 응답 자동 검증
- 타입 미스매치 조기 발견
- 런타임 오류 방지

### 4. 테스트 주도 개발 (TDD)

```python
# mock으로 외부 API 대체 → 테스트 속도 빠름 (0.4초)
# return_exceptions=True로 안전한 비동기 예외 처리
```

**학습**: 단위 테스트는 개발 단계에서 큰 시간 절약, 리팩토링 시 신뢰성 제공

### 5. 코드 품질 자동화

- `pre-commit hooks`: 커밋 전 자동 검사
- Black (포맷), Flake8 (스타일), Mypy (타입), Ruff (고급 분석)
- 일관성 있는 코드베이스 유지

## 트러블슈팅

| 문제                  | 원인                    | 해결책                                               |
| --------------------- | ----------------------- | ---------------------------------------------------- |
| Countries.dev API 404 | 엔드포인트 변경/폐쇄    | RESTCountries API로 전환                             |
| 301 Redirect 오류     | HTTP 리다이렉트 미처리  | `httpx.AsyncClient(follow_redirects=True)` 설정    |
| Pydantic 경고         | v1 ConfigDict 방식 사용 | `model_config = ConfigDict(...)` 로 마이그레이션   |
| 테스트 실패           | API 응답 구조 변경      | Mock 데이터를 새로운 API 구조로 업데이트             |
| .venv 대량 커밋       | `.gitignore` 누락     | `.gitignore` 생성 후 `git rm -r --cached .venv/` |

## 프로젝트 구조

```
src/
  ├── models.py          # Pydantic v2 데이터 모델 (3개)
  │   ├── WeatherForecast
  │   ├── CountryInfo
  │   └── LocationInfo
  │
  └── pipeline.py        # APICollector 클래스
      ├── fetch_weather()       # Open-Meteo 수집
      ├── fetch_country()       # RESTCountries 수집
      ├── fetch_location()      # IP-API 수집
      ├── collect_all()         # 비동기 병렬 수집
      ├── save_to_csv()         # CSV 저장
      └── save_to_parquet()     # Parquet 저장

tests/
  └── test_pipeline.py   # 8개 단위 테스트 (모두 PASS)
      ├── test_fetch_* (3개)    # API 수집 테스트
      ├── test_*_model_validation (2개) # 데이터 모델 검증
      └── test_save_* (3개)     # 파일 저장 테스트

data/                    # 수집 데이터 저장 폴더
```

## 🚀 사용 방법

### 1. 환경 설정

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. 파이프라인 실행

```bash
PYTHONPATH=. python src/pipeline.py
```

### 3. 테스트 실행

```bash
pytest tests/ -v
```

### 4. 코드 품질 검사

```bash
pre-commit run --all-files
```

## 💡 주요 통찰

### 비동기 vs 동기

- **동기**: 3개 API × 1초 = 3초
- **비동기**: max(1초, 1초, 1초) = 1초
- **효과**: 66% 성능 향상

### CSV vs Parquet

| 형식    | 장점                             | 단점           |
| ------- | -------------------------------- | -------------- |
| CSV     | 텍스트 기반, 어디서나 열 수 있음 | 용량 커짐      |
| Parquet | 압축, 스키마 지원, 빠른 쿼리     | 전문 도구 필요 |

**결론**: 소규모 데이터는 CSV, 빅데이터는 Parquet 추천

### 코드 품질의 가치

- pre-commit 없음 → 일관성 낮음, 버그 잦음
- pre-commit 적용 → 코드 스타일 통일, 명백한 오류 조기 발견
- 팀 프로젝트에서 필수

## 📈 성과

✅ 비동기 API 수집으로 성능 최적화
✅ Pydantic v2로 타입 안정성 확보
✅ 8/8 테스트 통과
✅ pre-commit hooks로 자동화된 품질 관리
✅ 2가지 형식으로 데이터 저장 및 비교

## 📚 참고 자료

- [Pydantic v2 공식 문서](https://docs.pydantic.dev/latest/)
- [Python asyncio 공식 문서](https://docs.python.org/3/library/asyncio.html)
- [Pre-commit 공식 문서](https://pre-commit.com/)
- [RESTCountries API](https://restcountries.com/)
