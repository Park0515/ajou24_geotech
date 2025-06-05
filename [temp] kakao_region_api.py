import pandas as pd
import requests
import time

# 1) 카카오 REST API 키 (발급받은 키 입력)
REST_API_KEY = "5d7a18fb2f6e17b780fbd79349d7c310"
HEADERS = {
    "Authorization": f"KakaoAK {REST_API_KEY}"
}

# 2) station_position.csv 읽어오기
#    - '고유역번호', '역명', '위도', '경도' 컬럼이 있다고 가정
try:
    stations = pd.read_csv('C:/project_geotech/station_position.csv', encoding='utf-8')
except UnicodeDecodeError:
    stations = pd.read_csv('C:/project_geotech/station_position.csv', encoding='cp949')
stations = stations.rename(columns={"고유역번호(외부역코드)": "고유역번호"})

# 3) 결과를 저장할 칼럼 미리 추가
stations["region_1depth_name"] = None  # 시/도
stations["region_2depth_name"] = None  # 시/군/구
stations["region_3depth_name"] = None  # 행정동(읍/면/동)
stations["region_code"] = None         # 행정동 코드 (시군구마다 다름)

# 4) 좌표→행정구역 API 호출 함수 정의
def coord_to_region(longitude: float, latitude: float):
    """
    카카오 로컬 API를 사용해 (longitude, latitude)를 행정동 정보로 변환
    반환값: dict {'region_1depth_name', 'region_2depth_name', 'region_3depth_name', 'code'}
    """
    url = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"
    params = {
        "x": longitude,  # 경도
        "y": latitude    # 위도
    }
    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()
    data = res.json()

    # 'region_type'이 'H'인 것만 선택
    h_docs = [doc for doc in data.get("documents", []) if doc.get("region_type") == "H"]
    if h_docs:
        doc = h_docs[0]
        return {
            "region_1depth_name": doc.get("region_1depth_name"),
            "region_2depth_name": doc.get("region_2depth_name"),
            "region_3depth_name": doc.get("region_3depth_name"),
            "code": doc.get("code")
        }
    else:
        return {
            "region_1depth_name": None,
            "region_2depth_name": None,
            "region_3depth_name": None,
            "code": None
        }

# 5) 반복문을 돌면서 API 호출 및 결과 채우기
for idx, row in stations.iterrows():
    lat = row["위도"]
    lon = row["경도"]
    try:
        info = coord_to_region(lon, lat)
        stations.at[idx, "region_1depth_name"] = info["region_1depth_name"]
        stations.at[idx, "region_2depth_name"] = info["region_2depth_name"]
        stations.at[idx, "region_3depth_name"] = info["region_3depth_name"]
        stations.at[idx, "region_code"] = info["code"]
    except Exception as e:
        print(f"Error at index {idx}, station_id={row['고유역번호']}: {e}")
    time.sleep(0.2)  # API 호출 간 약간의 딜레이 (과도한 요청 방지)

# 6) 결과 확인(상위 5개 출력)
print(stations[["고유역번호", "역명", "region_1depth_name", "region_2depth_name", "region_3depth_name", "region_code"]].head())

# 7) CSV로 저장
stations.to_csv("C:/project_geotech/station_with_region.csv", index=False, encoding="utf-8-sig")
print("station_with_region.csv 파일로 저장 완료")
