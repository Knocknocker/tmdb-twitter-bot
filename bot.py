import os
import sys
import random
import textwrap
from datetime import date, timedelta

import requests
import tweepy

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TMDB_DEFAULT_REGION = os.environ.get("TMDB_DEFAULT_REGION", "TR")

# X / Twitter credentials
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN")
X_API_KEY = os.environ.get("X_API_KEY")
X_API_SECRET = os.environ.get("X_API_SECRET")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.environ.get("X_ACCESS_SECRET")

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def ensure_env():
    missing = []
    if not TMDB_API_KEY:
        missing.append("TMDB_API_KEY")
    if not (X_BEARER_TOKEN and X_API_KEY and X_API_SECRET and X_ACCESS_TOKEN and X_ACCESS_SECRET):
        missing.extend(
            ["X_BEARER_TOKEN", "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
        )
    if missing:
        raise RuntimeError(f"Eksik environment değişkenleri: {', '.join(missing)}")


def tmdb_get(path, params=None):
    if params is None:
        params = {}
    params["api_key"] = TMDB_API_KEY
    url = TMDB_BASE_URL + path
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def pick_best_result(results, min_vote_count=50):
    """
    Poster'ı olan, oylanmış, mantıklı bir film seç.
    """
    filtered = [
        r for r in results
        if r.get("poster_path") and r.get("vote_count", 0) >= min_vote_count
    ]
    if not filtered:
        filtered = [r for r in results if r.get("poster_path")] or results
    if not filtered:
        return None
    # popularity + vote_average'e göre en iyiyi seç
    filtered.sort(key=lambda r: (r.get("vote_average", 0.0), r.get("popularity", 0.0)), reverse=True)
    return filtered[0]


def shorten(text, max_len=180):
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def build_poster_url(poster_path):
    if not poster_path:
        return None
    return f"{TMDB_IMAGE_BASE}{poster_path}"


def tweet(text):
    """
    Tek metin tweet atar.
    Tweet çok uzunsa 280 karaktere otomatik kısaltır.
    Duplicate veya diğer 403 hatalarında workflow'u patlatmaz.
    """
    # Tweet uzunluğu sınırı
    max_len = 270  # 280 değil, biraz boşluk bırakıyoruz

    # Eğer tweet çok uzunsa kısalt
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."

    client = tweepy.Client(
        bearer_token=X_BEARER_TOKEN,
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET,
    )
    try:
        resp = client.create_tweet(text=text)
        print("Tweet gönderildi:", resp)
    except tweepy.errors.Forbidden as e:
        msg = str(e).lower()
        if "duplicate" in msg:
            print("Aynı içerikten zaten tweet atılmış, atlıyorum.")
        else:
            print("403 Forbidden - Twitter bu tweet'e izin vermedi, atlıyorum.")
            print("Hata detayı:", e)





# ----------------- MODLAR ----------------- #

def mode_1_turkey_popular_today():
    """
    1) Bugün Türkiye'de en popüler film
    """
    data = tmdb_get(
        "/movie/popular",
        {"language": "tr-TR", "region": TMDB_DEFAULT_REGION, "page": 1},
    )
    movie = pick_best_result(data.get("results", []))
    if not movie:
        print("Film bulunamadı.")
        return

    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 150)
    url = f"https://tmdb.org/movie/{movie['id']}"

    text = f"""🎬 Bugün Türkiye'de en popüler film:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

Daha fazla: {url}
#film #sinema #tmdb"""
    tweet(text)


def mode_2_world_popular_today():
    """
    2) Dünyada bugün en popüler film (tweet Türkçe)
    """
    data = tmdb_get(
        "/movie/popular",
        {"language": "tr-TR", "page": 1},
    )
    movie = pick_best_result(data.get("results", []))
    if not movie:
        print("Film bulunamadı.")
        return

    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 150)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""🌍 Bugün dünyada en popüler film:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

Detaylar: {url}
#film #sinema #tmdb"""
    tweet(text)



def mode_3_new_release_today():
    """
    3) Yeni çıkan film (son 7 günden bir film, yoksa trend filme düşer)
    """
    today = date.today()
    start = today - timedelta(days=7)  # 2 yerine 7 gün aldık

    # Önce son 7 günde çıkan filmlerden en popüler olanı dene
    params = {
        "language": "tr-TR",
        "region": TMDB_DEFAULT_REGION,
        "sort_by": "popularity.desc",
        "primary_release_date.gte": start.isoformat(),
        "primary_release_date.lte": today.isoformat(),
        "page": 1,
    }
    data = tmdb_get("/discover/movie", params)
    movie = pick_best_result(data.get("results", []), min_vote_count=1)

    # Eğer hiç film bulamazsak, trending'e fallback
    if not movie:
        print("Son 7 günde yeni film bulunamadı, trending'e düşüyorum.")
        trend_data = tmdb_get("/trending/movie/day", {"language": "tr-TR"})
        movie = pick_best_result(trend_data.get("results", []), min_vote_count=1)
        if not movie:
            print("Trending'de de film bulunamadı, tweet atlamayı tercih ettim.")
            return

    title = movie["title"]
    date_str = movie.get("release_date", "")
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 150)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""🎟 Son günlerde vizyona gelen bir film:
{title} ({date_str}) – ⭐ {vote:.1f}

