import json
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

# ============================================================
# Config
# ============================================================
st.set_page_config(page_title="나와 어울리는 영화는?", page_icon="🎬", layout="centered")

TMDB_API_BASE = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
OPENAI_API_BASE = "https://api.openai.com/v1"

# TMDB 장르 ID
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

# ============================================================
# Sidebar
# ============================================================
st.sidebar.header("API 설정")

# --- TMDB ---
st.sidebar.subheader("TMDB")
api_key_v3 = st.sidebar.text_input(
    "TMDB v3 API Key (선택)",
    type="password",
    help="v4 토큰(Bearer)을 쓰면 비워도 됩니다.",
)
read_access_token_v4 = st.sidebar.text_input(
    "TMDB v4 API Read Access Token (Bearer) (선택)",
    type="password",
    help="Read Access Token을 넣으면 Authorization: Bearer 로 호출합니다.",
)

language = st.sidebar.selectbox("언어(language)", ["ko-KR", "en-US", "ja-JP"], index=0)
include_adult = st.sidebar.checkbox("성인 콘텐츠 포함(include_adult)", value=False)
min_vote_avg = st.sidebar.slider("최소 평점(vote_average) 필터", 0.0, 9.0, 6.0, 0.1)
min_vote_count = st.sidebar.slider("최소 투표 수(vote_count) 필터", 0, 5000, 200, 50)
pages_to_pool = st.sidebar.slider("추천 후보 풀(페이지 수)", 1, 5, 2, 1)
show_trailer = st.sidebar.checkbox("예고편(YouTube) 표시", value=True)

st.sidebar.divider()

# --- OpenAI ---
st.sidebar.subheader("OpenAI (LLM 최종 1편 선정)")
use_llm_final_pick = st.sidebar.checkbox("LLM으로 최종 1편만 추천", value=True)
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password")
openai_model = st.sidebar.selectbox(
    "모델",
    options=["gpt-5-mini", "gpt-4o-mini", "gpt-4.1-mini"],
    index=0,
    help="JSON Schema 출력이 안정적인 모델을 권장합니다.",
)

# ============================================================
# UI: Title
# ============================================================
st.title("🎬 나와 어울리는 영화는?")
st.write("5개의 질문에 답하면, 당신의 취향에 맞는 장르를 고르고 TMDB에서 인기 영화 5편을 추천해드려요.")
st.caption("추가 옵션을 켜면 - 추천 5편 중에서 LLM이 ‘진짜 좋아할 1편’을 최종 선정합니다.")
st.divider()

# ============================================================
# Questions
# 선택지 순서(중요): 1) 로맨스/드라마, 2) 액션/어드벤처, 3) SF/판타지, 4) 코미디
# ============================================================
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

# ============================================================
# Helpers - TMDB Auth & Requests
# ============================================================
def build_tmdb_auth(api_key: str, bearer: str) -> Tuple[Dict[str, str], Dict[str, Any]]:
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
    url = f"{TMDB_API_BASE}{path}"
    merged = dict(base_params)
    if params:
        merged.update(params)

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, params=merged, timeout=15)

            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(8, 1.2 * (2**attempt)))
                continue

            r.raise_for_status()
            return r.json()

        except requests.RequestException as e:
            last_err = e
            time.sleep(min(8, 1.2 * (2**attempt)))

    raise RuntimeError(f"TMDB 요청 실패: {last_err}")


@st.cache_data(ttl=60 * 30)
def discover_movies_cached(
    auth_fingerprint: str,
    genre_id: int,
    language: str,
    include_adult: bool,
    min_vote_avg: float,
    min_vote_count: int,
    pages: int,
) -> List[Dict[str, Any]]:
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

    uniq: Dict[int, Dict[str, Any]] = {}
    for m in pool:
        mid = m.get("id")
        if isinstance(mid, int) and mid not in uniq:
            uniq[mid] = m

    return list(uniq.values())


@st.cache_data(ttl=60 * 60)
def movie_details_cached(
    auth_fingerprint: str,
    movie_id: int,
    language: str,
    with_trailer: bool,
) -> Dict[str, Any]:
    headers, base_params = st.session_state["tmdb_auth"]

    params: Dict[str, Any] = {"language": language}
    if with_trailer:
        params["append_to_response"] = "videos"

    return tmdb_get(f"/movie/{movie_id}", headers=headers, base_params=base_params, params=params)


