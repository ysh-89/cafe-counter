import math
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

# 1. 페이지 기본 설정
st.set_page_config(page_title="위치 기반 카페 인원 측정기", layout="centered")

st.title("☕ 위치 기반 카페 실시간 인원 측정기")
st.write("카메라 없이 사용자의 현재 위치(GPS)를 기반으로 카페 반경 100m 이내 접속자를 자동으로 판별합니다.")

# 2. 대권거리(Haversine) 계산 함수 (두 위도/경도 사이의 미터 거리 계산)
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

# 3. 데이터 로드 (store.csv)
@st.cache_data
def load_store_data():
    df = pd.read_csv("store.csv")
    # '카페' 종목만 필터링 (필요 시 수정 가능)
    cafe_df = df[df["상권업종소분류명"] == "카페"].reset_index(drop=True)
    return cafe_df

df_cafe = load_store_data()

# Session State 초기화 (인원수 누적 관리용)
if "cafe_counts" not in st.session_state:
    st.session_state.cafe_counts = {}

# 4. 사용자 위치 수집
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

# 5. 카페 선택 및 측정
st.subheader("🏬 2. 카페 선택 및 인원 측정")

selected_cafe_name = st.selectbox(
    "조회할 카페를 선택하세요:",
    df_cafe["상호명"].unique()
)

cafe_info = df_cafe[df_cafe["상호명"] == selected_cafe_name].iloc[0]
cafe_lat = cafe_info["위도"]
cafe_lon = cafe_info["경도"]

st.write(f"**선택된 카페 주소**: {cafe_info['시도명']} {cafe_info['시군구명']}")

# 버튼을 누르면 거리 계산 및 카운팅 처리
if st.button("🔄 인원수 체크 및 자동 카운팅"):
    if user_lat is None or user_lon is None:
        st.error("⚠️ 사용자 위치 정보(GPS)를 불러오지 못했습니다. 위치 권한을 허용했는지 확인하세요.")
    else:
        # 거리 계산 (미터)
        dist = calculate_distance(user_lat, user_lon, cafe_lat, cafe_lon)
        
        st.write(f"📏 현재 위치에서 카페까지의 거리: **{dist:.1f} m**")
        
        # 기본 인원수 초기화
        if selected_cafe_name not in st.session_state.cafe_counts:
            st.session_state.cafe_counts[selected_cafe_name] = 0

        # 반경 100m 판별
        if dist <= 100.0:
            st.session_state.cafe_counts[selected_cafe_name] += 1
            st.balloons()
            st.success(f"✅ 카페 반경 100m 이내에 있습니다! (자동 인원수 +1 반영)")
        else:
            st.warning(f"❌ 카페 반경 100m 밖(약 {dist:.0f}m 떨어짐)에 위치해 있어 인원수 측정에서 제외됩니다.")

# 현재 측정된 인원수 출력
current_count = st.session_state.cafe_counts.get(selected_cafe_name, 0)
st.metric(label=f"[{selected_cafe_name}] 현재 집계된 인원수", value=f"{current_count} 명")

st.markdown("---")

# 6. 지도 시각화 (Folium Map)
st.subheader("🗺️ 3. 카페 위치 및 반경 100m 지도 확인")

# 지도 중심 설정 (선택된 카페 위치)
m = folium.Map(location=[cafe_lat, cafe_lon], zoom_start=17)

# 카페 위치 마커 (빨간색)
folium.Marker(
    location=[cafe_lat, cafe_lon],
    popup=selected_cafe_name,
    tooltip=selected_cafe_name,
    icon=folium.Icon(color="red", icon="coffee", prefix="fa")
).add_to(m)

# 카페 반경 100m 원(Circle) 표시
folium.Circle(
    location=[cafe_lat, cafe_lon],
    radius=100,  # 100미터
    color="blue",
    fill=True,
    fill_opacity=0.2,
    popup="반경 100m 측정 구역"
).add_to(m)

# 사용자 위치 마커 (파란색, 위치 정보 있을 때)
if user_lat and user_lon:
    folium.Marker(
        location=[user_lat, user_lon],
        popup="내 위치",
        tooltip="현재 사용자 위치",
        icon=folium.Icon(color="blue", icon="user", prefix="fa")
    ).add_to(m)

# Streamlit 내에 지도 렌더링
st_data = st_folium(m, width=700, height=450)
