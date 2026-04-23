#!/usr/bin/env python3
"""
QuantEdge AI — Model Eğitimi Scripti
Kullanım: python scripts/train_models.py --tickers AAPL MSFT --timeframes 1d 1w
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


async def main():
    parser = argparse.ArgumentParser(description="QuantEdge Model Eğitimi")
    parser.add_argument('--tickers',    nargs='+', default=['AAPL', 'MSFT', 'NVDA'])
    parser.add_argument('--timeframes', nargs='+', default=['1d', '1w'])
    parser.add_argument('--optimize',   action='store_true', default=False)
    parser.add_argument('--fast',       action='store_true', default=False)
    parser.add_argument('--dry-run',    action='store_true', default=False)
    args = parser.parse_args()

    print("=" * 60)
    print("QuantEdge AI — Model Eğitimi")
    print("=" * 60)
    print(f"Tickers    : {', '.join(args.tickers)}")
    print(f"Timeframes : {', '.join(args.timeframes)}")
    print(f"Optimize   : {args.optimize}")
    print(f"Fast       : {args.fast}")
    print()

    try:
        from app.services.data_fetchers.market_data import market_data_service
        from app.services.data_fetchers.sentiment import sentiment_service
        from app.services.data_fetchers.fundamental import fundamental_service
        from app.services.data_fetchers.macro import macro_service
        from app.services.analysis.technical import technical_service
        from app.services.ml.training import model_trainer
        from app.core.cache import cache_manager
    except ImportError as e:
        print(f"Import hatasi: {e}\nBackend dizininde calistirdiginizdan emin olun.")
        sys.exit(1)

    try:
        await cache_manager.connect()
        print("Redis baglantisi kuruldu.")
    except Exception:
        print("Redis baglantisi kurulamadi. Cache devre disi.")

    total_trained = total_failed = 0

    for ticker in args.tickers:
        print(f"\n--- {ticker} ---")
        ohlcv = await market_data_service.get_ohlcv(ticker, '1d', 500, use_cache=False)

        if not ohlcv or len(ohlcv) < 100:
            print(f"  Yetersiz veri ({len(ohlcv) if ohlcv else 0} bar). Atlaniyor.")
            total_failed += 1
            continue

        print(f"  {len(ohlcv)} bar OHLCV alindi.")
        if args.dry_run:
            print(f"  [dry-run] Egitim atlandi.")
            continue

        ta       = technical_service.analyze(ohlcv, '1d')
        macro    = None
        sentiment = fundamental = None

        try:
            macro = await macro_service.get_full_macro_context()
        except Exception:
            pass

        if not args.fast:
            try:
                sentiment = await sentiment_service.get_aggregated_sentiment(ticker)
            except Exception:
                pass
            try:
                fundamental = await fundamental_service.get_comprehensive_fundamental(ticker)
            except Exception:
                pass

        for tf in args.timeframes:
            print(f"  {tf} egitiliyor...", end=" ", flush=True)
            try:
                result = model_trainer.train_all_models(
                    ticker=ticker, timeframe=tf,
                    ohlcv=ohlcv, technical=ta,
                    sentiment=sentiment, fundamental=fundamental, macro=macro,
                    optimize_hyperparams=args.optimize,
                )
                if result.get("status") == "success":
                    print("OK")
                    total_trained += 1
                else:
                    print(f"HATA: {result.get('error','')[:60]}")
                    total_failed += 1
            except Exception as e:
                print(f"HATA: {str(e)[:60]}")
                total_failed += 1

        await asyncio.sleep(2)

    print(f"\n{'='*60}")
    print(f"Basarili: {total_trained}  |  Basarisiz: {total_failed}")
    if total_trained > 0:
        print("Modeller hazir. API'yi baslatabilirsiniz.")
    else:
        print("Hic model egitilemedi. API rule-based fallback kullanacak.")

    await cache_manager.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
