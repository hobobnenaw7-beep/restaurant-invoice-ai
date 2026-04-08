"""
Rate-limited LLM request handler with retry logic and request queue.
Prevents burst API limits by spacing requests and retrying on transient failures.
Handles webhook.site rate limiting from the Emergent integration proxy.
"""
import asyncio
import time
import logging

logger = logging.getLogger("restaurant_ai")

# Configuration
MIN_REQUEST_INTERVAL = 3.0  # seconds between LLM calls (prevents proxy burst limits)
MAX_RETRIES = 2
RETRY_DELAY_BASE = 8.0  # seconds — long enough for proxy rate window to reset

# Global state
_last_request_time = 0.0
_request_lock = asyncio.Lock()
_active_requests = 0
_total_requests = 0
_total_retries = 0
_total_failures = 0


async def rate_limited_llm_call(chat, user_msg, label="llm_call"):
    """
    Send an LLM message with rate limiting and retry logic.

    - Enforces minimum interval between requests (request queue via asyncio.Lock)
    - Retries on transient errors (rate limits, 502/503, webhook.site errors)
    - Exponential backoff: 8s, 16s between retries

    Args:
        chat: LlmChat instance (already configured with model)
        user_msg: UserMessage to send
        label: descriptive label for logging

    Returns:
        Response string from the LLM

    Raises:
        Exception: after MAX_RETRIES exhausted
    """
    global _last_request_time, _active_requests, _total_requests, _total_retries, _total_failures

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        # Rate limiting: acquire lock and enforce interval
        async with _request_lock:
            now = time.time()
            elapsed = now - _last_request_time
            wait_time = MIN_REQUEST_INTERVAL - elapsed

            # On retries, add extra backoff delay
            if attempt > 0:
                retry_delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                wait_time = max(wait_time, retry_delay)
                logger.warning(f"[Retry] {label}: attempt {attempt + 1}/{MAX_RETRIES + 1}, waiting {wait_time:.0f}s")
                _total_retries += 1

            if wait_time > 0:
                await asyncio.sleep(wait_time)

            _last_request_time = time.time()
            _active_requests += 1
            _total_requests += 1

        try:
            response = await chat.send_message(user_msg)
            _active_requests -= 1
            return response

        except Exception as e:
            _active_requests -= 1
            last_error = e
            error_str = str(e).lower()

            # Check if this is a retryable error
            retryable = any(kw in error_str for kw in [
                "rate limit", "ratelimit", "429", "503", "502",
                "timeout", "timed out",
                "budget", "exceeded", "overloaded", "capacity",
                "connection", "reset", "refused",
                "webhook", "request limit", "sign up",
                "too many requests", "throttl",
            ])

            if not retryable or attempt >= MAX_RETRIES:
                _total_failures += 1
                logger.error(f"[LLM] {label}: FAILED after {attempt + 1} attempt(s): {str(e)[:200]}")
                raise

            logger.warning(f"[LLM] {label}: retryable error (attempt {attempt + 1}): {str(e)[:150]}")

    _total_failures += 1
    raise last_error


def get_llm_stats():
    """Return current LLM request statistics."""
    return {
        "active_requests": _active_requests,
        "total_requests": _total_requests,
        "total_retries": _total_retries,
        "total_failures": _total_failures,
        "min_interval_sec": MIN_REQUEST_INTERVAL,
        "max_retries": MAX_RETRIES,
    }
