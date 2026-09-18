import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.database import Base  # noqa: E402
from models import SecurityEvent  # noqa: E402
from services.security_service import ingest_event  # noqa: E402


class SecurityEventIngestTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()

    def payload(self, event_id, device_code, sources, occurred_at):
        return SimpleNamespace(
            event_id=event_id,
            device_code=device_code,
            node_code='EDGE-FENCE',
            event_type='line_crossing',
            zone='周界宿舍区',
            confidence=0.92,
            sources=sources,
            local_actions=['video_snapshot'],
            local_latency_ms=35,
            message=None,
            occurred_at=occurred_at,
        )

    def test_replayed_merged_event_is_idempotent(self):
        now = datetime.now()

        first = ingest_event(
            self.db,
            self.payload('evt-source-video', 'CAM-FENCE-01', ['video'], now),
        )
        second = ingest_event(
            self.db,
            self.payload('evt-source-vibration', 'VIB-FENCE-01', ['vibration'], now + timedelta(seconds=2)),
        )
        replay = ingest_event(
            self.db,
            self.payload('evt-source-vibration', 'VIB-FENCE-01', ['vibration'], now + timedelta(seconds=4)),
        )

        event = self.db.query(SecurityEvent).one()
        self.assertEqual(first['action'], 'created')
        self.assertEqual(second['action'], 'merged')
        self.assertEqual(replay['action'], 'duplicate')
        self.assertEqual(event.merge_count, 2)
        self.assertEqual(event.to_dict()['merged_event_ids'], ['evt-source-vibration'])

    def test_dirty_json_fields_fall_back_to_empty_lists(self):
        event = SecurityEvent(
            event_id='evt-dirty-json',
            event_type='line_crossing',
            level=2,
            zone='周界宿舍区',
            sources='not-json',
            local_actions='{}',
            pushed_channels='broken',
            merged_event_ids='null',
            occurred_at=datetime.now(),
        )

        data = event.to_dict()

        self.assertEqual(data['sources'], [])
        self.assertEqual(data['local_actions'], [])
        self.assertEqual(data['pushed_channels'], [])
        self.assertEqual(data['merged_event_ids'], [])


if __name__ == '__main__':
    unittest.main()
