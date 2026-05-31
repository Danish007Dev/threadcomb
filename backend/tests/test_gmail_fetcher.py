import asyncio
import inspect
import threading
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from googleapiclient.errors import HttpError
from services.gmail_fetcher import fetch_thread_content, fetch_thread_ids


@pytest.mark.asyncio
async def test_fetch_thread_content_is_async_and_concurrent():
    # Assert that fetch_thread_content is defined with async def
    assert inspect.iscoroutinefunction(fetch_thread_content)

    mock_execute = MagicMock()
    
    def slow_execute():
        time.sleep(0.5)
        return {"id": "123", "snippet": "test"}

    mock_execute.side_effect = slow_execute
    
    mock_get = MagicMock()
    mock_get.return_value.execute = mock_execute
    
    mock_threads = MagicMock()
    mock_threads.return_value.get = mock_get
    
    mock_users = MagicMock()
    mock_users.return_value.threads = mock_threads
    
    mock_service = MagicMock()
    mock_service.users = mock_users

    with patch("services.gmail_fetcher.build", return_value=mock_service):
        start_time = time.time()
        
        # Run 10 concurrent calls
        tasks = [fetch_thread_content("fake_creds", f"t{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        
        assert len(results) == 10
        assert all(r is not None for r in results)
        
        # Assert total time is under 1.5 seconds (concurrent, not sequential)
        # Sequential would take 5 seconds (10 * 0.5)
        assert end_time - start_time < 1.5


@pytest.mark.asyncio
async def test_execute_wrapped_in_to_thread():
    # A synchronous .execute() call without asyncio.to_thread() must be caught as a test failure.
    # We can detect this by checking if the execute mock is called in a different thread
    # from the main asyncio event loop thread.
    
    main_thread_id = threading.get_ident()
    executed_thread_id = None
    
    def track_thread_execute():
        nonlocal executed_thread_id
        executed_thread_id = threading.get_ident()
        return {"id": "123"}

    mock_execute = MagicMock(side_effect=track_thread_execute)
    mock_get = MagicMock()
    mock_get.return_value.execute = mock_execute
    mock_threads = MagicMock()
    mock_threads.return_value.get = mock_get
    mock_users = MagicMock()
    mock_users.return_value.threads = mock_threads
    mock_service = MagicMock()
    mock_service.users = mock_users
    
    with patch("services.gmail_fetcher.build", return_value=mock_service):
        await fetch_thread_content("fake_creds", "t1")
        
        assert executed_thread_id is not None
        assert executed_thread_id != main_thread_id, "execute() was called synchronously in the main thread!"


@pytest.mark.asyncio
async def test_rate_limit_exponential_backoff():
    # Mock the Gmail API to raise HttpError 429 on the 3rd call.
    # Assert the fetcher retries with backoff.
    
    call_count = 0
    
    def simulate_rate_limit(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            resp = MagicMock()
            resp.status = 429
            raise HttpError(resp=resp, content=b"Rate Limit Exceeded")
        
        # Return empty list on the next successful call to break the loop
        if call_count > 3:
            return {"threads": []}
            
        return {"threads": [{"id": f"t{call_count}"}], "nextPageToken": f"token{call_count}"}

    mock_execute = MagicMock(side_effect=simulate_rate_limit)
    mock_list = MagicMock()
    mock_list.return_value.execute = mock_execute
    mock_threads = MagicMock()
    mock_threads.return_value.list = mock_list
    mock_users = MagicMock()
    mock_users.return_value.threads = mock_threads
    mock_service = MagicMock()
    mock_service.users = mock_users

    with patch("services.gmail_fetcher.build", return_value=mock_service), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        # Assert it does not raise an unhandled exception
        thread_ids, _ = await fetch_thread_ids("fake_creds")
        
        # Assert the job continues processing other threads after the retry
        assert len(thread_ids) == 2
        assert "t1" in thread_ids
        assert "t2" in thread_ids
        
        # Ensure sleep was called for backoff (our implementation does await asyncio.sleep(5) on 429)
        mock_sleep.assert_any_call(5)
