import streamlit as st
import numpy as np
from PIL import Image
from ultralytics import YOLO
from streamlit_js_eval import get_geolocation

# 1. 페이지 기본 설정
st.set_page_config(page_title="위치 기반 카페 인원 측정기", layout="centered")

st.title("☕ 위치 기반 카페 인원 측정 앱")
st.write("위치 권한을 허용하고, 버튼을 눌러 현재 카페의 인원수를 측정하세요.")

# 2. YOLOv8 객체 탐지 모델 로드
@st.cache_resource
def load_model():
    return YOLO("yolov8n.pt")

model = load_model()

# 3. 위치 권한 및 사용자 좌표 수집
st.subheader("1. 위치 권한 확인")
loc = get_geolocation()

if loc:
    lat = loc['coords']['latitude']
    lon = loc['coords']['longitude']
    st.success(f"📍 위치 확인 완료! (위도: {lat:.4f}, 경도: {lon:.4f})")
else:
    st.info("👆 브라우저의 위치 권한을 허용해 주세요.")

st.markdown("---")

# 4. 카페 촬영/업로드 및 버튼 기반 측정
st.subheader("2. 카페 인원 측정")

# 입력을 위한 카메라 또는 이미지 파일 수집
img_file = st.camera_input("카페 내부를 촬영하세요")

if img_file is None:
    uploaded_file = st.file_uploader("또는 카페 이미지를 업로드하세요", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        img_file = uploaded_file

# 5. [측정 시작] 버튼을 누를 때만 계산 진행
if st.button("🔍 인원수 측정하기"):
    if not loc:
        st.warning("⚠️ 위치 정보가 확인되지 않았습니다. 위치 권한을 허용했는지 확인해 주세요.")
    elif img_file is None:
        st.warning("⚠️ 카메라 입력이나 이미지를 먼저 등록해 주세요.")
    else:
        with st.spinner("이미지를 분석하여 인원수를 세는 중입니다..."):
            image = Image.open(img_file).convert("RGB")
            img_array = np.array(image)

            # YOLO 모델로 사람(class 0) 탐지
            results = model(img_array)

            person_count = 0
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    if int(box.cls[0]) == 0:  # 사람(person)
                        person_count += 1
                
                # 결과 박스 시각화 (RGB 변환)
                res_plotted = result.plot()
                annotated_frame = Image.fromarray(res_plotted[..., ::-1])

            st.balloons()
            st.success("🎉 측정 완료!")
            st.metric(label="현재 측정된 카페 인원수", value=f"{person_count} 명")
            st.image(annotated_frame, caption="AI 인원 감지 결과", use_container_width=True)
