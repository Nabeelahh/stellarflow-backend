#!/usr/bin/env python3
"""
Database Maintenance Cleanup Job
================================
Automatically deletes tracking metrics older than 14 days to keep database lean and fast.

This script can be run as a cron job or scheduled task to periodically clean up old telemetry data.

Cron configuration example:
  # Run cleanup job daily at 2 AM
  0 2 * * * /usr/bin/python3 /path/to/src/database/cleanup_job.py

Environment Variables Required:
  - DATABASE_URL: PostgreSQL connection string (e.g., postgresql://user:pass@host:port/dbname)
  - LOG_LEVEL: (optional) Logging level - DEBUG, INFO, WARNING, ERROR (default: INFO)
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple
import psycopg2
from psycopg2 import sql, Error

# Configure logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('database_cleanup.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class DatabaseCleanupJob:
    """Handles database maintenance and cleanup operations."""

    RETENTION_DAYS = 14
    BATCH_SIZE = 10000  # Delete in batches to avoid locking tables

    def __init__(self, database_url: str):
        """
        Initialize the cleanup job.

        Args:
            database_url: PostgreSQL connection string
        """
        self.database_url = database_url
        self.connection = None
        self.stats = {
            'price_history_deleted': 0,
            'error_logs_deleted': 0,
            'expired_multisig_deleted': 0,
            'duration_seconds': 0,
            'start_time': datetime.now(),
        }

    def connect(self) -> bool:
        """
        Establish database connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.connection = psycopg2.connect(self.database_url)
            logger.info("Successfully connected to database")
            return True
        except Error as e:
            logger.error(f"Failed to connect to database: {e}")
            return False

    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

    def cleanup_price_history(self) -> int:
        """
        Delete PriceHistory records older than retention period.

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now() - timedelta(days=self.RETENTION_DAYS)
        deleted_count = 0

        try:
            cursor = self.connection.cursor()

            # Delete in batches to avoid long locks
            while True:
                delete_query = sql.SQL("""
                    DELETE FROM "PriceHistory"
                    WHERE "createdAt" < %s
                    LIMIT %s
                """)

                cursor.execute(delete_query, (cutoff_date, self.BATCH_SIZE))
                batch_deleted = cursor.rowcount
                deleted_count += batch_deleted

                if batch_deleted == 0:
                    break

                self.connection.commit()
                logger.debug(f"Deleted {batch_deleted} PriceHistory records")

            logger.info(
                f"Cleanup PriceHistory: Deleted {deleted_count} records older than {cutoff_date.date()}"
            )
            return deleted_count

        except Error as e:
            self.connection.rollback()
            logger.error(f"Error cleaning up PriceHistory: {e}")
            return 0
        finally:
            cursor.close()

    def cleanup_error_logs(self) -> int:
        """
        Delete ErrorLog records older than retention period.

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now() - timedelta(days=self.RETENTION_DAYS)
        deleted_count = 0

        try:
            cursor = self.connection.cursor()

            # Delete in batches to avoid long locks
            while True:
                delete_query = sql.SQL("""
                    DELETE FROM "ErrorLog"
                    WHERE "occurredAt" < %s
                    LIMIT %s
                """)

                cursor.execute(delete_query, (cutoff_date, self.BATCH_SIZE))
                batch_deleted = cursor.rowcount
                deleted_count += batch_deleted

                if batch_deleted == 0:
                    break

                self.connection.commit()
                logger.debug(f"Deleted {batch_deleted} ErrorLog records")

            logger.info(
                f"Cleanup ErrorLog: Deleted {deleted_count} records older than {cutoff_date.date()}"
            )
            return deleted_count

        except Error as e:
            self.connection.rollback()
            logger.error(f"Error cleaning up ErrorLog: {e}")
            return 0
        finally:
            cursor.close()

    def cleanup_expired_multisig(self) -> int:
        """
        Delete expired MultiSigPrice records and their associated signatures.

        Removes:
        - Records with status 'EXPIRED' older than retention period
        - Records with status 'REJECTED' older than retention period

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now() - timedelta(days=self.RETENTION_DAYS)
        deleted_count = 0

        try:
            cursor = self.connection.cursor()

            # Delete in batches to avoid long locks
            # Cascade delete will remove associated signatures
            while True:
                delete_query = sql.SQL("""
                    DELETE FROM "MultiSigPrice"
                    WHERE (
                        ("status" = 'EXPIRED' OR "status" = 'REJECTED')
                        AND "createdAt" < %s
                    )
                    LIMIT %s
                """)

                cursor.execute(delete_query, (cutoff_date, self.BATCH_SIZE))
                batch_deleted = cursor.rowcount
                deleted_count += batch_deleted

                if batch_deleted == 0:
                    break

                self.connection.commit()
                logger.debug(f"Deleted {batch_deleted} MultiSigPrice records")

            logger.info(
                f"Cleanup MultiSigPrice: Deleted {deleted_count} expired/rejected records older than {cutoff_date.date()}"
            )
            return deleted_count

        except Error as e:
            self.connection.rollback()
            logger.error(f"Error cleaning up MultiSigPrice: {e}")
            return 0
        finally:
            cursor.close()

    def cleanup_stale_multisig_signatures(self) -> int:
        """
        Delete orphaned MultiSigSignature records (if any exist after cascade deletes).

        Returns:
            Number of records deleted
        """
        deleted_count = 0

        try:
            cursor = self.connection.cursor()

            # Clean up any orphaned signatures
            delete_query = sql.SQL("""
                DELETE FROM "MultiSigSignature"
                WHERE "multiSigPriceId" NOT IN (
                    SELECT id FROM "MultiSigPrice"
                )
            """)

            cursor.execute(delete_query)
            deleted_count = cursor.rowcount
            self.connection.commit()

            if deleted_count > 0:
                logger.info(f"Cleanup MultiSigSignature: Deleted {deleted_count} orphaned records")

            return deleted_count

        except Error as e:
            self.connection.rollback()
            logger.error(f"Error cleaning up orphaned signatures: {e}")
            return 0
        finally:
            cursor.close()

    def get_database_stats(self) -> Dict[str, int]:
        """
        Get current record counts for monitored tables.

        Returns:
            Dictionary with table names and record counts
        """
        stats = {}
        tables = ['PriceHistory', 'ErrorLog', 'MultiSigPrice', 'MultiSigSignature']

        try:
            cursor = self.connection.cursor()

            for table in tables:
                count_query = sql.SQL("SELECT COUNT(*) FROM {}").format(
                    sql.Identifier(table)
                )
                cursor.execute(count_query)
                count = cursor.fetchone()[0]
                stats[table] = count

            cursor.close()
            return stats

        except Error as e:
            logger.error(f"Error fetching database stats: {e}")
            return {}

    def run(self) -> bool:
        """
        Execute the complete cleanup job.

        Returns:
            True if cleanup completed successfully, False otherwise
        """
        try:
            logger.info("=" * 60)
            logger.info("Starting database cleanup job")
            logger.info(f"Retention period: {self.RETENTION_DAYS} days")

            # Log pre-cleanup stats
            pre_stats = self.get_database_stats()
            logger.info("Pre-cleanup record counts:")
            for table, count in pre_stats.items():
                logger.info(f"  {table}: {count:,} records")

            # Run cleanup operations
            self.stats['price_history_deleted'] = self.cleanup_price_history()
            self.stats['error_logs_deleted'] = self.cleanup_error_logs()
            self.stats['expired_multisig_deleted'] = self.cleanup_expired_multisig()
            self.cleanup_stale_multisig_signatures()

            # Log post-cleanup stats
            post_stats = self.get_database_stats()
            logger.info("Post-cleanup record counts:")
            for table, count in post_stats.items():
                logger.info(f"  {table}: {count:,} records")

            # Calculate duration
            duration = datetime.now() - self.stats['start_time']
            self.stats['duration_seconds'] = duration.total_seconds()

            # Log cleanup summary
            logger.info("=" * 60)
            logger.info("Cleanup job completed successfully")
            logger.info(f"Total records deleted: {sum([self.stats['price_history_deleted'], self.stats['error_logs_deleted'], self.stats['expired_multisig_deleted']])}")
            logger.info(f"Duration: {self.stats['duration_seconds']:.2f} seconds")
            logger.info("=" * 60)

            return True

        except Exception as e:
            logger.error(f"Unexpected error during cleanup: {e}")
            return False

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


def main():
    """Main entry point for the cleanup job."""
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        logger.error("DATABASE_URL environment variable is not set")
        sys.exit(1)

    try:
        with DatabaseCleanupJob(database_url) as cleanup_job:
            success = cleanup_job.run()
            sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
