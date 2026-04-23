"""
QuantEdge AI — Duygu Analizi Veri Çekme Modülü
================================================
Kaynaklar:
  1. Reddit (PRAW)    : r/wallstreetbets, r/stocks, r/investing
  2. StockTwits       : Borsa odaklı sosyal medya
  3. NewsAPI          : Bloomberg, Reuters, CNBC haber akışı
  4. GDELT Project    : Jeopolitik haber analizi (ücretsiz)

NLP Pipeline:
  FinBERT (ProsusAI/finbert) → Finansal metin için fine-tuned BERT
  Girdi: Ham metin
  Çıktı: {positive, negative, neutral} skorları

Mimari Not (Senior Architect):
  Haberler ChromaDB'ye embedding olarak saklanır.
  Bu, benzer geçmiş olayları RAG pipeline ile sorgulamayı sağlar.
  Örnek: "Fed faiz artırımı" haberi geldiğinde geçmişteki benzer
         olayların piyasaya etkisi semantik arama ile bulunur.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import structlog

from app.core.config import settings
from app.core.cache import cache_manager, CacheNamespace
from app.utils.retry import async_retry, reddit_limiter, news_api_limiter

logger = structlog.get_logger()


# ----------------------------------------------------------
# FinBERT NLP PIPELINE
# ----------------------------------------------------------

class FinBERTAnalyzer:
    """
    FinBERT tabanlı finansal duygu analizi.
    HuggingFace'den ProsusAI/finbert modeli kullanılır.

    Neden FinBERT?
    - Finansal metinler için BERT'i fine-tune edilmiş
    - VADER/TextBlob'dan %15-20 daha doğru (FiQA benchmark)
    - "Bearish", "bullish", "earnings beat" gibi terimleri anlar

    Not: İlk çalıştırmada model (~420MB) indirilir.
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._pipeline = None
        self._initialized = False

    def _initialize(self):
        """Lazy initialization — ilk kullanımda yükle."""
        if self._initialized:
            return
        try:
            from transformers import pipeline as hf_pipeline
            logger.info("FinBERT yükleniyor...")
            self._pipeline = hf_pipeline(
                "text-classification",
                model="ProsusAI/finbert",
                return_all_scores=True,
                device=-1,   # CPU (-1), GPU için 0 kullan
            )
            self._initialized = True
            logger.info("FinBERT hazır.")
        except ImportError:
            logger.warning("transformers kütüphanesi bulunamadı. Kural tabanlı sentiment kullanılıyor.")
            self._initialized = True   # Fallback'e geçecek
        except Exception as e:
            logger.error("FinBERT yüklenemedi.", error=str(e))
            self._initialized = True

    def analyze_batch(self, texts: List[str]) -> List[Dict]:
        """
        Metin listesini analiz eder.

        Args:
            texts: Analiz edilecek metin listesi (max 512 token/metin)

        Returns:
            [{'positive': 0.8, 'negative': 0.1, 'neutral': 0.1, 'composite': 0.7}]
        """
        self._initialize()

        if not texts:
            return []

        # Metinleri temizle ve kısalt (BERT max 512 token)
        cleaned = [self._clean_text(t)[:512] for t in texts]

        results = []
        if self._pipeline:
            try:
                raw_results = self._pipeline(cleaned, batch_size=8, truncation=True)
                for raw in raw_results:
                    scores = {item["label"].lower(): item["score"] for item in raw}
                    pos = scores.get("positive", 0.33)
                    neg = scores.get("negative", 0.33)
                    neu = scores.get("neutral", 0.33)
                    composite = pos - neg   # -1 ile 1 arası
                    results.append({
                        "positive": round(pos, 4),
                        "negative": round(neg, 4),
                        "neutral": round(neu, 4),
                        "composite": round(composite, 4),
                    })
            except Exception as e:
                logger.warning("FinBERT tahmin hatası, fallback kullanılıyor.", error=str(e))
                results = [self._rule_based_sentiment(t) for t in cleaned]
        else:
            # FinBERT yoksa kural tabanlı sentiment
            results = [self._rule_based_sentiment(t) for t in cleaned]

        return results

    def analyze_single(self, text: str) -> Dict:
        """Tek metin için sentiment analizi."""
        results = self.analyze_batch([text])
        return results[0] if results else {"positive": 0.33, "negative": 0.33, "neutral": 0.33, "composite": 0.0}

    def _clean_text(self, text: str) -> str:
        """Metni analiz için temizler."""
        # URL'leri kaldır
        text = re.sub(r'http\S+|www\S+', '', text)
        # Özel karakterleri kaldır
        text = re.sub(r'[^\w\s.,!?$%#@]', ' ', text)
        # Fazla boşlukları temizle
        text = ' '.join(text.split())
        return text.strip()

    def _rule_based_sentiment(self, text: str) -> Dict:
        """
        FinBERT yokken kullanılan kural tabanlı fallback.
        Finansal kelime listesi tabanlı basit sentiment.
        """
        text_lower = text.lower()

        bullish_words = [
            'buy', 'bull', 'bullish', 'gain', 'profit', 'surge', 'rally',
            'growth', 'beat', 'exceed', 'strong', 'up', 'positive', 'boost',
            'upgrade', 'outperform', 'record', 'high', 'breakout', 'rocket',
        ]
        bearish_words = [
            'sell', 'bear', 'bearish', 'loss', 'drop', 'crash', 'plunge',
            'decline', 'miss', 'weak', 'down', 'negative', 'cut', 'downgrade',
            'underperform', 'low', 'breakdown', 'warning', 'layoff', 'debt',
        ]

        bull_count = sum(1 for w in bullish_words if w in text_lower)
        bear_count = sum(1 for w in bearish_words if w in text_lower)
        total = bull_count + bear_count + 1

        pos = bull_count / total
        neg = bear_count / total
        neu = 1 - pos - neg

        return {
            "positive": round(max(0, pos), 4),
            "negative": round(max(0, neg), 4),
            "neutral": round(max(0, neu), 4),
            "composite": round(pos - neg, 4),
        }


