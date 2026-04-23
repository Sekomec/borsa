-- ============================================================
-- QuantEdge AI — TimescaleDB Başlangıç SQL Scripti
-- ============================================================
-- Bu script Docker başlatıldığında otomatik çalışır.
-- TimescaleDB extension ve temel yapılandırma.

-- TimescaleDB extension'ını etkinleştir
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- UUID desteği
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Metin arama desteği
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- TEMEL İNDEKSLER (tablolar SQLAlchemy tarafından oluşturulur)
-- ============================================================

-- OHLCV sorguları için bileşik indeks
-- (SQLAlchemy tablolar oluşturduktan sonra çalışır)
DO $$
BEGIN
  -- Hypertable oluşturma (yoksa)
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ohlcv_data') THEN
    PERFORM create_hypertable(
      'ohlcv_data', 'timestamp',
      if_not_exists => TRUE,
      chunk_time_interval => INTERVAL '30 days'
    );

    -- Veri sıkıştırma politikası (90 günden eski)
    PERFORM add_compression_policy(
      'ohlcv_data',
      INTERVAL '90 days',
      if_not_exists => TRUE
    );

    -- Sürekli agregasyon (günlük ortalama)
    -- Hızlı dashboard sorguları için materialized view
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'macro_indicators') THEN
    PERFORM create_hypertable(
      'macro_indicators', 'timestamp',
      if_not_exists => TRUE
    );
  END IF;
END
$$;

-- ============================================================
-- ÖRNEK VERİLER (development ortamı için)
-- ============================================================

-- Not: Bazı tablolar uygulama (SQLAlchemy) tarafından runtime'da oluşturulsa da,
-- bu init script Docker ilk açılışında çalışır. Bu yüzden seed atacağımız tabloları
-- burada güvenli şekilde (IF NOT EXISTS) oluşturuyoruz.

-- Temel hisse metadata tablosu (seed için gerekli)
CREATE TABLE IF NOT EXISTS stock_info (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  ticker       VARCHAR(20) UNIQUE NOT NULL,
  company_name VARCHAR(255) NOT NULL,
  exchange     VARCHAR(50),
  sector       VARCHAR(100),
  industry     VARCHAR(150),
  market_cap   BIGINT,
  country      VARCHAR(50),
  currency     VARCHAR(10) DEFAULT 'USD',
  created_at   TIMESTAMP DEFAULT NOW(),
  updated_at   TIMESTAMP DEFAULT NOW()
);

-- Temel hisse listesi
INSERT INTO stock_info (ticker, company_name, exchange, sector, industry, market_cap, country, currency)
VALUES
  ('AAPL',  'Apple Inc.',              'NASDAQ', 'Technology',          'Consumer Electronics',       3000000000000, 'USA', 'USD'),
  ('MSFT',  'Microsoft Corporation',   'NASDAQ', 'Technology',          'Software-Infrastructure',    2800000000000, 'USA', 'USD'),
  ('GOOGL', 'Alphabet Inc.',           'NASDAQ', 'Technology',          'Internet Content & Info',    2000000000000, 'USA', 'USD'),
  ('AMZN',  'Amazon.com Inc.',         'NASDAQ', 'Consumer Cyclical',   'Internet Retail',            1800000000000, 'USA', 'USD'),
  ('NVDA',  'NVIDIA Corporation',      'NASDAQ', 'Technology',          'Semiconductors',             2200000000000, 'USA', 'USD'),
  ('META',  'Meta Platforms Inc.',     'NASDAQ', 'Technology',          'Internet Content & Info',    1200000000000, 'USA', 'USD'),
  ('TSLA',  'Tesla Inc.',              'NASDAQ', 'Consumer Cyclical',   'Auto Manufacturers',          700000000000, 'USA', 'USD'),
  ('JPM',   'JPMorgan Chase & Co.',    'NYSE',   'Financial Services',  'Banks-Diversified',           500000000000, 'USA', 'USD'),
  ('JNJ',   'Johnson & Johnson',       'NYSE',   'Healthcare',          'Drug Manufacturers-General',  400000000000, 'USA', 'USD'),
  ('V',     'Visa Inc.',               'NYSE',   'Financial Services',  'Credit Services',             500000000000, 'USA', 'USD'),
  ('WMT',   'Walmart Inc.',            'NYSE',   'Consumer Defensive',  'Discount Stores',             500000000000, 'USA', 'USD'),
  ('XOM',   'Exxon Mobil Corporation', 'NYSE',   'Energy',              'Oil & Gas Integrated',        450000000000, 'USA', 'USD'),
  ('AMD',   'Advanced Micro Devices',  'NASDAQ', 'Technology',          'Semiconductors',              250000000000, 'USA', 'USD'),
  ('PLTR',  'Palantir Technologies',   'NYSE',   'Technology',          'Software-Application',         50000000000, 'USA', 'USD'),
  ('SPY',   'SPDR S&P 500 ETF',        'NYSE',   'ETF',                 'Large Blend',                 400000000000, 'USA', 'USD'),
  ('QQQ',   'Invesco QQQ Trust',       'NASDAQ', 'ETF',                 'Large Growth',                200000000000, 'USA', 'USD')
ON CONFLICT (ticker) DO NOTHING;

-- ============================================================
-- YARDIMCI FONKSİYONLAR
-- ============================================================

-- Hisse için en son OHLCV kaydını döndüren fonksiyon
CREATE OR REPLACE FUNCTION get_latest_price(p_ticker VARCHAR)
RETURNS TABLE (
  ticker VARCHAR,
  close_price FLOAT,
  volume BIGINT,
  ts TIMESTAMP
) AS $$
BEGIN
  RETURN QUERY
  SELECT si.ticker, od.close_price, od.volume, od.timestamp AS ts
  FROM ohlcv_data od
  JOIN stock_info si ON si.id = od.stock_id
  WHERE si.ticker = p_ticker
    AND od.timeframe = '1d'
  ORDER BY od.timestamp DESC
  LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Performans log tablosu
CREATE TABLE IF NOT EXISTS api_request_log (
  id          BIGSERIAL PRIMARY KEY,
  endpoint    VARCHAR(200),
  ticker      VARCHAR(20),
  timeframe   VARCHAR(10),
  response_ms INTEGER,
  status_code INTEGER,
  created_at  TIMESTAMP DEFAULT NOW()
);

-- Mesaj: Başlatma tamamlandı
DO $$
BEGIN
  RAISE NOTICE 'QuantEdge AI TimescaleDB başlatma tamamlandı.';
  RAISE NOTICE 'Stock info: % kayıt eklendi.', (SELECT COUNT(*) FROM stock_info);
END
$$;
