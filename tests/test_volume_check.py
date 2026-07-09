"""Volume guardrail: a batch far off the source's trailing median quarantines."""

import json

from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import BloombergRssAdapter
from sovereign_monitor.registry import Registry
from tests.conftest import FIXTURES_DIRECTORY

TINY_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Bloomberg Markets</title>
<item><title>lone headline</title><link>https://www.bloomberg.com/news/articles/lone</link>
<pubDate>Wed, 08 Jul 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_collapsed_batch_is_quarantined_as_volume_anomaly(
    registry: Registry, settings: Settings
) -> None:
    adapter = BloombergRssAdapter(registry.sources["bloomberg_rss"], settings)
    healthy = adapter.run(payload=(FIXTURES_DIRECTORY / "bloomberg_markets_news.xml").read_bytes())
    assert not healthy.quarantined and healthy.rows_in_batch >= 20

    collapsed = adapter.run(payload=TINY_FEED)
    assert collapsed.quarantined

    quarantine_root = settings.data_directory / "quarantine" / "bloomberg_rss"
    reason_files = list(quarantine_root.glob("*/reason.json"))
    assert len(reason_files) == 1
    reason = json.loads(reason_files[0].read_text(encoding="utf-8"))
    assert "volume anomaly" in reason["reason"]
