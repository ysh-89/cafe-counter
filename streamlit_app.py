import math
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

# 1. 페이지 기본 설정
st.set_page_config(page_title="위치 기반 카페 통합 정보 앱", layout="wide")

st.title("☕ 위치 기반 카페 실시간 지도 앱")
st.write("지도를 이동하면 **현재 화면 중앙 기점으로 가장 가까운 카페 50개**가 실시간으로 표시됩니다.")

# 2. 거리 계산 함수 (Haversine Formula)
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000.0  # 지구 반지름 (미터)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

# 3. 데이터 로드 및 전처리 (캐싱)
@st.cache_data
def load_cafe_data():
    try:
        df = pd.read_csv("store (1).csv", encoding="cp949")
    except UnicodeDecodeError:
        df = pd.read_csv("store (1).csv", encoding="utf-8")
        
    if "상권업종소분류명" in df.columns:
        cafe_df = df[df["상권업종소분류명"] == "카페"].reset_index(drop=True)
    else:
        cafe_df = df.copy()
    
    cafe_df.columns = cafe_df.columns.str.strip()
    
    # 숫자형 필터링을 위한 데이터 변환
    for col, target_col in [("좌석수", "좌석 수"), ("1인좌석수", "1인 좌석 수"), ("콘센트", "콘센트"), ("와이파이속도", "와이파이 속도")]:
        if target_col in cafe_df.columns:
            cafe_df[col] = cafe_df[target_col].astype(str).str.replace(r'[^0-9.]', '', regex=True)
            cafe_df[col] = pd.to_numeric(cafe_df[col], errors='coerce').fillna(0)
        else:
            cafe_df[col] = 0
            
    return cafe_df

df_cafe = load_cafe_data()

# Session State 초기화
if "cafe_counts" not in st.session_state:
    st.session_state.cafe_counts = {}
if "last_message" not in st.session_state:
    st.session_state.last_message = "아직 측정 이력이 없습니다."
if "last_status" not in st.session_state:
    st.session_state.last_status = "info"
if "map_center" not in st.session_state:
    # 기본 중심 위치 (데이터 첫 번째 카페 기준)
    st.session_state.map_center = [df_cafe["위도"].iloc[0], df_cafe["경도"].iloc[0]]

# ==========================================
# 4. 사이드바 필터 (지역 선택 + 시설 조건)
# ==========================================
st.sidebar.header("📍 1. 지역 선택")

sido_list = ["전체"] + list(df_cafe["시도명"].unique())
selected_sido = st.sidebar.selectbox("시/도 선택", sido_list)

if selected_sido != "전체":
    sigungu_options = ["전체"] + list(df_cafe[df_cafe["시도명"] == selected_sido]["시군구명"].unique())
else:
    sigungu_options = ["전체"] + list(df_cafe["시군구명"].unique())

selected_sigungu = st.sidebar.selectbox("시/군/구 선택", sigungu_options)

st.sidebar.markdown("---")
st.sidebar.header("🔍 2. 상세 조건 필터")

min_seats = st.sidebar.slider("최소 좌석 수", min_value=0, max_value=150, value=0, step=5)
min_single_seats = st.sidebar.slider("최소 1인 좌석 수", min_value=0, max_value=50, value=0, step=5)
min_outlets = st.sidebar.slider("최소 콘센트 수", min_value=0, max_value=40, value=0, step=5)
min_wifi = st.sidebar.slider("최소 와이파이 속도 (mbps)", min_value=0, max_value=500, value=0, step=25)

# 필터링 적용 로직
filtered_df = df_cafe.copy()

if selected_sido != "전체":
    filtered_df = filtered_df[filtered_df["시도명"] == selected_sido]

if selected_sigungu != "전체":
    filtered_df = filtered_df[filtered_df["시군구명"] == selected_sigungu]

filtered_df = filtered_df[
    (filtered_df["좌석수"] >= min_seats) &
    (filtered_df["1인좌석수"] >= min_single_seats) &
    (filtered_df["콘센트"] >= min_outlets) &
    (filtered_df["와이파이속도"] >= min_wifi)
].reset_index(drop=True)

st.sidebar.markdown(f"**필터링된 총 카페 수**: {len(filtered_df)}개")

if len(filtered_df) == 0:
    st.warning("⚠️ 선택하신 조건에 해당하는 카페가 없습니다. 필터를 완화해 주세요.")
    filtered_df = df_cafe.copy()

# 5. 사용자 위치 수집
st.subheader("📍 1. 위치 권한 확인")
loc = get_geolocation()

user_lat, user_lon = None, None
if loc and 'coords' in loc:
    user_lat = loc['coords']['latitude']
    user_lon = loc['coords']['longitude']
    st.success(f"현재 내 위치 수집 완료 (위도: {user_lat:.5f}, 경도: {user_lon:.5f})")
else:
    st.info("👆 상단 브라우저의 위치 권한 요청을 허용해 주세요.")

st.markdown("---")

# 6. 카페 선택 및 상세 정보 확인 UI
st.subheader("🗺️ 2. 지도 중심 기반 주변 카페 (최대 50개)")

