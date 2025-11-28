"""
Vendor Index Scheduler

Background scheduler for refreshing the vendor documentation index.

Runs periodic crawls to keep the index up-to-date without blocking
the main application.
"""

import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import json

from .storage import VendorDocumentStorage
from .crawler import VendorCrawler
from rag.manufacturer_domains import get_manufacturer_domains

logger = logging.getLogger(__name__)


class VendorIndexScheduler:
    """
    Scheduler for periodic vendor index refreshes.

    Runs background crawls to keep documentation index current.
    """

    def __init__(
        self,
        storage: VendorDocumentStorage,
        refresh_interval_days: int = 7
    ):
        """
        Initialize scheduler

        Args:
            storage: VendorDocumentStorage instance
            refresh_interval_days: Days between full index refreshes (default: 7)
        """
        self.storage = storage
        self.crawler = VendorCrawler(storage)
        self.refresh_interval = timedelta(days=refresh_interval_days)

        # Scheduler state file
        self.state_file = Path.home() / "homesight" / "vendor_index_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Load state (last crawl times)
        self.state = self._load_state()

        # Background task
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def _load_state(self) -> dict:
        """Load scheduler state from file"""
        if not self.state_file.exists():
            return {"last_crawl": {}, "next_crawl": {}}

        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load scheduler state: {e}")
            return {"last_crawl": {}, "next_crawl": {}}

    def _save_state(self):
        """Save scheduler state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save scheduler state: {e}")

    async def start(self):
        """Start the background scheduler"""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Vendor index scheduler started (refresh every {self.refresh_interval.days} days)")

    async def stop(self):
        """Stop the background scheduler"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Vendor index scheduler stopped")

    async def _run_loop(self):
        """Main scheduler loop"""
        while self._running:
            try:
                # Check which manufacturers need refreshing
                manufacturers = await self._get_manufacturers_to_refresh()

                for manufacturer in manufacturers:
                    if not self._running:
                        break

                    try:
                        await self._refresh_manufacturer(manufacturer)
                    except Exception as e:
                        logger.error(f"Error refreshing {manufacturer}: {e}")

                # Sleep for 1 hour before checking again
                await asyncio.sleep(3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(300)  # 5 minutes on error

    async def _get_manufacturers_to_refresh(self) -> List[str]:
        """Get list of manufacturers that need refreshing"""
        manufacturers = []
        now = datetime.now()

        # Get all manufacturers from the index
        all_manufacturers = self.storage.get_all_manufacturers()

        for mfr in all_manufacturers:
            last_crawl = self.state["last_crawl"].get(mfr)

            if not last_crawl:
                # Never crawled, add to list
                manufacturers.append(mfr)
            else:
                # Check if refresh interval has passed
                last_crawl_dt = datetime.fromisoformat(last_crawl)
                if now - last_crawl_dt > self.refresh_interval:
                    manufacturers.append(mfr)

        return manufacturers

    async def _refresh_manufacturer(self, manufacturer: str):
        """Refresh documentation index for a manufacturer"""
        logger.info(f"Refreshing documentation index for {manufacturer}")

        try:
            # Get domains for manufacturer
            domains = get_manufacturer_domains(manufacturer)

            if not domains:
                logger.warning(f"No domains found for {manufacturer}")
                return

            # Convert domains to seed URLs
            seed_urls = []
            for domain in domains[:5]:  # Limit to top 5 domains
                if not domain.startswith("http"):
                    seed_urls.append(f"https://{domain}")
                else:
                    seed_urls.append(domain)

            # Crawl manufacturer domains
            discovered = await self.crawler.crawl_manufacturer(manufacturer, seed_urls)

            # Update state
            self.state["last_crawl"][manufacturer] = datetime.now().isoformat()
            self._save_state()

            logger.info(f"Refreshed {manufacturer}: discovered {discovered} documents")

        except Exception as e:
            logger.error(f"Failed to refresh {manufacturer}: {e}")

    async def crawl_manufacturer_now(self, manufacturer: str) -> int:
        """
        Immediately crawl a manufacturer (on-demand).

        Args:
            manufacturer: Manufacturer name

        Returns:
            Number of documents discovered
        """
        logger.info(f"On-demand crawl for {manufacturer}")

        # Get domains
        domains = get_manufacturer_domains(manufacturer)

        if not domains:
            logger.warning(f"No domains found for {manufacturer}")
            return 0

        # Convert to seed URLs
        seed_urls = []
        for domain in domains[:5]:
            if not domain.startswith("http"):
                seed_urls.append(f"https://{domain}")
            else:
                seed_urls.append(domain)

        # Crawl
        discovered = await self.crawler.crawl_manufacturer(manufacturer, seed_urls)

        # Update state
        self.state["last_crawl"][manufacturer] = datetime.now().isoformat()
        self._save_state()

        return discovered


# Global scheduler instance
_scheduler: Optional[VendorIndexScheduler] = None


def get_scheduler(storage: Optional[VendorDocumentStorage] = None) -> VendorIndexScheduler:
    """Get or create global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        if storage is None:
            storage = VendorDocumentStorage()
        _scheduler = VendorIndexScheduler(storage)
    return _scheduler


async def start_background_indexer():
    """Start the background indexer (call at app startup)"""
    scheduler = get_scheduler()
    await scheduler.start()
    logger.info("Background vendor indexer started")


async def stop_background_indexer():
    """Stop the background indexer (call at app shutdown)"""
    scheduler = get_scheduler()
    await scheduler.stop()
    logger.info("Background vendor indexer stopped")