{overview}

Detaylar: {url}
#yenifilm #filmönerisi #tmdb"""
    tweet(text)


def mode_4_week_top_rated():
    """
    4) Son 7 günde çıkanlar içinde en yüksek puanlı film
    """
    today = date.today()
    start = today - timedelta(days=7)
    params = {
        "language": "en-US",
        "sort_by": "vote_average.desc",
        "vote_count.gte": 100,
        "primary_release_date.gte": start.isoformat(),
        "primary_release_date.lte": today.isoformat(),
        "page": 1,
    }
    data = tmdb_get("/discover/movie", params)
    movie = pick_best_result(data.get("results", []), min_vote_count=100)
    if not movie:
        print("Film bulunamadı.")
        return

    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 150)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""📈 Haftanın en yüksek puanlı yeni filmi:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

Detay: {url}
#filmönerisi #tmdb"""
    tweet(text)


def mode_5_random_quality():
    """
    5) Rastgele ama kaliteli bir film (tweet Türkçe)
    """
    base_params = {
        "language": "tr-TR",
        "sort_by": "popularity.desc",
        "vote_average.gte": 7.5,
        "vote_count.gte": 300,
    }
    first = tmdb_get("/discover/movie", base_params)
    total_pages = min(first.get("total_pages", 1), 50)
    random_page = random.randint(1, max(total_pages, 1))
    params = dict(base_params)
    params["page"] = random_page
    data = tmdb_get("/discover/movie", params)

    results = data.get("results") or first.get("results") or []
    if not results:
        print("Rastgele kaliteli film bulunamadı.")
        return

    movie = random.choice(results)
    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 160)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""🎲 Bugünün rastgele kaliteli filmi:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

Listeye ekle: {url}
#filmönerisi #random #tmdb"""
    tweet(text)



def mode_8_netflix_tr_popular():
    """
    8) Türkiye'de Netflix'te en popüler film
    Netflix watch_provider id: 8 (örnek: US için 8; TR’de de çoğu senaryoda 8) :contentReference[oaicite:5]{index=5}
    """
    params = {
        "language": "tr-TR",
        "sort_by": "popularity.desc",
        "with_watch_providers": 8,
        "watch_region": TMDB_DEFAULT_REGION,
        "page": 1,
    }
    data = tmdb_get("/discover/movie", params)
    movie = pick_best_result(data.get("results", []), min_vote_count=20)
    if not movie:
        print("Netflix filmi bulunamadı.")
        return

    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 150)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""📺 Türkiye'de Netflix'te en popüler film:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

TMDB sayfası: {url}
#netflix #film #tmdb"""
    tweet(text)


def mode_10_box_office_like():
    """
    10) Son haftanın 'gişe şampiyonu'na yakın bir şey:
    Son 14 günde çıkan filmleri gelir (revenue) proxy'si olarak popularity.desc ile sıralıyoruz.
    """
    today = date.today()
    start = today - timedelta(days=14)
    params = {
        "language": "en-US",
        "sort_by": "popularity.desc",
        "primary_release_date.gte": start.isoformat(),
        "primary_release_date.lte": today.isoformat(),
        "vote_count.gte": 100,
        "page": 1,
    }
    data = tmdb_get("/discover/movie", params)
    movie = pick_best_result(data.get("results", []), min_vote_count=100)
    if not movie:
        print("Film bulunamadı.")
        return

    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 150)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""💰 Son haftaların gişe şampiyonu kıvamında film:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

Daha fazla: {url}
#boxoffice #film #tmdb"""
    tweet(text)


def mode_13_trending_riser():
    """
    13) Son 24 saatin yükselen filmi (TMDB trending/day)
    """
    data = tmdb_get("/trending/movie/day", {"language": "en-US"})
    movie = pick_best_result(data.get("results", []), min_vote_count=50)
    if not movie:
        print("Film bulunamadı.")
        return

    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 150)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""🚀 Son 24 saatte trend olan film:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

TMDB: {url}
#trending #film #tmdb"""
    tweet(text)


def mode_14_best_poster():
    """
    14) Posteri en iyi görünen popüler film (poster'ı olan popüler filmlerden rastgele)
    """
    data = tmdb_get("/movie/popular", {"language": "en-US", "page": 1})
    candidates = [m for m in data.get("results", []) if m.get("poster_path")]
    if not candidates:
        print("Poster'lı film bulunamadı.")
        return

    movie = random.choice(candidates)
    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    poster_url = build_poster_url(movie["poster_path"])
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""🖼 Bugünün poster seçimi:
{title} ({year})