def poster_url(poster_path: Optional[str]) -> Optional[str]:
    if not poster_path:
        return None
    return POSTER_BASE + poster_path


def extract_youtube_trailer(videos_obj: Dict[str, Any]) -> Optional[str]:
    results = (videos_obj or {}).get("results") or []
    youtube = [v for v in results if v.get("site") == "YouTube" and v.get("key")]

    if not youtube:
        return None

    def score(v: Dict[str, Any]) -> int:
        t = (v.get("type") or "").lower()
        official = v.get("official") is True
        s = 0
        if t == "trailer":
            s += 20
        elif t == "teaser":
            s += 10
        if official:
            s += 5
        return s

    youtube.sort(key=score, reverse=True)
    return f"https://www.youtube.com/watch?v={youtube[0]['key']}"


# ============================================================
# Helpers - Genre decision & reasons
# ============================================================
def decide_final_genre(selected_texts: List[str], category_counts: Counter) -> str:
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


# ============================================================
# Helpers - OpenAI Responses API
# ============================================================
def openai_extract_output_text(resp_json: Dict[str, Any]) -> str:
    """
    Responses API: output[] -> message -> content[] -> output_text.text
    """
    out = resp_json.get("output") or []
    chunks: List[str] = []
    for item in out:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                    chunks.append(c["text"])
    return "\n".join(chunks).strip()


