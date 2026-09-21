import streamlit as st
from streamlit_js_eval import get_geolocation
import pandas as pd
import numpy as np
import uuid
import folium
from streamlit_folium import st_folium
import os

# 페이지 기본 설정
st.set_page_config(
    page_title="제주 카페 실시간 인원 카운터",
    page_icon="☕",
    layout="wide"
)

ALLOWED_RADIUS_METERS = 50  # 인원 감지 반경 (50m)

# 고속 거리를 미터 단위로 산출하는 함수 (numpy 벡터화)
def fast_distance_meters(lat1, lon1, lat2, lon2):
    lat_diff = (lat2 - lat1) * 111000
    lon_diff = (lon2 - lon1) * 88000
    return np.sqrt(lat_diff**2 + lon_diff**2)

# 1. 서버 전역 저장소 및 데이터 로드
@st.cache_resource
def get_global_store():
    admin_email = st.secrets.get("ADMIN_EMAIL", "seokhwanyun892@gmail.com")
    
    file_path = "store_2.csv" if os.path.exists("store_2.csv") else "store.csv"
    try:
        df = pd.read_csv(file_path)
    except Exception:
        df = pd.DataFrame(columns=['상호명', '상권업종소분류명', '시도명', '시군구명', '위도', '경도'])
    
    return {
        "base_location": None,
        "base_address": "",
        "cafe_active_users": {},     # 카페별 실시간 상주 사용자 식별자 저장소
        "admin_email": admin_email,
        "store_df": df
    }

global_store = get_global_store()

# 2. 고유 사용자 식별 ID 고정
if "uid" in st.query_params:
    user_id = st.query_params["uid"]
else:
    user_id = str(uuid.uuid4())[:8]
    st.query_params["uid"] = user_id

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# 3. 사이드바 필터 설정
st.sidebar.header("⚙️ 검색 및 표시 필터")

region_list = ["전체", "제주시", "서귀포시"]
selected_region = st.sidebar.selectbox("📍 지역 선택", options=region_list)

st.sidebar.subheader("🏪 카테고리 필터")
all_categories = list(global_store["store_df"]['상권업종소분류명'].unique()) if not global_store["store_df"].empty else ["카페", "편의점"]

selected_categories = []
category_labels = {"카페": "☕ 카페", "편의점": "🏪 편의점"}

for cat in all_categories:
    label = category_labels.get(cat, f"📍 {cat}")
    default_val = True if cat == "카페" else False
    if st.sidebar.checkbox(label, value=default_val, key=f"cat_chk_{cat}"):
        selected_categories.append(cat)

st.sidebar.divider()
dist_filter = st.sidebar.select_slider(
    "📏 내 위치 기준 검색 범위",
    options=["전체 보기", "1km 이내", "3km 이내", "5km 이내"],
    value="전체 보기"
)

# 4. 데이터 필터링
df_data = global_store["store_df"].copy()

if selected_region != "전체":
    df_data = df_data[df_data['시군구명'] == selected_region]

if selected_categories:
    df_filtered = df_data[df_data['상권업종소분류명'].isin(selected_categories)].reset_index(drop=True)
else:
    df_filtered = pd.DataFrame(columns=df_data.columns)

# 5. 메인 UI 화면
tab_user, tab_admin = st.tabs(["📱 실시간 카페 인원 조회", "🔐 관리자 설정"])

location = get_geolocation()