Poster: {poster_url}
Detay: {url}
#poster #film #tmdb"""
    tweet(text)


def mode_15_turkish_movies_popular():
    """
    15) En popüler Türk filmi (orijinal dili tr)
    """
    params = {
        "language": "tr-TR",
        "with_original_language": "tr",
        "sort_by": "popularity.desc",
        "page": 1,
    }
    data = tmdb_get("/discover/movie", params)
    movie = pick_best_result(data.get("results", []), min_vote_count=20)
    if not movie:
        print("Türk filmi bulunamadı.")
        return

    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 150)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""🇹🇷 Bugün en popüler Türk filmi:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

Detay: {url}
#yerlifilm #turkiye #tmdb"""
    tweet(text)


def mode_16_classic_of_day():
    """
    16) Belirli bir yıldan önceki 'klasik' film (2005 öncesi)
    """
    base_params = {
        "language": "en-US",
        "sort_by": "popularity.desc",
        "primary_release_date.lte": "2005-12-31",
        "vote_count.gte": 500,
    }
    first = tmdb_get("/discover/movie", base_params)
    total_pages = min(first.get("total_pages", 1), 50)
    random_page = random.randint(1, max(total_pages, 1))
    params = dict(base_params)
    params["page"] = random_page
    data = tmdb_get("/discover/movie", params)

    results = data.get("results") or first.get("results") or []
    if not results:
        print("Klasik film bulunamadı.")
        return

    movie = random.choice(results)
    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 160)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""🎞 Bugünün klasik filmi:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

Koleksiyona ekle: {url}
#klasik #film #tmdb"""
    tweet(text)


def mode_17_hidden_gem():
    """
    17) Gizli mücevher: puanı yüksek ama çok da patlamamış film
    Önce 7.0+ ve 100–2000 oy aralığına bakar, yoksa 7.0+ ve 50+ oya düşer.
    """
    base_params = {
        "language": "tr-TR",
        "sort_by": "popularity.desc",
        "vote_average.gte": 7.0,
        "vote_count.gte": 100,
        "vote_count.lte": 2000,
    }
    first = tmdb_get("/discover/movie", base_params)
    results = first.get("results") or []

    # Eğer bu aralıkta film bulamazsak, filtreyi gevşet
    if not results:
        print("Dar hidden gem filtresinde film bulunamadı, filtremi gevşetiyorum.")
        relaxed_params = {
            "language": "tr-TR",
            "sort_by": "popularity.desc",
            "vote_average.gte": 7.0,
            "vote_count.gte": 50,
        }
        first = tmdb_get("/discover/movie", relaxed_params)
        results = first.get("results") or []
        base_params = relaxed_params  # sayfaları bu parametreyle gezeceğiz

    if not results:
        print("Hidden gem film hâlâ bulunamadı, tweet atlamayı tercih ettim.")
        return

    total_pages = min(first.get("total_pages", 1), 30)
    random_page = random.randint(1, max(total_pages, 1))
    params = dict(base_params)
    params["page"] = random_page
    data = tmdb_get("/discover/movie", params)

    all_results = data.get("results") or results
    movie = random.choice(all_results)

    title = movie["title"]
    year = movie.get("release_date", "")[:4]
    vote = movie.get("vote_average", 0.0)
    overview = shorten(movie.get("overview", ""), 160)
    url = f"https://www.themoviedb.org/movie/{movie['id']}"

    text = f"""💎 Bugünün gizli mücevher filmi:
{title} ({year}) – ⭐ {vote:.1f}

{overview}

Keşfet: {url}
#gizlifilm #filmönerisi #tmdb"""
    tweet(text)



MODES = {
    "1": mode_1_turkey_popular_today,
    "2": mode_2_world_popular_today,
    "3": mode_3_new_release_today,
    "4": mode_4_week_top_rated,
    "5": mode_5_random_quality,
    "8": mode_8_netflix_tr_popular,
    "10": mode_10_box_office_like,
    "13": mode_13_trending_riser,
    "14": mode_14_best_poster,
    "15": mode_15_turkish_movies_popular,
    "16": mode_16_classic_of_day,
    "17": mode_17_hidden_gem,
}


def main():
    ensure_env()
    if len(sys.argv) < 2:
        raise SystemExit(
            "Kullanım: python bot.py <MODE>\n"
            "Örnek: python bot.py 1  # Türkiye'de en popüler film"
        )
    mode_key = sys.argv[1]
    func = MODES.get(mode_key)
    if not func:
        raise SystemExit(f"Bilinmeyen MODE: {mode_key}")
    func()


if __name__ == "__main__":
    main()
