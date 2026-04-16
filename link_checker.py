"""
Link checker utility for the RFX Multi-Agent system.
Adapted from https://github.com/HaoZhang615/RFX-Agents/blob/main/helper/link_checker.py

Provides functions to extract URLs from text, validate them via HTTP requests,
and summarize the results. Includes soft-404 detection.
"""

import re
import logging
import asyncio
import concurrent.futures
import aiohttp
import urllib.parse
from typing import Dict, List

logger = logging.getLogger(__name__)


async def _check_url(
    session: aiohttp.ClientSession,
    url: str,
    max_redirects: int = 5,
) -> Dict:
    """Check a URL to see if it's valid and working.

    Uses HEAD first (efficient), falls back to GET if HEAD fails.
    For 200 responses, checks content for soft-404 patterns.
    """
    try:
        # First try HEAD request
        try:
            async with session.head(
                url,
                allow_redirects=True,
                max_redirects=max_redirects,
                ssl=False,
            ) as response:
                status = response.status
                final_url = str(response.url)

                if 200 <= status < 400:
                    return {
                        "success": True,
                        "status_code": status,
                        "final_url": final_url,
                    }

                # Some servers don't support HEAD, fall back to GET
                if status in (404, 405, 403):
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=status,
                        message=f"HEAD request failed with status {status}, trying GET",
                    )

                return {
                    "success": False,
                    "status_code": status,
                    "message": f"HTTP Error: {status}",
                }

        except (aiohttp.ClientResponseError, aiohttp.ClientError):
            # Fall back to GET request if HEAD fails
            async with session.get(
                url,
                allow_redirects=True,
                max_redirects=max_redirects,
                ssl=False,
            ) as response:
                status = response.status
                final_url = str(response.url)

                if 200 <= status < 400:
                    # For 200 OK responses, check if it's actually an error page (soft 404)
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" in content_type.lower():
                        content = await response.text(encoding="utf-8", errors="ignore")

                        error_patterns = [
                            r"404 - Page not found",
                            r"<title>[^<]*(?:404|not found|error|page does not exist)[^<]*</title>",
                            r"<h1>[^<]*(?:404|not found|error|page does not exist)[^<]*</h1>",
                            r"<h2[^>]*>[^<]*(?:404|not found|error|page does not exist)[^<]*</h2>",
                            r"Sorry, the page you requested cannot be found",
                            r"The page you're looking for isn't available",
                            r"The resource you are looking for has been removed",
                            r"404 Not Found",
                            r"Page Not Found",
                            r"The page cannot be found",
                            r"This page does not exist",
                            r"We can't find the page you're looking for",
                        ]

                        for pattern in error_patterns:
                            if re.search(pattern, content, re.IGNORECASE):
                                return {
                                    "success": False,
                                    "status_code": 404,
                                    "message": "Soft 404 detected: Page appears to be an error page despite 200 status",
                                }

                    return {
                        "success": True,
                        "status_code": status,
                        "final_url": final_url,
                    }
                else:
                    return {
                        "success": False,
                        "status_code": status,
                        "message": f"HTTP Error: {status}",
                    }

    except aiohttp.ClientConnectorError as e:
        return {"success": False, "message": f"Connection error: {str(e)}"}
    except aiohttp.ClientError as e:
        return {"success": False, "message": f"Request error: {str(e)}"}
    except asyncio.TimeoutError:
        return {"success": False, "message": "Request timed out"}
    except Exception as e:
        logger.error(f"Error checking URL {url}: {str(e)}")
        return {"success": False, "message": f"Unexpected error: {str(e)}"}


def extract_urls(text: str) -> List[str]:
    """Extract URLs from a piece of text."""
    url_pattern = r"https?://[^\s\)\]\"\'\>]+"
    return re.findall(url_pattern, text)


async def _validate_urls_async(
    urls: List[str], timeout: int = 10, max_redirects: int = 5
) -> List[str]:
    """Validate a list of URLs and return results as strings."""
    results = []

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LinkValidator/1.0"},
    ) as session:
        tasks = []
        valid_urls = []

        for url in urls:
            url = url.strip()
            if not url:
                continue

            try:
                parsed_url = urllib.parse.urlparse(url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    results.append(f"INVALID: {url} - Malformed URL")
                    continue
            except Exception as e:
                results.append(f"INVALID: {url} - {str(e)}")
                continue

            valid_urls.append(url)
            tasks.append(_check_url(session, url, max_redirects))

        check_results = await asyncio.gather(*tasks, return_exceptions=True)

        for url, result in zip(valid_urls, check_results):
            if isinstance(result, Exception):
                results.append(f"INVALID: {url} - {str(result)}")
            elif result["success"]:
                results.append(f"VALID: {url} - Status {result['status_code']}")
            else:
                results.append(f"INVALID: {url} - {result['message']}")

    return results


def validate_urls_in_text(text: str) -> str:
    """Extract and validate all URLs found in the given text.

    Returns 'LINKS CORRECT' or 'LINKS INCORRECT' with details.
    Safe to call from within a running asyncio event loop (uses a thread).
    """
    urls = extract_urls(text)
    if not urls:
        return "LINKS CORRECT — No URLs found in the text."

    # Run in a separate thread to avoid nested event loop issues
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        results = pool.submit(asyncio.run, _validate_urls_async(urls)).result()

    invalid = [r for r in results if r.startswith("INVALID")]
    if invalid:
        return "LINKS INCORRECT\n" + "\n".join(results)
    return "LINKS CORRECT\n" + "\n".join(results)
