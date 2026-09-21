import math
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

# 1. 페이지 기본 설정
st.set_page_config(page_title="위치 기반 카페 인원 측정기", layout="centered")

st.title("☕ 위치 기반 카페 실시간 인원 측정기")
st.write("지도를 클릭하거나 카페를 선택하여 반경 100m 이내 접속자를 자동으로 판별합니다.")

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

# 3. 데이터 로드 (store.csv)
@st.cache_data
def load_store_data():
    df = pd.read_csv("store.csv")
    cafe_df = df[df["상권업종소분류명"] == "카페"].reset_index(drop=True)
    return cafe_df

df_cafe = load_store_data()

# Session State 초기화 (인원수 및 상태 유지용)
if "cafe_counts" not in st.session_state:
    st.session_state.cafe_counts = {}
if "last_message" not in st.session_state:
    st.session_state.last_message = "아직 측정 이력이 없습니다."
if "last_status" not in st.session_state:
    st.session_state.last_status = "info" # info, success, warning
if "selected_cafe" not in st.session_state:
    st.session_state.selected_cafe = df_cafe["상호명"].iloc[0]

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

# 5. 지도 시각화 및 마커 클릭 선택 기능
st.subheader("🗺️ 2. 지도에서 카페 선택하기")
st.write("아래 지도에서 원하는 **카페 마커(빨간색)**를 클릭하거나 드롭다운을 통해 선택하세요.")

# 드롭다운과 선택 동기화
selected_cafe_name = st.selectbox(
    "조회할 카페 선택:",
    df_cafe["상호명"].unique(),
    index=list(df_cafe["상호명"].unique()).index(st.session_state.selected_cafe)
if st.session_state.selected_cafe in df_cafe["상호명"].unique() else 0
)

# 드롭다운에서 변경한 경우 상태 업데이트
if selected_cafe_name != st.session_state.selected_cafe:
    st.session_state.selected_cafe = selected_cafe_name

# 선택된 카페 정보 가져오기
cafe_info = df_cafe[df_cafe["상호명"] == st.session_state.selected_cafe].iloc[0]
cafe_lat = cafe_info["위도"]
cafe_lon = cafe_info["경도"]

# Folium 지도 생성 (모든 카페 표시 + 선택된 카페 강조)
m = folium.Map(location=[cafe_lat, cafe_lon], zoom_start=15)

# 전체 카페 마커 추가 (클릭 가능한 대상들)
for idx, row in df_cafe.iterrows():
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

# 지도 렌더링 및 사용자의 지도 클릭 이벤트 감지
map_data = st_folium(m, width=700, height=450)

# 사용자가 지도 위의 다른 마커나 요소를 클릭했을 때 처리
if map_data and map_data.get("last_clicked"):
    clicked_lat = map_data["last_clicked"]["lat"]
    clicked_lon = map_data["last_clicked"]["lng"]
    
    # 클릭한 좌표와 가장 가까운 카페 찾기
    df_cafe["temp_dist"] = df_cafe.apply(lambda r: calculate_distance(clicked_lat, clicked_lon, r["위도"], r["경도"]), axis=1)
    nearest_cafe = df_cafe.loc[df_cafe["temp_dist"].idxmin()]
    
    # 만약 클릭 지점이 카페와 50m 이내라면 선택 변경 후 자동 새로고침
    if nearest_cafe["temp_dist"] < 50 and nearest_cafe["상호명"] != st.session_state.selected_cafe:
        st.session_state.selected_cafe = nearest_cafe["상호명"]
        st.rerun()

st.markdown("---")

# 6. 인원 측정 및 결과 메시지 유지 출력
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

# 새로고침되거나 다른 조작을 해도 결과 메시지가 화면에 남아있도록 출력
if st.session_state.last_status == "success":
    st.success(st.session_state.last_message)
elif st.session_state.last_status == "warning":
    st.warning(st.session_state.last_message)
elif st.session_state.last_status == "error":
    st.error(st.session_state.last_message)
else:
    st.info(st.session_state.last_message)

# 현재 집계된 인원수 표시
current_count = st.session_state.cafe_counts.get(st.session_state.selected_cafe, 0)
st.metric(label=f"[{st.session_state.selected_cafe}] 현재 집계된 인원수", value=f"{current_count} 명")
