import math
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

# 1. 페이지 기본 설정
st.set_page_config(page_title="위치 기반 카페 인원 측정기", layout="centered")

st.title("☕ 위치 기반 카페 실시간 인원 측정기")
st.write("지도 리소스 최적화를 위해 주변 최대 150개의 카페 마커만 표시합니다.")

# 2. 대권거리(Haversine) 계산 함수
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

# 3. 데이터 로드 및 편의점 제외 처리 (캐싱 적용)
@st.cache_data
def load_cafe_data():
    df = pd.read_csv("store.csv")
    if "상권업종소분류명" in df.columns:
        cafe_df = df[df["상권업종소분류명"] == "카페"].reset_index(drop=True)
    else:
        cafe_df = df.copy()
    return cafe_df

df_cafe = load_cafe_data()

# Session State 초기화
if "cafe_counts" not in st.session_state:
    st.session_state.cafe_counts = {}
if "last_message" not in st.session_state:
    st.session_state.last_message = "아직 측정 이력이 없습니다."
if "last_status" not in st.session_state:
    st.session_state.last_status = "info"
if "selected_cafe" not in st.session_state:
    st.session_state.selected_cafe = df_cafe["상호명"].iloc[0] if len(df_cafe) > 0 else ""

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

# 5. 카페 선택 UI
st.subheader("🗺️ 2. 카페 선택하기")

selected_cafe_name = st.selectbox(
    "조회할 카페 선택:",
    df_cafe["상호명"].unique(),
    index=list(df_cafe["상호명"].unique()).index(st.session_state.selected_cafe)
    if st.session_state.selected_cafe in df_cafe["상호명"].unique() else 0
)

if selected_cafe_name != st.session_state.selected_cafe:
    st.session_state.selected_cafe = selected_cafe_name

cafe_info = df_cafe[df_cafe["상호명"] == st.session_state.selected_cafe].iloc[0]
cafe_lat = cafe_info["위도"]
cafe_lon = cafe_info["경도"]

# [리소스 최적화] 선택된 카페 기준 거리 계산 후 가까운 순으로 정렬하여 상위 150개만 추출
df_cafe["dist_from_selected"] = df_cafe.apply(
    lambda r: calculate_distance(cafe_lat, cafe_lon, r["위도"], r["경도"]), axis=1
)
nearby_cafes = df_cafe.sort_values("dist_from_selected").head(150)

# Folium 지도 생성 (prefer_canvas로 렌더링 부하 감소)
m = folium.Map(location=[cafe_lat, cafe_lon], zoom_start=15, prefer_canvas=True)

# 상위 150개 카페 마커만 지도에 추가
for idx, row in nearby_cafes.iterrows():
    is_target = (row["상호명"] == st.session_state.selected_cafe)
    icon_color = "red" if is_target else "gray"
    icon_shape = "star" if is_target else "coffee"
    
    folium.Marker(
        location=[row["위도"], row["경도"]],
        popup=row["상호명"],
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
    popup=f"{st.session_state.selected_cafe} 반경 100m"
).add_to(m)

# 사용자 위치 마커 표시
if user_lat and user_lon:
    folium.Marker(
        location=[user_lat, user_lon],
        popup="내 위치",
        tooltip="현재 사용자 위치",
        icon=folium.Icon(color="blue", icon="user", prefix="fa")
    ).add_to(m)

# 지도 렌더링
st_data = st_folium(m, width=700, height=400)

st.markdown("---")

# 6. 인원 측정 및 결과 메시지 유지
st.subheader("🏬 3. 인원 측정 및 결과")
st.write(f"현재 선택된 카페: **{st.session_state.selected_cafe}** ({cafe_info['시도명']} {cafe_info['시군구명']})")

if st.button("🔄 인원수 체크 및 자동 카운팅"):
    if user_lat is None or user_lon is None:
        st.session_state.last_message = "⚠️ 사용자 위치 정보(GPS)를 불러오지 못했습니다. 위치 권한을 허용하세요."
        st.session_state.last_status = "error"
    else:
        dist = calculate_distance(user_lat, user_lon, cafe_lat, cafe_lon)
        
        if st.session_state.selected_cafe not in st.session_state.cafe_counts:
            st.session_state.cafe_counts[st.session_state.selected_cafe] = 0

        # 반경 100m 판별
        if dist <= 100.0:
            st.session_state.cafe_counts[st.session_state.selected_cafe] += 1
            st.session_state.last_message = f"✅ 성공! [{st.session_state.selected_cafe}] 반경 100m 이내에 있습니다. (거리: {dist:.1f}m) -> 인원수 +1 반영 완료!"
            st.session_state.last_status = "success"
        else:
            st.session_state.last_message = f"❌ 제외됨! [{st.session_state.selected_cafe}] 반경 100m 밖(약 {dist:.1f}m 거리)에 있어 인원수 측정에서 제외되었습니다."
            st.session_state.last_status = "warning"

# 결과 출력 유지
if st.session_state.last_status == "success":
    st.success(st.session_state.last_message)
elif st.session_state.last_status == "warning":
    st.warning(st.session_state.last_message)
elif st.session_state.last_status == "error":
    st.error(st.session_state.last_message)
else:
    st.info(st.session_state.last_message)

current_count = st.session_state.cafe_counts.get(st.session_state.selected_cafe, 0)
st.metric(label=f"[{st.session_state.selected_cafe}] 현재 집계된 인원수", value=f"{current_count} 명")