def openai_pick_one_movie(
    api_key: str,
    model: str,
    user_answers: List[str],
    inferred_genre_key: str,
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    candidates: list of dicts with fields: id, title, overview, vote_average, vote_count, release_date
    returns: {"movie_id": int, "title": str, "reason": str, "confidence": float}
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("OpenAI API Key가 비어있습니다.")

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "movie_id": {"type": "integer", "description": "최종 추천 영화의 TMDB movie id"},
            "title": {"type": "string", "description": "최종 추천 영화 제목"},
            "reason": {"type": "string", "description": "사용자의 답변과 후보 영화 정보에 근거한 추천 이유 (2~4문장)"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "추천 확신도 (0~1)"},
        },
        "required": ["movie_id", "title", "reason", "confidence"],
    }

    inferred = DISPLAY_LABEL.get(inferred_genre_key, inferred_genre_key)

    prompt_user = {
        "role": "user",
        "content": (
            "아래는 대학생 사용자의 심리테스트 답변과, TMDB에서 뽑은 후보 영화 5편이다.\n"
            "목표: ‘사용자가 실제로 가장 좋아할 가능성이 높은 단 한 편’을 고른다.\n\n"
            f"[사용자 답변]\n- " + "\n- ".join(user_answers) + "\n\n"
            f"[시스템이 추정한 선호 장르]\n- {inferred} ({inferred_genre_key})\n\n"
            "[후보 영화 5편]\n"
            + "\n".join(
                [
                    (
                        f"- id={m['id']} | title={m.get('title','')} | vote={m.get('vote_average','')} "
                        f"| votes={m.get('vote_count','')} | release={m.get('release_date','')}\n"
                        f"  overview={m.get('overview','')}"
                    )
                    for m in candidates
                ]
            )
            + "\n\n"
            "선정 기준:\n"
            "1) 답변에서 드러난 ‘시청 동기’(힐링/자극/몰입/웃음)와 톤이 잘 맞는가\n"
            "2) 줄거리가 너무 무겁거나 난해한 경우는 감점(단, 답변이 몰입/세계관을 강하게 원하면 예외)\n"
            "3) 후보 중 중복된 결(비슷한 톤)이면, 더 접근성이 좋고 만족도가 높을 것으로 보이는 쪽을 선택\n\n"
            "출력은 반드시 JSON만."
        ),
    }

    instructions = (
        "너는 개인화 추천 전문가다. "
        "사용자의 답변을 근거로, 후보 5편 중 최적 1편을 고른다. "
        "반드시 주어진 JSON 스키마로만 출력한다."
    )

    body = {
        "model": model,
        "instructions": instructions,
        "input": [prompt_user],
        "temperature": 0.4,
        "max_output_tokens": 400,
        "text": {
            "format": {
                "type": "json_schema",
                "strict": True,
                "schema": schema,
            }
        },
    }

    r = requests.post(
        f"{OPENAI_API_BASE}/responses",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        data=json.dumps(body),
        timeout=30,
    )

    # 에러 처리
    if r.status_code in (401, 403):
        raise RuntimeError("OpenAI 인증 실패: API Key를 확인해 주세요.")
    if r.status_code == 429:
        raise RuntimeError("OpenAI 요청이 너무 많습니다(429). 잠시 후 다시 시도해 주세요.")
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI 요청 실패({r.status_code}): {r.text[:400]}")

    resp_json = r.json()
    text = openai_extract_output_text(resp_json)
    if not text:
        raise RuntimeError("OpenAI 응답에서 텍스트를 추출하지 못했습니다.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # 마지막 보험: 텍스트에서 JSON 구간만 잘라 파싱
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("OpenAI JSON 파싱 실패: 유효한 JSON을 찾지 못했습니다.")
        parsed = json.loads(text[start : end + 1])

    return parsed


# ============================================================
# UI: radios
# ============================================================
selected_texts: List[str] = []
selected_option_indices: List[int] = []

for i, item in enumerate(questions, start=1):
    st.subheader(item["q"])
    choice = st.radio("", item["options"], key=f"q{i}")
    selected_texts.append(choice)
    selected_option_indices.append(item["options"].index(choice))
    st.write("")

st.divider()

# ============================================================
# Submit
# ============================================================
if st.button("결과 보기", type="primary"):
    # --- TMDB Auth check ---
    headers, base_params = build_tmdb_auth(api_key_v3, read_access_token_v4)
    if "Authorization" not in headers and "api_key" not in base_params:
        st.warning("사이드바에 TMDB 인증 정보를 입력해 주세요. - v4 토큰(Bearer) 또는 v3 API Key 중 하나면 됩니다.")
        st.stop()

    st.session_state["tmdb_auth"] = (headers, base_params)
    auth_fingerprint = "bearer" if "Authorization" in headers else "apikey"

    # --- 1) 답변 분석 -> 장르 결정 ---
    categories = [category_by_option_index[idx] for idx in selected_option_indices]
    category_counts = Counter(categories)
    final_genre_key = decide_final_genre(selected_texts, category_counts)
    final_genre_id = TMDB_GENRE_IDS[final_genre_key]

    # --- 2) TMDB Discover -> 후보 풀 ---
    with st.spinner("분석 중..."):
        try:
            pool = discover_movies_cached(
                auth_fingerprint=auth_fingerprint,
                genre_id=final_genre_id,
                language=language,
                include_adult=include_adult,
                min_vote_avg=min_vote_avg,
                min_vote_count=min_vote_count,
                pages=pages_to_pool,
            )
        except Exception as e:
            st.error("TMDB Discover 요청에 실패했습니다. - 인증/네트워크 상태를 확인해 주세요.")
            st.caption(str(e))
            st.stop()

    if not pool:
        st.info("조건에 맞는 영화가 없습니다. - 최소 평점/투표수 필터를 낮춰보세요.")
        st.stop()

    # --- 3) 간단 재랭킹(고도화) ---
    def blended_score(m: Dict[str, Any]) -> float:
        pop = float(m.get("popularity") or 0.0)
        vote = float(m.get("vote_average") or 0.0)
        # popularity는 스케일이 커서 sqrt로 완화
        return (vote * 2.0) + (0.6 * (pop ** 0.5))

    pool.sort(key=blended_score, reverse=True)
    pool.sort(key=lambda m: 0 if m.get("poster_path") else 1)  # 포스터 없는 건 뒤로

    top5 = pool[:5]

    # --- 4) Top5 상세 조회 + 표시용 정리 ---
    movies_for_display: List[Dict[str, Any]] = []
    with st.spinner("추천 목록 가져오는 중..."):
        for base_movie in top5:
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
                details = base_movie

            movies_for_display.append(
                {
                    "id": movie_id,
                    "title": details.get("title") or base_movie.get("title") or "제목 없음",
                    "overview": (details.get("overview") or base_movie.get("overview") or "").strip(),
                    "vote_average": details.get("vote_average", base_movie.get("vote_average")),
                    "vote_count": details.get("vote_count", base_movie.get("vote_count")),
                    "release_date": details.get("release_date", base_movie.get("release_date")),
                    "poster_path": details.get("poster_path") or base_movie.get("poster_path"),
                    "videos": details.get("videos") if isinstance(details.get("videos"), dict) else None,
                }
            )

    # --- 결과 헤더 ---
    st.success(f"당신과 어울리는 장르: **{DISPLAY_LABEL.get(final_genre_key, final_genre_key)}**")
    st.caption(build_reason(final_genre_key, selected_texts, category_counts))
    st.write("")

    # --- 5) LLM 최종 1편 선정(옵션) ---
    llm_pick: Optional[Dict[str, Any]] = None
    if use_llm_final_pick:
        if not openai_api_key.strip():
            st.warning("LLM 최종 추천을 켰습니다. - 사이드바에 OpenAI API Key를 입력해 주세요.")
        else:
            # LLM에 넘길 후보는 "표시용" 5편 그대로
            candidates_payload = []
            for m in movies_for_display:
                candidates_payload.append(
                    {
                        "id": m["id"],
                        "title": m["title"],
                        "overview": m["overview"],
                        "vote_average": float(m["vote_average"] or 0.0),
                        "vote_count": int(m["vote_count"] or 0),
                        "release_date": m.get("release_date") or "",
                    }
                )

            with st.spinner("LLM이 최종 1편을 고르는 중..."):
                try:
                    llm_pick = openai_pick_one_movie(
                        api_key=openai_api_key,
                        model=openai_model,
                        user_answers=selected_texts,
                        inferred_genre_key=final_genre_key,
                        candidates=candidates_payload,
                    )
                except Exception as e:
                    st.error("LLM 최종 추천에 실패했습니다. - OpenAI API Key/요청 상태를 확인해 주세요.")
                    st.caption(str(e))
                    llm_pick = None

    # --- 6) 최종 추천 강조 카드 ---
    if llm_pick and isinstance(llm_pick, dict):
        picked_id = llm_pick.get("movie_id")
        picked_movie = next((m for m in movies_for_display if m["id"] == picked_id), None)

        if picked_movie:
            st.subheader("✅ LLM 최종 추천 - 딱 한 편")
            with st.container(border=True):
                cols = st.columns([1, 2], vertical_alignment="top")

                with cols[0]:
                    img = poster_url(picked_movie.get("poster_path"))
                    if img:
                        st.image(img, use_container_width=True)
                    else:
                        st.caption("포스터 없음")

                with cols[1]:
                    st.markdown(f"### {picked_movie['title']}")
                    va = picked_movie.get("vote_average")
                    vc = picked_movie.get("vote_count")
                    if va is not None:
                        try:
                            st.write(f"평점: **{float(va):.1f} / 10** - 투표 {int(vc or 0):,}개")
                        except Exception:
                            st.write(f"평점: **{va} / 10**")
                    st.write(picked_movie["overview"] if picked_movie["overview"] else "줄거리: 정보 없음")

                    reason = (llm_pick.get("reason") or "").strip()
                    conf = llm_pick.get("confidence", None)

                    if reason:
                        st.markdown("**추천 이유**")
                        st.write(reason)

                    if isinstance(conf, (int, float)):
                        st.progress(min(max(float(conf), 0.0), 1.0))

                    # 예고편 버튼
                    if show_trailer and isinstance(picked_movie.get("videos"), dict):
                        trailer_url = extract_youtube_trailer(picked_movie["videos"])
                        if trailer_url:
                            st.link_button("예고편 보기 (YouTube)", trailer_url)

            st.divider()

    # --- 7) TMDB Top5 전체 표시 ---
    st.subheader("🎞️ 추천 후보 5편")
    for m in movies_for_display:
        img = poster_url(m.get("poster_path"))
        title = m.get("title", "제목 없음")
        rating = m.get("vote_average")
        overview = m.get("overview") or ""
        trailer_url = extract_youtube_trailer(m["videos"]) if (show_trailer and isinstance(m.get("videos"), dict)) else None

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

st.divider()
with st.expander("🔍 (옵션) 디버그 정보 보기"):
    st.write("선택 답변:", selected_texts)
    st.write("옵션 인덱스:", selected_option_indices)
    try:
        st.write("카테고리 카운트:", dict(category_counts))
        st.write("최종 장르:", final_genre_key)
    except Exception:
        st.write("결과 버튼을 누르면 여기에 분석 정보가 표시됩니다.")


