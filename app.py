import streamlit as st
import requests
from collections import Counter

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="나와 어울리는 영화는?",
    page_icon="🎬",
    layout="centered",
)

# -----------------------------
# Sidebar: TMDB API Key
# -----------------------------
st.sidebar.header("TMDB 설정")
api_key = st.sidebar.text_input("TMDB API Key", type="password", help="TMDB에서 발급받은 API Key를 입력하세요.")

# -----------------------------
# Title & intro
# -----------------------------
st.title("🎬 나와 어울리는 영화는?")
st.write("5개의 질문에 답하면, 당신의 취향에 가장 잘 맞는 장르를 골라 TMDB에서 인기 영화 5편을 추천해드려요.")
st.divider()

# -----------------------------
# Questions
# 각 질문의 4개 선택지는 항상 같은 장르 순서:
# 1) 로맨스/드라마, 2) 액션/어드벤처, 3) SF/판타지, 4) 코미디
# -----------------------------
questions = [
    {
        "q": "Q1. 시험이 끝난 날, 가장 하고 싶은 일은?",
        "options": [
            "조용한 카페에 가서 음악 들으며 하루를 정리한다",   # 로맨스/드라마
            "친구들이랑 즉흥적으로 여행이나 액티비티를 간다",    # 액션/어드벤처
            "집에서 몰입감 있는 세계관의 작품을 정주행한다",      # SF/판타지
            "아무 생각 없이 웃긴 영상이나 예능을 본다",          # 코미디
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

# 선택지 인덱스(0~3)를 큰 장르 카테고리로 매핑
category_by_option_index = {
    0: "romance_drama",
    1: "action_adventure",
    2: "sf_fantasy",
    3: "comedy",
}

# TMDB 장르 ID
TMDB_GENRE_IDS = {
    "action": 28,
    "comedy": 35,
    "drama": 18,
    "scifi": 878,
    "romance": 10749,
    "fantasy": 14,
}

# 결과 표시용 라벨
DISPLAY_LABEL = {
    "action": "액션",
    "comedy": "코미디",
    "drama": "드라마",
    "scifi": "SF",
    "romance": "로맨스",
    "fantasy": "판타지",
}

# -----------------------------
# Helpers
# -----------------------------
def decide_final_genre(selected_texts, category_counts):
    """
    큰 카테고리(로맨스/드라마, 액션, SF/판타지, 코미디)를 먼저 고르고,
    필요 시(로맨스/드라마, SF/판타지) 세부 장르를 휴리스틱으로 결정.
    """
    top_category = category_counts.most_common(1)[0][0]

    if top_category == "action_adventure":
        return "action"

    if top_category == "comedy":
        return "comedy"

    if top_category == "romance_drama":
        # 로맨스 vs 드라마 휴리스틱:
        # - 관계/감정선/감정이입/로맨스 뉘앙스 강하면 로맨스
        # - 여운/성장/현실적인 고민 뉘앙스 강하면 드라마
        romance_keywords = ["관계", "감정선", "감정이입", "로맨스", "설렘"]
        drama_keywords = ["여운", "성장", "현실", "고민", "정리", "천천히"]

        romance_score = sum(any(k in t for k in romance_keywords) for t in selected_texts)
        drama_score = sum(any(k in t for k in drama_keywords) for t in selected_texts)

        # 많이 선택했으면 로맨스 쪽으로 살짝 가중치 (대학생 취향에서 “감정선” 강조 시)
        if romance_score > drama_score:
            return "romance"
        return "drama"

    if top_category == "sf_fantasy":
        # SF vs 판타지 휴리스틱:
        # - 설정/참신/미래/과학 뉘앙스면 SF
        # - 능력/운명/마법/특별함 뉘앙스면 판타지
        scifi_keywords = ["설정", "참신", "미래", "과학", "우주", "AI", "시간"]
        fantasy_keywords = ["능력", "운명", "마법", "전설", "왕국", "드래곤", "특별한"]

        scifi_score = sum(any(k in t for k in scifi_keywords) for t in selected_texts)
        fantasy_score = sum(any(k in t for k in fantasy_keywords) for t in selected_texts)

        if fantasy_score > scifi_score:
            return "fantasy"
        return "scifi"

    # fallback
    return "drama"


def fetch_popular_movies_by_genre(api_key, genre_id, n=5):
    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": api_key,
        "with_genres": genre_id,
        "language": "ko-KR",
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "page": 1,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return (data.get("results") or [])[:n]


def build_reason(genre_key, selected_texts, category_counts):
    """
    추천 이유를 아주 짧게 구성: 장르 선호 근거 + 사용자가 고른 답변에서 대표 포인트 1~2개
    """
    label = DISPLAY_LABEL.get(genre_key, genre_key)
    top_cat, top_cnt = category_counts.most_common(1)[0]
    cat_kor = {
        "romance_drama": "로맨스/드라마",
        "action_adventure": "액션/어드벤처",
        "sf_fantasy": "SF/판타지",
        "comedy": "코미디",
    }.get(top_cat, top_cat)

    # 답변에서 키워드성 문장 1~2개 추려서 “취향 포인트”로 활용
    # 너무 길면 잘라서 표시
    picks = []
    for t in selected_texts:
        if len(picks) >= 2:
            break
        if len(t) > 28:
            picks.append(t[:28] + "…")
        else:
            picks.append(t)

    if picks:
        return f"당신의 답변에서 **{cat_kor} 성향**이 가장 강했어요({top_cnt}/5). - 그래서 **{label}** 장르로 추천했어요. - 취향 포인트: “{picks[0]}”" + (f", “{picks[1]}”" if len(picks) > 1 else "")
    return f"당신의 답변에서 **{cat_kor} 성향**이 가장 강했어요({top_cnt}/5). - 그래서 **{label}** 장르로 추천했어요."


def poster_url(poster_path):
    if not poster_path:
        return None
    return "https://image.tmdb.org/t/p/w500" + poster_path


# -----------------------------
# UI: radios
# -----------------------------
answers = []
selected_texts = []
selected_option_indices = []

for i, item in enumerate(questions, start=1):
    st.subheader(item["q"])
    choice = st.radio(
        label="",
        options=item["options"],
        key=f"q{i}",
    )
    answers.append(choice)
    selected_texts.append(choice)
    selected_option_indices.append(item["options"].index(choice))
    st.write("")

st.divider()

# -----------------------------
# Submit: analyze + TMDB call
# -----------------------------
if st.button("결과 보기", type="primary"):
    if not api_key.strip():
        st.warning("사이드바에 TMDB API Key를 입력해 주세요.")
        st.stop()

    # 1) 사용자 답변 -> 큰 장르 카테고리 카운트
    categories = [category_by_option_index[idx] for idx in selected_option_indices]
    category_counts = Counter(categories)

    # 2) 세부 장르 결정 (action/comedy/drama/romance/scifi/fantasy)
    final_genre_key = decide_final_genre(selected_texts, category_counts)
    final_genre_id = TMDB_GENRE_IDS[final_genre_key]

    # 3) TMDB에서 인기 영화 5개 가져오기
    with st.spinner("분석 중..."):
        try:
            movies = fetch_popular_movies_by_genre(api_key, final_genre_id, n=5)
        except requests.HTTPError as e:
            st.error("TMDB 요청에 실패했어요. - API Key가 유효한지 확인해 주세요.")
            st.caption(f"HTTP Error: {e}")
            st.stop()
        except requests.RequestException as e:
            st.error("네트워크 문제로 TMDB 요청에 실패했어요. - 잠시 후 다시 시도해 주세요.")
            st.caption(f"Request Error: {e}")
            st.stop()

    # 결과 헤더
    st.success(f"당신과 어울리는 장르: **{DISPLAY_LABEL.get(final_genre_key, final_genre_key)}**")
    st.caption(build_reason(final_genre_key, selected_texts, category_counts))
    st.write("")

    # 4) 포스터, 제목, 평점, 줄거리 + 5) 추천 이유
    if not movies:
        st.info("해당 장르에서 가져올 영화가 없어요. - 다른 답변 조합으로 다시 시도해 주세요.")
        st.stop()

    for m in movies:
        title = m.get("title") or m.get("name") or "제목 없음"
        rating = m.get("vote_average")
        overview = (m.get("overview") or "").strip()
        img = poster_url(m.get("poster_path"))

        # 카드 형태로 표시
        with st.container(border=True):
            cols = st.columns([1, 2])

            with cols[0]:
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.caption("포스터 없음")

            with cols[1]:
                st.markdown(f"### {title}")
                if rating is not None:
                    st.write(f"평점: **{rating:.1f} / 10**")
                else:
                    st.write("평점: 정보 없음")

                st.write(overview if overview else "줄거리: 정보 없음")

                # “이 영화를 추천하는 이유” (짧게)
                # 장르 기반 + 사용자가 중요시한 요소를 한 줄로 연결
                reason = build_reason(final_genre_key, selected_texts, category_counts)
                st.markdown(f"**이 영화를 추천하는 이유** - {reason}")
