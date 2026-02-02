import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import requests
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
# Sidebar: Auth & Options
# -----------------------------
st.sidebar.header("TMDB 설정")

api_key_v3 = st.sidebar.text_input(
    "TMDB v3 API Key (선택)",
    type="password",
    help="기존 v3 api_key. 아래 v4 Read Access Token을 쓰면 비워도 됩니다.",
)

read_access_token_v4 = st.sidebar.text_input(
    "TMDB v4 API Read Access Token (Bearer) (선택)",
    type="password",
    help="TMDB 계정의 API 설정에서 확인 가능한 Read Access Token. 있으면 이걸 우선 사용합니다.",
)

language = st.sidebar.selectbox(
    "언어(language)",
    options=["ko-KR", "en-US", "ja-JP"],
    index=0,
)

include_adult = st.sidebar.checkbox("성인 콘텐츠 포함(include_adult)", value=False)
min_vote_avg = st.sidebar.slider("최소 평점(vote_average) 필터", 0.0, 9.0, 6.0, 0.1)
min_vote_count = st.sidebar.slider("최소 투표 수(vote_count) 필터", 0, 5000, 200, 50)
show_trailer = st.sidebar.checkbox("예고편(YouTube)도 표시", value=True)

st.sidebar.divider()
st.sidebar.caption("팁: v4 토큰(Bearer) 방식이 인증/호환성이 깔끔합니다.")

# -----------------------------
# Title & intro
# -----------------------------
st.title("🎬 나와 어울리는 영화는?")
st.write("5개의 질문에 답하면, 당신의 취향에 맞는 장르를 고르고 TMDB에서 인기 영화 5편을 추천해드려요.")
st.divider()

# -----------------------------
# Questions
# 선택지 순서(중요): 1) 로맨스/드라마, 2) 액션/어드벤처, 3) SF/판타지, 4) 코미디
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

category_by_option_index = {
    0: "romance_drama",
    1: "action_adventure",
    2: "sf_fantasy",
    3: "comedy",
}

TMDB_GENRE_IDS = {
    "action": 28,
    "comedy": 35,
    "drama": 18,
    "scifi": 878,
    "romance": 10749,
    "fantasy": 14,
}

DISPLAY_LABEL = {
    "action": "액션",
    "comedy": "코미디",
    "drama": "드라마",
    "scifi": "SF",
    "romance": "로맨스",
    "fantasy": "판타지",
}

POSTER_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_API_BASE = "https://api.themoviedb.org/3"