selected_cafe_name = st.selectbox(
    "조회할 카페를 선택하거나 아래 지도를 이동해 보세요:",
    filtered_df["상호명"].unique()
)

cafe_info = filtered_df[filtered_df["상호명"] == selected_cafe_name].iloc[0]
cafe_lat = cafe_info["위도"]
cafe_lon = cafe_info["경도"]

# 통합 카페 정보 카드 출력
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("좌석 수", f"{cafe_info['좌석 수']}")
col2.metric("1인 좌석 수", f"{cafe_info['1인 좌석 수']}")
col3.metric("콘센트", f"{cafe_info['콘센트']}개")
col4.metric("와이파이 속도", f"{cafe_info['와이파이 속도']}")
col5.metric("지역", f"{cafe_info['시군구명']}")

# [핵심 로직] 지도 화면 중앙(Center)을 기점으로 주변 50개 카페 추출
center_lat, center_lon = st.session_state.map_center

filtered_df["dist_from_center"] = filtered_df.apply(
    lambda r: calculate_distance(center_lat, center_lon, r["위도"], r["경도"]), axis=1
)

# 화면 중앙 기준 최단거리 카페 상위 50개 선택
nearby_50_cafes = filtered_df.sort_values("dist_from_center").head(50)

# Folium 지도 생성
m = folium.Map(location=[center_lat, center_lon], zoom_start=15, prefer_canvas=True)

# 50개 카페 마커 표시
for idx, row in nearby_50_cafes.iterrows():
    is_target = (row["상호명"] == selected_cafe_name)
    icon_color = "red" if is_target else "gray"
    icon_shape = "star" if is_target else "coffee"
    
    popup_html = f"<b>{row['상호명']}</b><br>지역: {row['시군구명']}<br>좌석: {row['좌석 수']}<br>콘센트: {row['콘센트']}<br>와이파이: {row['와이파이 속도']}"
    
    folium.Marker(
        location=[row["위도"], row["경도"]],
        popup=folium.Popup(popup_html, max_width=220),
        tooltip=row["상호명"],
        icon=folium.Icon(color=icon_color, icon=icon_shape, prefix="fa")
    ).add_to(m)

# 선택된 카페 반경 100m 원 표시
folium.Circle(
    location=[cafe_lat, cafe_lon],
    radius=100,
    color="blue",
    fill=True,
    fill_opacity=0.2,
    popup=f"{selected_cafe_name} 반경 100m"
).add_to(m)

if user_lat and user_lon:
    folium.Marker(
        location=[user_lat, user_lon],
        popup="내 위치",
        tooltip="현재 사용자 위치",
        icon=folium.Icon(color="blue", icon="user", prefix="fa")
    ).add_to(m)

# 지도 렌더링 및 이벤트 수집
st_data = st_folium(m, width=700, height=400, key="cafe_map")

# [동적 갱신] 사용자가 지도를 이동했을 때 지도 중앙 좌표를 업데이트하여 주변 50개 재계산
if st_data and st_data.get("center"):
    new_center_lat = st_data["center"]["lat"]
    new_center_lon = st_data["center"]["lng"]
    
    # 일정 수준 이상의 이동이 있을 때 세션 상태 업데이트 후 새로고침
    if (abs(new_center_lat - center_lat) > 0.0001 or abs(new_center_lon - center_lon) > 0.0001):
        st.session_state.map_center = [new_center_lat, new_center_lon]
        st.rerun()

st.markdown("---")

# 7. 인원 측정 및 결과 메시지 유지
st.subheader("🏬 3. 인원 측정 및 결과")

if st.button("🔄 인원수 체크 및 자동 카운팅"):
    if user_lat is None or user_lon is None:
        st.session_state.last_message = "⚠️ 사용자 위치 정보(GPS)를 불러오지 못했습니다. 위치 권한을 허용하세요."
        st.session_state.last_status = "error"
    else:
        dist = calculate_distance(user_lat, user_lon, cafe_lat, cafe_lon)
        
        if selected_cafe_name not in st.session_state.cafe_counts:
            st.session_state.cafe_counts[selected_cafe_name] = 0

        if dist <= 100.0:
            st.session_state.cafe_counts[selected_cafe_name] += 1
            st.session_state.last_message = f"✅ 성공! [{selected_cafe_name}] 반경 100m 이내에 있습니다. (거리: {dist:.1f}m) -> 인원수 +1 반영 완료!"
            st.session_state.last_status = "success"
        else:
            st.session_state.last_message = f"❌ 제외됨! [{selected_cafe_name}] 반경 100m 밖(약 {dist:.1f}m 거리)에 있어 인원수 측정에서 제외되었습니다."
            st.session_state.last_status = "warning"

if st.session_state.last_status == "success":
    st.success(st.session_state.last_message)
elif st.session_state.last_status == "warning":
    st.warning(st.session_state.last_message)
elif st.session_state.last_status == "error":
    st.error(st.session_state.last_message)
else:
    st.info(st.session_state.last_message)

current_count = st.session_state.cafe_counts.get(selected_cafe_name, 0)
st.metric(label=f"[{selected_cafe_name}] 현재 집계된 인원수", value=f"{current_count} 명")