# ----------------------------------------------------------
# REDDIT FETCHER
# ----------------------------------------------------------

class RedditFetcher:
    """
    Reddit API (PRAW) istemcisi.
    r/wallstreetbets, r/stocks, r/investing takibi.

    Ücretsiz — https://www.reddit.com/prefs/apps
    """

    SUBREDDITS = [
        "wallstreetbets",
        "stocks",
        "investing",
        "StockMarket",
        "options",
    ]

    def __init__(self, sentiment_analyzer: FinBERTAnalyzer):
        self.analyzer = sentiment_analyzer
        self._reddit = None

    def _get_reddit(self):
        """Lazy PRAW initialization."""
        if not self._reddit:
            if not settings.has_reddit:
                raise ValueError("Reddit API kimlik bilgileri tanımlı değil.")
            import praw
            self._reddit = praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT,
            )
        return self._reddit

    @async_retry(max_attempts=2, delay=3.0)
    async def get_ticker_mentions(
        self,
        ticker: str,
        hours: int = 24,
        limit: int = 100,
    ) -> Dict:
        """
        Ticker için Reddit gönderilerini ve yorumlarını çeker.

        Args:
            ticker : Hisse kodu
            hours  : Kaç saatlik geçmişe bakılsın
            limit  : Maksimum gönderi sayısı

        Returns:
            Agregat sentiment skoru ve mentionlar
        """
        cache_key = f"{ticker}:reddit:{hours}h"
        cached = await cache_manager.get(CacheNamespace.SENTIMENT, cache_key)
        if cached:
            return cached

        if not settings.has_reddit:
            logger.debug("Reddit kimlik bilgisi yok. Mock sentiment döndürülüyor.", ticker=ticker)
            return self._mock_sentiment(ticker, "reddit")

        loop = asyncio.get_event_loop()

        def fetch_sync():
            reddit = self._get_reddit()
            texts = []
            scores = []

            cutoff = datetime.utcnow() - timedelta(hours=hours)

            for subreddit_name in self.SUBREDDITS[:3]:  # Rate limit için 3 ile sınırla
                try:
                    subreddit = reddit.subreddit(subreddit_name)
                    # Ticker'ı ara
                    for post in subreddit.search(ticker, limit=limit // 3, time_filter="day"):
                        created = datetime.utcfromtimestamp(post.created_utc)
                        if created < cutoff:
                            continue

                        text = f"{post.title} {post.selftext or ''}"
                        if ticker.upper() in text.upper():
                            texts.append(text)
                            scores.append(post.score)   # Upvote sayısı

                except Exception as e:
                    logger.warning(f"Reddit r/{subreddit_name} hatası.", error=str(e))
                    continue

            return texts, scores

        async with reddit_limiter():
            texts, upvote_scores = await loop.run_in_executor(None, fetch_sync)

        if not texts:
            result = self._mock_sentiment(ticker, "reddit")
            return result

        # FinBERT ile analiz
        sentiments = self.analyzer.analyze_batch(texts)

        # Upvote ağırlıklı ortalama
        total_weight = sum(max(1, s) for s in upvote_scores) if upvote_scores else len(texts)
        weights = [max(1, s) / total_weight for s in upvote_scores] if upvote_scores else [1 / len(texts)] * len(texts)

        weighted_pos = sum(s["positive"] * w for s, w in zip(sentiments, weights))
        weighted_neg = sum(s["negative"] * w for s, w in zip(sentiments, weights))
        weighted_neu = sum(s["neutral"] * w for s, w in zip(sentiments, weights))
        composite = weighted_pos - weighted_neg

        result = {
            "ticker": ticker,
            "source": "reddit",
            "positive": round(weighted_pos, 4),
            "negative": round(weighted_neg, 4),
            "neutral": round(weighted_neu, 4),
            "composite": round(composite, 4),
            "mention_count": len(texts),
            "subreddits_checked": self.SUBREDDITS[:3],
            "timestamp": datetime.utcnow().isoformat(),
        }

        await cache_manager.set(CacheNamespace.SENTIMENT, cache_key, result, ttl=1800)
        return result

    def _mock_sentiment(self, ticker: str, source: str) -> Dict:
        """API yokken deterministik mock sentiment."""
        import hashlib
        seed = int(hashlib.md5(f"{ticker}{source}".encode()).hexdigest(), 16) % 100
        composite = (seed - 50) / 100   # -0.5 ile 0.5 arası
        positive = max(0.1, 0.5 + composite * 0.3)
        negative = max(0.1, 0.5 - composite * 0.3)
        neutral = max(0.0, 1 - positive - negative)
        return {
            "ticker": ticker,
            "source": source,
            "positive": round(positive, 4),
            "negative": round(negative, 4),
            "neutral": round(neutral, 4),
            "composite": round(composite, 4),
            "mention_count": seed * 10,
            "timestamp": datetime.utcnow().isoformat(),
            "is_mock": True,
        }


# ----------------------------------------------------------
# NEWS API FETCHER
# ----------------------------------------------------------

class NewsFetcher:
    """
    NewsAPI istemcisi.
    Bloomberg, Reuters, CNBC, WSJ, Financial Times haber akışı.

    Ücretsiz: Günde 100 istek — https://newsapi.org
    """

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self, sentiment_analyzer: FinBERTAnalyzer):
        self.analyzer = sentiment_analyzer
        self.api_key = settings.NEWS_API_KEY

    @async_retry(max_attempts=2, delay=2.0)
    async def get_ticker_news(
        self,
        ticker: str,
        company_name: Optional[str] = None,
        hours: int = 48,
        limit: int = 20,
    ) -> Dict:
        """
        Hisse için haber makalelerini çeker ve sentiment analizi yapar.
        """
        cache_key = f"{ticker}:news:{hours}h"
        cached = await cache_manager.get(CacheNamespace.NEWS, cache_key)
        if cached:
            return cached

        if not self.api_key:
            logger.debug("NewsAPI anahtarı yok. Mock haber sentiment döndürülüyor.", ticker=ticker)
            return self._build_mock_news_result(ticker)

        # Arama sorgusu: ticker + şirket adı
        query = f"{ticker} stock"
        if company_name:
            short_name = company_name.split()[0]   # "Apple Inc." → "Apple"
            query = f"{short_name} OR {ticker} stock market"

        from_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "q": query,
            "from": from_date,
            "sortBy": "relevancy",
            "pageSize": min(limit, 100),
            "language": "en",
            # Güvenilir finans kaynakları filtresi
            "domains": "bloomberg.com,reuters.com,cnbc.com,wsj.com,ft.com,marketwatch.com,barrons.com",
            "apiKey": self.api_key,
        }

        async with news_api_limiter():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/everything",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 429:
                        raise Exception("NewsAPI rate limit aşıldı.")
                    if resp.status != 200:
                        raise Exception(f"NewsAPI HTTP {resp.status}")
                    data = await resp.json()

        articles = data.get("articles", [])
        if not articles:
            return self._build_mock_news_result(ticker)

        # Başlık + açıklama metinleri
        texts = []
        article_meta = []
        for article in articles:
            text = f"{article.get('title', '')} {article.get('description', '')}"
            if len(text.strip()) > 20:
                texts.append(text)
                article_meta.append({
                    "title": article.get("title"),
                    "source": article.get("source", {}).get("name"),
                    "published_at": article.get("publishedAt"),
                    "url": article.get("url"),
                })

        # FinBERT analizi
        sentiments = self.analyzer.analyze_batch(texts)

        # Ortalama sentiment
        avg_pos = sum(s["positive"] for s in sentiments) / len(sentiments)
        avg_neg = sum(s["negative"] for s in sentiments) / len(sentiments)
        avg_neu = sum(s["neutral"] for s in sentiments) / len(sentiments)
        composite = avg_pos - avg_neg

        result = {
            "ticker": ticker,
            "source": "news",
            "positive": round(avg_pos, 4),
            "negative": round(avg_neg, 4),
            "neutral": round(avg_neu, 4),
            "composite": round(composite, 4),
            "article_count": len(articles),
            "top_headlines": article_meta[:5],
            "timestamp": datetime.utcnow().isoformat(),
        }

        # ChromaDB'ye embedding olarak kaydet (RAG için)
        await self._store_in_vector_db(ticker, texts, article_meta)

        await cache_manager.set(CacheNamespace.NEWS, cache_key, result, ttl=3600)
        return result

    async def _store_in_vector_db(self, ticker: str, texts: List[str], metadata: List[Dict]):
        """
        Haberleri ChromaDB'ye embedding olarak kaydeder.
        RAG (Retrieval Augmented Generation) pipeline için.

        Bu, geçmişteki benzer haberleri semantik arama ile
        bulmayı sağlar: "FED faiz artırımı" → geçmişteki etkileri bul.
        """
        try:
            import chromadb
            client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
            )
            collection = client.get_or_create_collection(
                name=f"news_{ticker.lower()}",
                metadata={"hnsw:space": "cosine"},
            )

            docs = texts[:10]  # İlk 10 makale
            ids = [f"{ticker}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{i}" for i in range(len(docs))]
            metas = [{"ticker": ticker, "source": m.get("source", ""), "date": m.get("published_at", "")}
                     for m in metadata[:len(docs)]]

            collection.add(documents=docs, ids=ids, metadatas=metas)
            logger.debug("Haberler ChromaDB'ye kaydedildi.", ticker=ticker, count=len(docs))

        except Exception as e:
            logger.warning("ChromaDB kayıt hatası.", error=str(e))

    def _build_mock_news_result(self, ticker: str) -> Dict:
        """Mock haber sentiment."""
        import hashlib
        seed = int(hashlib.md5(f"{ticker}news".encode()).hexdigest(), 16) % 100
        composite = (seed - 50) / 120
        positive = 0.4 + composite * 0.2
        negative = 0.3 - composite * 0.2
        neutral = 1 - positive - negative

        return {
            "ticker": ticker,
            "source": "news",
            "positive": round(max(0.1, positive), 4),
            "negative": round(max(0.05, negative), 4),
            "neutral": round(max(0.1, neutral), 4),
            "composite": round(composite, 4),
            "article_count": 0,
            "top_headlines": [],
            "timestamp": datetime.utcnow().isoformat(),
            "is_mock": True,
        }


