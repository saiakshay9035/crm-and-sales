import time
from unittest.mock import patch

from icp_background_worker import ICPBackgroundWorker


def test_icp_worker_status_dict():
    worker = ICPBackgroundWorker(interval_seconds=600)
    status = worker.get_status_dict()
    
    assert "running" in status
    assert "status" in status
    assert "total_discovered" in status


def test_icp_worker_lifecycle():
    worker = ICPBackgroundWorker(interval_seconds=600)
    
    def mock_loop():
        while not worker._stop_event.is_set():
            time.sleep(0.05)

    with patch.object(worker, '_run_loop', side_effect=mock_loop):
        worker.start()
        assert worker.is_running() is True
        worker.stop()
        time.sleep(0.1)
        assert worker.is_running() is False