# -----------------------------
# TMDB Client (requests-based)
# -----------------------------
def build_auth(
    api_key: str,
    bearer: str,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Returns:
      headers: if bearer present -> Authorization header
      base_params: if api_key present and no bearer -> api_key param
    """
    headers: Dict[str, str] = {"accept": "application/json"}
    base_params: Dict[str, Any] = {}

    bearer = (bearer or "").strip()
    api_key = (api_key or "").strip()

    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif api_key:
        base_params["api_key"] = api_key

    return headers, base_params


def tmdb_get(
    path: str,
    headers: Dict[str, str],
    base_params: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 4,
) -> Dict[str, Any]:
    """
    Robust GET with simple exponential backoff.
    - Handles intermittent network errors
    - Backs off on 429 / 5xx
    """
    url = f"{TMDB_API_BASE}{path}"
    merged = dict(base_params)
    if params:
        merged.update(params)

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, params=merged, timeout=15)

            # Rate limit or transient server errors
            if r.status_code in (429, 500, 502, 503, 504):
                sleep_s = min(8, 1.2 * (2**attempt))
                time.sleep(sleep_s)
                continue

            r.raise_for_status()
            return r.json()

        except requests.RequestException as e:
            last_err = e
            sleep_s = min(8, 1.2 * (2**attempt))
            time.sleep(sleep_s)

    raise RuntimeError(f"TMDB 요청 실패: {last_err}")


@st.cache_data(ttl=60 * 30)  # 30분 캐시
def discover_movies_cached(
    auth_fingerprint: str,
    genre_id: int,
    language: str,
    include_adult: bool,
    min_vote_avg: float,
    min_vote_count: int,
    pages: int = 2,
) -> List[Dict[str, Any]]:
    """
    Discover에서 여러 페이지를 가져와 pool을 만든 뒤, 유니크하게 정리해서 반환.
    auth_fingerprint: 캐시 키 분리를 위한 더미(토큰/키 자체는 저장하지 않음)
    """
    headers, base_params = st.session_state["tmdb_auth"]

    pool: List[Dict[str, Any]] = []
    for page in range(1, pages + 1):
        data = tmdb_get(
            "/discover/movie",
            headers=headers,
            base_params=base_params,
            params={
                "with_genres": genre_id,
                "language": language,
                "sort_by": "popularity.desc",
                "include_adult": str(include_adult).lower(),
                "page": page,
                "vote_average.gte": min_vote_avg,
                "vote_count.gte": min_vote_count,
            },
        )
        pool.extend(data.get("results") or [])

    # 유니크(영화 id 기준)
    uniq: Dict[int, Dict[str, Any]] = {}
    for m in pool:
        mid = m.get("id")
        if isinstance(mid, int) and mid not in uniq:
            uniq[mid] = m

    return list(uniq.values())


@st.cache_data(ttl=60 * 60)  # 60분 캐시
def movie_details_cached(
    auth_fingerprint: str,
    movie_id: int,
    language: str,
    with_trailer: bool,
) -> Dict[str, Any]:
    """
    영화 상세 + (선택) videos를 append_to_response로 1회 호출로 받음.
    """
    headers, base_params = st.session_state["tmdb_auth"]

    params = {"language": language}
    if with_trailer:
        params["append_to_response"] = "videos"

    return tmdb_get(
        f"/movie/{movie_id}",
        headers=headers,
        base_params=base_params,
        params=params,
    )


def decide_final_genre(selected_texts: List[str], category_counts: Counter) -> str:
    """
    큰 카테고리에서 1차 결정 후, 서브장르(로맨스/드라마, SF/판타지) 세부 결정.
    """
    top_category = category_counts.most_common(1)[0][0]

    if top_category == "action_adventure":
        return "action"
    if top_category == "comedy":
        return "comedy"

    if top_category == "romance_drama":
        romance_keywords = ["관계", "감정선", "감정이입", "로맨스", "설렘"]
        drama_keywords = ["여운", "성장", "현실", "고민", "정리", "천천히"]

        romance_score = sum(any(k in t for k in romance_keywords) for t in selected_texts)
        drama_score = sum(any(k in t for k in drama_keywords) for t in selected_texts)

        return "romance" if romance_score > drama_score else "drama"

    if top_category == "sf_fantasy":
        scifi_keywords = ["설정", "참신", "미래", "과학", "우주", "AI", "시간"]
        fantasy_keywords = ["능력", "운명", "마법", "전설", "왕국", "드래곤", "특별한"]

        scifi_score = sum(any(k in t for k in scifi_keywords) for t in selected_texts)
        fantasy_score = sum(any(k in t for k in fantasy_keywords) for t in selected_texts)

        return "fantasy" if fantasy_score > scifi_score else "scifi"

    return "drama"


def build_reason(genre_key: str, selected_texts: List[str], category_counts: Counter) -> str:
    label = DISPLAY_LABEL.get(genre_key, genre_key)
    top_cat, top_cnt = category_counts.most_common(1)[0]
    cat_kor = {
        "romance_drama": "로맨스/드라마",
        "action_adventure": "액션/어드벤처",
        "sf_fantasy": "SF/판타지",
        "comedy": "코미디",
    }.get(top_cat, top_cat)

    picks = []
    for t in selected_texts:
        if len(picks) >= 2:
            break
        picks.append(t if len(t) <= 28 else t[:28] + "…")

    base = f"답변에서 **{cat_kor} 성향**이 가장 강했어요({top_cnt}/5). - 그래서 **{label}** 장르가 잘 맞습니다."
    if picks:
        base += f" - 취향 포인트: “{picks[0]}”" + (f", “{picks[1]}”" if len(picks) > 1 else "")
    return base


def poster_url(poster_path: Optional[str]) -> Optional[str]:
    if not poster_path:
        return None
    return POSTER_BASE + poster_path


def extract_youtube_trailer(videos_obj: Dict[str, Any]) -> Optional[str]:
    """
    videos.results 중 YouTube Trailer 우선, 없으면 YouTube Teaser
    """
    results = (videos_obj or {}).get("results") or []
    youtube = [v for v in results if v.get("site") == "YouTube" and v.get("key")]
    if not youtube:
        return None

    def score(v: Dict[str, Any]) -> int:
        t = (v.get("type") or "").lower()
        o = (v.get("official") is True)
        # Trailer > Teaser > others, official 우대
        base = 0
        if t == "trailer":
            base += 20
        elif t == "teaser":
            base += 10
        if o:
            base += 5
        return base

    youtube.sort(key=score, reverse=True)
    return f"https://www.youtube.com/watch?v={youtube[0]['key']}"


# -----------------------------
# UI: radios
# -----------------------------
selected_texts: List[str] = []
selected_option_indices: List[int] = []

for i, item in enumerate(questions, start=1):
    st.subheader(item["q"])
    choice = st.radio(
        label="",
        options=item["options"],
        key=f"q{i}",
    )
    selected_texts.append(choice)
    selected_option_indices.append(item["options"].index(choice))
    st.write("")

st.divider()

# -----------------------------
# Submit
# -----------------------------
if st.button("결과 보기", type="primary"):
    headers, base_params = build_auth(api_key_v3, read_access_token_v4)

    if "Authorization" not in headers and "api_key" not in base_params:
        st.warning("사이드바에 TMDB 인증 정보를 입력해 주세요. - v4 토큰(Bearer) 또는 v3 API Key 중 하나면 됩니다.")
        st.stop()

    # 세션에 auth 저장 (캐시 함수에서 사용)
    st.session_state["tmdb_auth"] = (headers, base_params)

    # 캐시 분리용 fingerprint (민감정보는 직접 넣지 않음)
    auth_fingerprint = "bearer" if "Authorization" in headers else "apikey"

    # 1) 사용자 답변 -> 큰 장르 카테고리 카운트
    categories = [category_by_option_index[idx] for idx in selected_option_indices]
    category_counts = Counter(categories)

    # 2) 세부 장르 결정
    final_genre_key = decide_final_genre(selected_texts, category_counts)
    final_genre_id = TMDB_GENRE_IDS[final_genre_key]

    # 3) TMDB Discover로 후보 풀 확보(여러 페이지) -> 상위 5개 추천
    with st.spinner("분석 중..."):
        try:
            pool = discover_movies_cached(
                auth_fingerprint=auth_fingerprint,
                genre_id=final_genre_id,
                language=language,
                include_adult=include_adult,
                min_vote_avg=min_vote_avg,
                min_vote_count=min_vote_count,
                pages=2,
            )
        except Exception as e:
            st.error("TMDB Discover 요청에 실패했어요. - 인증 정보/네트워크 상태를 확인해 주세요.")
            st.caption(str(e))
            st.stop()

    if not pool:
        st.info("조건에 맞는 영화가 없어요. - 최소 평점/투표수 필터를 낮춰보세요.")
        st.stop()

    # 간단 재랭킹: popularity와 vote_average를 함께 고려(가벼운 고도화)
    def blended_score(m: Dict[str, Any]) -> float:
        pop = float(m.get("popularity") or 0.0)
        vote = float(m.get("vote_average") or 0.0)
        # popularity 스케일이 커서 log로 완화
        return (vote * 2.0) + (0.6 * (pop ** 0.5))

    pool.sort(key=blended_score, reverse=True)

    # 포스터 없는 작품은 뒤로 미룸
    pool.sort(key=lambda m: 0 if m.get("poster_path") else 1)

    picks = pool[:5]

    # 결과 헤더
    st.success(f"당신과 어울리는 장르: **{DISPLAY_LABEL.get(final_genre_key, final_genre_key)}**")
    st.caption(build_reason(final_genre_key, selected_texts, category_counts))
    st.write("")

    # 4) 상세/포스터/제목/평점/줄거리 (+ 선택: 예고편)
    for base_movie in picks:
        movie_id = base_movie.get("id")
        if not isinstance(movie_id, int):
            continue

        try:
            details = movie_details_cached(
                auth_fingerprint=auth_fingerprint,
                movie_id=movie_id,
                language=language,
                with_trailer=show_trailer,
            )
        except Exception:
            # 상세 실패 시 base 데이터로 최소 표시
            details = base_movie

        title = details.get("title") or base_movie.get("title") or "제목 없음"
        rating = details.get("vote_average", base_movie.get("vote_average"))
        overview = (details.get("overview") or base_movie.get("overview") or "").strip()
        img = poster_url(details.get("poster_path") or base_movie.get("poster_path"))

        trailer_url = None
        if show_trailer and isinstance(details.get("videos"), dict):
            trailer_url = extract_youtube_trailer(details.get("videos"))

        with st.container(border=True):
            cols = st.columns([1, 2], vertical_alignment="top")

            with cols[0]:
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.caption("포스터 없음")

            with cols[1]:
                st.markdown(f"### {title}")

                if rating is not None:
                    try:
                        st.write(f"평점: **{float(rating):.1f} / 10**")
                    except Exception:
                        st.write(f"평점: **{rating} / 10**")
                else:
                    st.write("평점: 정보 없음")

                st.write(overview if overview else "줄거리: 정보 없음")

                st.markdown(f"**이 영화를 추천하는 이유** - {build_reason(final_genre_key, selected_texts, category_counts)}")

                if trailer_url:
                    st.link_button("예고편 보기 (YouTube)", trailer_url)
