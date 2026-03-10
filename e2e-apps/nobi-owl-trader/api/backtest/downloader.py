import pandas as pd
import time
from datetime import datetime
from typing import List, Optional
from api.database import get_db_connection
from api.trading_engine import TradingEngine
from api.logger import nobi_logger

class DataDownloader:
    """
    Downloads historical OHLCV data from the exchange and saves it to SQLite.
    Checks local DB first to avoid redundant API calls.
    """
    def __init__(self, engine: TradingEngine):
        self.engine = engine
        self.conn = get_db_connection()

    def get_local_range(self, symbol: str, timeframe: str) -> Optional[tuple]:
        """Returns (min_ts, max_ts) of data we already have"""
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv_data WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe)
        ).fetchone()
        
        if row and row[0] is not None:
            return (row[0], row[1])
        return None

    def download_range(self, symbol: str, timeframe: str, start_date: datetime, limit: int = 1000):
        """
        Downloads data from start_date forward.
        """
        return self.download_range_with_end(symbol, timeframe, start_date, None, limit)

    def _timeframe_to_ms(self, timeframe: str) -> int:
        if not timeframe:
            return 0
        unit = timeframe[-1]
        try:
            value = int(timeframe[:-1])
        except ValueError:
            return 0
        if unit == "m":
            return value * 60 * 1000
        if unit == "h":
            return value * 60 * 60 * 1000
        if unit == "d":
            return value * 24 * 60 * 60 * 1000
        if unit == "w":
            return value * 7 * 24 * 60 * 60 * 1000
        return 0

    def download_range_with_end(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: Optional[datetime],
        limit: int = 1000,
        max_batches: int = 100,
    ) -> int:
        """
        Download data from start_date forward, paginating until end_date or max_batches.
        """
        since = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000) if end_date else None
        tf_ms = self._timeframe_to_ms(timeframe)
        batches = 0
        total_rows = 0
        last_ts = None

        nobi_logger.info(
            f"Downloading historical data for {symbol} {timeframe} starting from {start_date}"
        )

        try:
            while batches < max_batches and (end_ms is None or since <= end_ms):
                ohlcv = self.engine._api_call_with_retry(
                    self.engine.exchange.fetch_ohlcv,
                    symbol,
                    timeframe,
                    since=since,
                    limit=limit,
                )
                if not ohlcv:
                    break

                cursor = self.conn.cursor()
                batch_count = 0
                for row in ohlcv:
                    try:
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO ohlcv_data (symbol, timeframe, timestamp, open, high, low, close, volume)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (symbol, timeframe, row[0], row[1], row[2], row[3], row[4], row[5]),
                        )
                        batch_count += 1
                    except Exception:
                        continue

                self.conn.commit()
                total_rows += batch_count
                last_ts = ohlcv[-1][0]
                batches += 1

                if last_ts is None:
                    break
                if since >= last_ts:
                    break

                since = last_ts + (tf_ms if tf_ms else 1)

            nobi_logger.info(f"Saved {total_rows} new candles for {symbol}")
            return total_rows

        except Exception as e:
            nobi_logger.error(f"Download failed: {e}")
            return total_rows

    def sync_data(self, symbol: str, timeframe: str, days: int = 30):
        """
        Ensures we have the last X days of data locally.
        """
        start_date = datetime.now() - pd.Timedelta(days=days)
        end_date = datetime.now()

        # Estimate batches needed and cap to avoid runaway
        tf_ms = self._timeframe_to_ms(timeframe) or 1
        expected = int((end_date.timestamp() - start_date.timestamp()) * 1000 / tf_ms)
        max_batches = min(200, max(5, int(expected / 1000) + 2))

        self.download_range_with_end(
            symbol,
            timeframe,
            start_date,
            end_date,
            limit=1000,
            max_batches=max_batches,
        )

    def get_data_as_df(self, symbol: str, timeframe: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        """Retrieves local data as a Pandas DataFrame for the backtester"""
        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)
        
        query = """
            SELECT * FROM ohlcv_data 
            WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, self.conn, params=(symbol, timeframe, start_ts, end_ts))
        if not df.empty:
            df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
