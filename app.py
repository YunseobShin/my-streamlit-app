import streamlit as st

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="나와 어울리는 영화는?",
    page_icon="🎬",
    layout="centered",
)

# -----------------------------
# Title & intro
# -----------------------------
st.title("🎬 나와 어울리는 영화는?")
st.write("5개의 질문에 답하면, 당신의 취향에 가장 잘 맞는 영화 장르를 찾아드려요. (지금은 결과 분석 API 연동 전 단계입니다)")

st.divider()

# -----------------------------
# Questions (from previous step)
# -----------------------------
questions = [
    {
        "q": "Q1. 시험이 끝난 날, 가장 하고 싶은 일은?",
        "options": [
            "조용한 카페에 가서 음악 들으며 하루를 정리한다",
            "친구들이랑 즉흥적으로 여행이나 액티비티를 간다",
            "집에서 몰입감 있는 세계관의 작품을 정주행한다",
            "아무 생각 없이 웃긴 영상이나 예능을 본다",
        ],
    },
    {
        "q": "Q2. 영화 볼 때 가장 중요하게 보는 요소는?",
        "options": [
            "인물 간의 감정선과 관계 변화",
            "긴장감 넘치는 전개와 시원한 장면",
            "설정의 참신함과 세계관의 완성도",
            "대사나 상황에서 나오는 웃음 포인트",
        ],
    },
    {
        "q": "Q3. 친구가 영화를 추천해달라고 하면?",
        "options": [
            "여운이 오래 남는 작품을 추천한다",
            "같이 보면서 감탄할 수 있는 영화를 추천한다",
            "“이건 설정이 미쳤다” 싶은 영화를 추천한다",
            "같이 웃으면서 볼 수 있는 영화를 추천한다",
        ],
    },
    {
        "q": "Q4. 당신이 더 끌리는 영화 속 주인공은?",
        "options": [
            "현실적인 고민을 안고 성장하는 인물",
            "위험한 상황에서도 몸부터 움직이는 인물",
            "특별한 능력이나 운명을 지닌 인물",
            "실수 많고 인간적인 매력의 인물",
        ],
    },
    {
        "q": "Q5. 주말에 혼자 영화 한 편을 본다면?",
        "options": [
            "감정이입하며 천천히 몰입할 수 있는 영화",
            "스트레스가 확 풀리는 영화",
            "현실을 잠시 잊게 해주는 영화",
            "가볍게 웃고 끝낼 수 있는 영화",
        ],
    },
]

# -----------------------------
# UI: radios
# -----------------------------
answers = []
for i, item in enumerate(questions, start=1):
    st.subheader(item["q"])
    choice = st.radio(
        label="",
        options=item["options"],
        key=f"q{i}",
    )
    answers.append(choice)
    st.write("")  # spacing

st.divider()

# -----------------------------
# Submit button
# -----------------------------
if st.button("결과 보기", type="primary"):
    # (Next session) We'll connect to an API and analyze.
    # For now: only show "analyzing..."
    st.info("분석 중...")  # placeholder