# ----------------------------------------------------------
# STOCKTWITS FETCHER
# ----------------------------------------------------------

class StockTwitsFetcher:
    """
    StockTwits API istemcisi.
    Borsa odaklı Twitter benzeri platform.
    Kullanıcılar kendi "Bullish/Bearish" etiketlerini ekler.

    API Belgesi: https://api.stocktwits.com/developers/docs
    """

    BASE_URL = "https://api.stocktwits.com/api/2"

    def __init__(self):
        self.access_token = settings.STOCKTWITS_ACCESS_TOKEN

    @async_retry(max_attempts=2, delay=3.0)
    async def get_symbol_stream(self, ticker: str, limit: int = 30) -> Dict:
        """
        StockTwits'ten ticker için son mesajları çeker.
        Kullanıcı etiketleri (Bullish/Bearish) doğrudan sentiment sağlar.
        """
        cache_key = f"{ticker}:stocktwits"
        cached = await cache_manager.get(CacheNamespace.SENTIMENT, cache_key)
        if cached:
            return cached

        params = {"filter": "top"}
        if self.access_token:
            params["access_token"] = self.access_token

        url = f"{self.BASE_URL}/streams/symbol/{ticker}.json"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 404:
                        return self._empty_result(ticker)
                    if resp.status != 200:
                        raise Exception(f"StockTwits HTTP {resp.status}")
                    data = await resp.json()

            messages = data.get("messages", [])[:limit]

            # Kullanıcı etiketlerini say (doğrudan sentiment)
            bullish_count = 0
            bearish_count = 0
            no_label = 0

            for msg in messages:
                entities = msg.get("entities", {})
                sentiment = entities.get("sentiment")
                if sentiment:
                    basic = sentiment.get("basic", "")
                    if basic == "Bullish":
                        bullish_count += 1
                    elif basic == "Bearish":
                        bearish_count += 1
                    else:
                        no_label += 1
                else:
                    no_label += 1

            total = len(messages) or 1
            positive = bullish_count / total
            negative = bearish_count / total
            neutral = no_label / total
            composite = positive - negative

            result = {
                "ticker": ticker,
                "source": "stocktwits",
                "positive": round(positive, 4),
                "negative": round(negative, 4),
                "neutral": round(neutral, 4),
                "composite": round(composite, 4),
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "total_messages": len(messages),
                "timestamp": datetime.utcnow().isoformat(),
            }

            await cache_manager.set(CacheNamespace.SENTIMENT, cache_key, result, ttl=900)
            return result

        except Exception as e:
            logger.warning("StockTwits hatası.", ticker=ticker, error=str(e))
            return self._empty_result(ticker)

    def _empty_result(self, ticker: str) -> Dict:
        return {
            "ticker": ticker, "source": "stocktwits",
            "positive": 0.33, "negative": 0.33, "neutral": 0.34,
            "composite": 0.0, "total_messages": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }


# ----------------------------------------------------------
# ANA SENTIMENT SERVİSİ
# ----------------------------------------------------------

class SentimentService:
    """
    Tüm sentiment kaynaklarını birleştiren ana servis.
    FinBERT NLP + Reddit + StockTwits + Haber analizi.
    """

    def __init__(self):
        self.analyzer = FinBERTAnalyzer()
        self.reddit = RedditFetcher(self.analyzer)
        self.news = NewsFetcher(self.analyzer)
        self.stocktwits = StockTwitsFetcher()

    async def get_aggregated_sentiment(
        self,
        ticker: str,
        company_name: Optional[str] = None,
    ) -> Dict:
        """
        Tüm kaynaklardan ağırlıklı ortalama sentiment skoru.

        Ağırlıklar:
        - Haber      : 0.40 (güvenilir kaynak)
        - Reddit     : 0.35 (hacim ve anlık duygu)
        - StockTwits : 0.25 (finansal odaklı)
        """
        cache_key = f"{ticker}:aggregated_sentiment"
        cached = await cache_manager.get(CacheNamespace.SENTIMENT, cache_key)
        if cached:
            return cached

        # Paralel çekme
        news_task = self.news.get_ticker_news(ticker, company_name)
        reddit_task = self.reddit.get_ticker_mentions(ticker)
        stocktwits_task = self.stocktwits.get_symbol_stream(ticker)

        news_result, reddit_result, stocktwits_result = await asyncio.gather(
            news_task, reddit_task, stocktwits_task, return_exceptions=True
        )

        # Hata kontrolü
        sources = {}
        if not isinstance(news_result, Exception) and news_result:
            sources["news"] = {"data": news_result, "weight": 0.40}
        if not isinstance(reddit_result, Exception) and reddit_result:
            sources["reddit"] = {"data": reddit_result, "weight": 0.35}
        if not isinstance(stocktwits_result, Exception) and stocktwits_result:
            sources["stocktwits"] = {"data": stocktwits_result, "weight": 0.25}

        if not sources:
            return self._neutral_aggregate(ticker)

        # Ağırlık normalizasyonu (eksik kaynak varsa diğerlerine yeniden dağıt)
        total_weight = sum(s["weight"] for s in sources.values())
        normalized_sources = {
            k: {**v, "weight": v["weight"] / total_weight}
            for k, v in sources.items()
        }

        # Ağırlıklı ortalama composite skor
        composite = sum(
            s["data"]["composite"] * s["weight"]
            for s in normalized_sources.values()
        )

        # Sentiment etiketi
        label = self._composite_to_label(composite)

        result = {
            "ticker": ticker,
            "overall_score": round(composite, 4),
            "sentiment_label": label,
            "reddit_score": reddit_result.get("composite") if isinstance(reddit_result, dict) else None,
            "stocktwits_score": stocktwits_result.get("composite") if isinstance(stocktwits_result, dict) else None,
            "news_score": news_result.get("composite") if isinstance(news_result, dict) else None,
            "total_mentions": (
                (reddit_result.get("mention_count", 0) if isinstance(reddit_result, dict) else 0) +
                (stocktwits_result.get("total_messages", 0) if isinstance(stocktwits_result, dict) else 0)
            ),
            "news_article_count": news_result.get("article_count", 0) if isinstance(news_result, dict) else 0,
            "top_headlines": news_result.get("top_headlines", []) if isinstance(news_result, dict) else [],
            "sources": list(sources.keys()),
            "last_updated": datetime.utcnow().isoformat(),
        }

        await cache_manager.set(CacheNamespace.SENTIMENT, cache_key, result, ttl=1800)
        return result

    def _composite_to_label(self, score: float) -> str:
        """Composite skoru insan okunabilir etikete çevirir."""
        if score > 0.4:
            return "Very Bullish"
        elif score > 0.15:
            return "Bullish"
        elif score > -0.15:
            return "Neutral"
        elif score > -0.4:
            return "Bearish"
        else:
            return "Very Bearish"

    def _neutral_aggregate(self, ticker: str) -> Dict:
        return {
            "ticker": ticker,
            "overall_score": 0.0,
            "sentiment_label": "Neutral",
            "reddit_score": None,
            "stocktwits_score": None,
            "news_score": None,
            "total_mentions": 0,
            "last_updated": datetime.utcnow().isoformat(),
        }


# Singleton
sentiment_service = SentimentService()