with tab_user:
    st.title("☕ 제주 카페 실시간 인원 카운터")
    st.caption("위치 권한을 수락하면 50m 반경 내 상주 인원이 자동으로 집계됩니다.")

    if location is None:
        st.info("🌐 브라우저의 위치 권한 요청을 승인해 주세요...")
    elif not isinstance(location, dict) or "coords" not in location or location["coords"] is None:
        st.warning("⚠️ 위치 정보를 가져올 수 없습니다. 브라우저 GPS 권한을 확인해 주세요.")
    else:
        user_lat = location['coords']['latitude']
        user_lon = location['coords']['longitude']

        # 내 위치 기준 내림차순 정렬 및 범위 제한
        if not df_filtered.empty:
            df_filtered['dist_m'] = fast_distance_meters(user_lat, user_lon, df_filtered['위도'].values, df_filtered['경도'].values)
            if dist_filter != "전체 보기":
                max_d = {"1km 이내": 1000, "3km 이내": 3000, "5km 이내": 5000}[dist_filter]
                df_filtered = df_filtered[df_filtered['dist_m'] <= max_d].reset_index(drop=True)
            df_filtered = df_filtered.sort_values(by='dist_m').reset_index(drop=True)

        st.subheader("📍 카페 선택")
        place_options = ["선택 안함 (지도의 마커 클릭 가능)"]
        if not df_filtered.empty:
            place_options += [
                f"[{row['상권업종소분류명']}] {row['상호명']} ({row['시군구명']})" for _, row in df_filtered.iterrows()
            ]

        current_addr = global_store["base_address"]
        default_index = 0
        if current_addr and not df_filtered.empty:
            for idx, row in df_filtered.iterrows():
                if str(row['상호명']) == current_addr:
                    default_index = idx + 1
                    break

        selected_option = st.selectbox("카페 검색 및 목록 선택", options=place_options, index=default_index)

        if selected_option != "선택 안함 (지도의 마커 클릭 가능)":
            selected_idx = place_options.index(selected_option) - 1
            selected_row = df_filtered.iloc[selected_idx]
            global_store["base_location"] = (float(selected_row['위도']), float(selected_row['경도']))
            global_store["base_address"] = str(selected_row['상호명'])

        # 지도 중심점 설정
        if global_store["base_location"]:
            map_center = global_store["base_location"]
            map_zoom = 15
        else:
            map_center = [user_lat, user_lon]
            map_zoom = 13

        m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="OpenStreetMap")

        display_df = df_filtered.head(200) if not df_filtered.empty else pd.DataFrame()

        if not display_df.empty:
            for _, row in display_df.iterrows():
                category = str(row['상권업종소분류명'])
                name = str(row['상호명'])
                is_selected = (name == global_store["base_address"])

                if is_selected:
                    folium.CircleMarker(
                        location=[row['위도'], row['경도']],
                        radius=14,
                        color="#C0392B",
                        fill=True,
                        fill_color="#E74C3C",
                        fill_opacity=0.9,
                        popup=f"⭐ [선택됨] {name}",
                        tooltip=f"⭐ [선택됨] {name}"
                    ).add_to(m)
                elif '카페' in category:
                    folium.CircleMarker(
                        location=[row['위도'], row['경도']],
                        radius=10,
                        color="#D35400",
                        fill=True,
                        fill_color="#E67E22",
                        fill_opacity=0.85,
                        popup=f"☕ {name}",
                        tooltip=f"☕ {name}"
                    ).add_to(m)
                else:
                    folium.CircleMarker(
                        location=[row['위도'], row['경도']],
                        radius=8,
                        color="#1B4F72",
                        fill=True,
                        fill_color="#2980B9",
                        fill_opacity=0.8,
                        popup=f"🏪 {name}",
                        tooltip=f"🏪 {name}"
                    ).add_to(m)

        # 선택 카페 50m 반경 원 표시
        if global_store["base_location"]:
            base_lat, base_lon = global_store["base_location"]
            folium.Circle(
                location=[base_lat, base_lon],
                radius=ALLOWED_RADIUS_METERS,
                color="#E74C3C",
                weight=3,
                fill=True,
                fill_color="#E74C3C",
                fill_opacity=0.35,
                popup=f"{global_store['base_address']} (50m 감지 범위)"
            ).add_to(m)

        # 사용자 내 위치 마커
        folium.CircleMarker(
            [user_lat, user_lon],
            radius=12,
            color="#5B2C6F",
            fill=True,
            fill_color="#8E44AD",
            fill_opacity=0.95,
            popup="📱 내 위치",
            tooltip="📱 내 위치"
        ).add_to(m)

        st.subheader(f"🗺️ 실시간 제주 카페 지도 ({selected_region})")
        
        cat_key_str = "_".join(selected_categories) if selected_categories else "none"
        base_addr_str = global_store["base_address"] or "none"
        dynamic_map_key = f"map_{selected_region}_{cat_key_str}_{dist_filter}_{base_addr_str}"

        map_data = st_folium(m, width=850, height=480, key=dynamic_map_key)

        # 지도 마커 선택 수신
        clicked_obj = None
        if map_data:
            clicked_obj = map_data.get("last_marker_clicked") or map_data.get("last_object_clicked")

        if clicked_obj and "lat" in clicked_obj and "lng" in clicked_obj:
            clicked_lat = clicked_obj["lat"]
            clicked_lon = clicked_obj["lng"]

            if not display_df.empty:
                display_df['dist_calc'] = (display_df['위도'] - clicked_lat)**2 + (display_df['경도'] - clicked_lon)**2
                closest_place = display_df.loc[display_df['dist_calc'].idxmin()]
                
                if closest_place['dist_calc'] < 0.0008:
                    new_addr = str(closest_place['상호명'])
                    new_loc = (float(closest_place['위도']), float(closest_place['경도']))
                    if global_store["base_address"] != new_addr:
                        global_store["base_location"] = new_loc
                        global_store["base_address"] = new_addr
                        st.rerun()

        st.divider()

        # 인원수 조회 카드
        if global_store["base_location"] is None or not global_store["base_address"]:
            st.warning("📍 현재 선택된 카페가 없습니다. 지도 위의 마커나 목록에서 카페를 선택해 주세요.")
        else:
            target_place = global_store["base_address"]
            if target_place not in global_store["cafe_active_users"]:
                global_store["cafe_active_users"][target_place] = set()

            active_set = global_store["cafe_active_users"][target_place]
            b_lat, b_lon = global_store["base_location"]
            
            distance = fast_distance_meters(user_lat, user_lon, b_lat, b_lon)

            # 50m 반경 인원 세기
            if distance <= ALLOWED_RADIUS_METERS:
                active_set.add(user_id)
                status_msg = f"✅ 현재 반경 {ALLOWED_RADIUS_METERS}m 이내에 있어 **[실시간 방문자 카운트 포함]** 상태입니다."
                status_box = st.success
            else:
                active_set.discard(user_id)
                status_msg = f"❌ 현재 카페 반경 {ALLOWED_RADIUS_METERS}m 밖에 있습니다."
                status_box = st.info

            st.markdown(f"### ☕ 선택된 카페: **{target_place}**")
            st.metric(label=f"📊 '{target_place}' (50m 반경) 현재 실시간 상주 인원수", value=f"{len(active_set)} 명")
            st.write(f"📍 내 위치와 카페와의 거리: **약 {int(distance)}m**")
            status_box(status_msg)

            st.divider()
            if st.button("🔄 실시간 인원수 새로고침", use_container_width=True, type="primary"):
                st.rerun()

# 6. 관리자 설정
with tab_admin:
    st.header("🔐 관리자 페이지")

    if not st.session_state.is_admin:
        admin_email_input = st.text_input("관리자 이메일 로그인", placeholder="seokhwanyun892@gmail.com")
        if st.button("로그인", use_container_width=True, type="primary"):
            if admin_email_input.strip().lower() == global_store["admin_email"].lower():
                st.session_state.is_admin = True
                st.success("인증 성공!")
                st.rerun()
            else:
                st.error("이메일 불일치")
    else:
        st.success("🔓 관리자 인증됨")
        if st.button("⚠️ 실시간 카운팅 인원 전체 초기화", use_container_width=True):
            global_store["cafe_active_users"] = {}
            st.warning("모든 카페의 실시간 인원 카운트가 초기화되었습니다.")
            st.rerun()
