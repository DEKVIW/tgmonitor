from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import aiohttp

from .cache import LINK_RESULT_CACHE, should_cache_status
from .constants import DEFAULT_REQUEST_HEADERS, UNKNOWN_PLATFORM
from .platforms import get_platform_limits
from .history import LinkCheckHistoryProvider
from .parser import canonical_target_key, detect_platform_from_url, is_http_url, normalize_candidate_url
from .registry import CheckerRegistry
from .resolver import LinkResolver
from .result import (
    LinkCheckResult,
    LinkTarget,
    REASON_EXCEPTION,
    REASON_FORMAT,
    REASON_HTTP,
    REASON_NETWORK,
    REASON_TIMEOUT,
    RETRYABLE_STATUSES,
)


class LinkCheckStopped(RuntimeError):
    """Raised when a running link check task is asked to stop."""


class LinkValidator:
    def __init__(self, *, timeout: float = 15.0):
        self.default_timeout = timeout
        self.resolver = LinkResolver()
        self.registry = CheckerRegistry(timeout=timeout)
        self.result_cache = LINK_RESULT_CACHE
        self.history_provider = LinkCheckHistoryProvider()
        self.error_counts: Dict[str, int] = {}
        self.max_errors_per_netdisk = 10
        self.max_retries = 2
        self.retry_delay = 1.5
        self.retryable_errors = [REASON_TIMEOUT, REASON_NETWORK, REASON_HTTP, REASON_EXCEPTION]
        self.non_retryable_errors = [REASON_FORMAT]

    def validate_url_format(self, url: str) -> bool:
        normalized = normalize_candidate_url(url)
        return bool(normalized and is_http_url(normalized))

    def get_netdisk_type(self, url: str) -> str:
        direct_type = detect_platform_from_url(url)
        if direct_type != UNKNOWN_PLATFORM:
            return direct_type
        return self.resolver.guess_platform(url)

    def get_netdisk_limits(self, netdisk_type: str) -> Dict:
        return get_platform_limits(netdisk_type)

    def is_retryable_error(self, result: Dict) -> bool:
        return (
            result.get("status") in RETRYABLE_STATUSES
            or result.get("reason") in self.retryable_errors
        )

    async def _should_stop(self, should_stop: Optional[Callable[[], bool | Awaitable[bool]]]) -> bool:
        if should_stop is None:
            return False
        value = should_stop()
        if inspect.isawaitable(value):
            value = await value
        return bool(value)

    @staticmethod
    def _cancel_pending_tasks(tasks: List[asyncio.Task]) -> None:
        for task in tasks:
            if not task.done():
                task.cancel()

    def _clone_result_for_url(
        self,
        result: LinkCheckResult,
        *,
        url: str,
        resolved_url: Optional[str] = None,
        netdisk_type: Optional[str] = None,
    ) -> Dict:
        cloned = result.clone_for_input(url)
        if resolved_url:
            cloned.resolved_url = resolved_url
        if netdisk_type and netdisk_type != UNKNOWN_PLATFORM:
            cloned.netdisk_type = netdisk_type
        return cloned.to_dict()

    def _build_target_cache_keys(self, target: LinkTarget) -> List[str]:
        keys = [
            canonical_target_key(target.original_url),
            canonical_target_key(target.resolved_url, fallback=target.original_url),
        ]
        return [key for key in dict.fromkeys(keys) if key]

    def _store_result_in_cache(self, target: LinkTarget, result: LinkCheckResult) -> None:
        self.result_cache.set(self._build_target_cache_keys(target), result)

    def _get_cached_result_for_keys(self, keys: List[str]) -> Optional[LinkCheckResult]:
        for key in keys:
            cached_result = self.result_cache.get(key)
            if cached_result is not None:
                return cached_result
        return None

    def _get_history_results(self, urls: List[str]) -> Dict[str, LinkCheckResult]:
        raw_history_results = self.history_provider.get_recent_results(urls)
        history_results = {
            history_url: history_result
            for history_url, history_result in raw_history_results.items()
            if should_cache_status(history_result.status)
        }
        for history_url, history_result in history_results.items():
            self.result_cache.set([history_url], history_result)
        return history_results

    async def _create_session(self, timeout: float) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            headers=DEFAULT_REQUEST_HEADERS,
            timeout=aiohttp.ClientTimeout(total=timeout),
        )

    async def _prepare_target(
        self,
        original_url: str,
        http_session: aiohttp.ClientSession,
    ) -> LinkTarget:
        normalized = normalize_candidate_url(original_url)
        if not normalized or not is_http_url(normalized):
            return LinkTarget(
                original_url=original_url,
                resolved_url="",
                netdisk_type=UNKNOWN_PLATFORM,
            )

        resolved_url = await self.resolver.resolve(normalized, http_session)
        netdisk_type = detect_platform_from_url(resolved_url)
        if netdisk_type == UNKNOWN_PLATFORM:
            netdisk_type = self.resolver.guess_platform(normalized)

        return LinkTarget(
            original_url=normalized,
            resolved_url=resolved_url or normalized,
            netdisk_type=netdisk_type,
        )

    async def _execute_with_retry(
        self,
        target: LinkTarget,
        checker,
        http_session: aiohttp.ClientSession,
    ) -> LinkCheckResult:
        last_result: Optional[LinkCheckResult] = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await checker.check(target, http_session)
            except Exception as exc:
                return checker.uncertain_result(
                    target,
                    reason=REASON_EXCEPTION,
                    error=f"{type(exc).__name__}: {exc}",
                )
            last_result = result
            if result.status not in RETRYABLE_STATUSES or attempt >= self.max_retries:
                return result
            await asyncio.sleep(self.retry_delay * (attempt + 1))

        return last_result or checker.format_error_result(target, error="Unexpected retry state")

    async def check_single_link(self, url: str, timeout: int = 15) -> Dict:
        registry = self.registry if timeout == self.default_timeout else CheckerRegistry(timeout=timeout)
        normalized_url = normalize_candidate_url(url) or (url or "").strip()
        if normalized_url:
            cached_result = self._get_cached_result_for_keys([normalized_url])
            if cached_result is not None:
                return self._clone_result_for_url(cached_result, url=normalized_url)

            history_results = self._get_history_results([normalized_url])
            history_result = history_results.get(normalized_url)
            if history_result is not None:
                return self._clone_result_for_url(history_result, url=normalized_url)

        async with await self._create_session(float(timeout)) as http_session:
            target = await self._prepare_target(url, http_session)
            if not target.resolved_url:
                checker = registry.get_checker(target.netdisk_type)
                result = checker.format_error_result(
                    target,
                    error="URL format is invalid",
                )
                self._store_result_in_cache(target, result)
                return result.to_dict()

            target_cache_keys = self._build_target_cache_keys(target)
            cached_result = self._get_cached_result_for_keys(target_cache_keys)
            if cached_result is not None:
                self.result_cache.set(target_cache_keys, cached_result)
                return self._clone_result_for_url(
                    cached_result,
                    url=target.original_url,
                    resolved_url=target.resolved_url,
                    netdisk_type=target.netdisk_type,
                )

            history_results = self._get_history_results(target_cache_keys)
            history_result = None
            for cache_key in target_cache_keys:
                history_result = history_results.get(cache_key)
                if history_result is not None:
                    break
            if history_result is not None:
                self.result_cache.set(target_cache_keys, history_result)
                return self._clone_result_for_url(
                    history_result,
                    url=target.original_url,
                    resolved_url=target.resolved_url,
                    netdisk_type=target.netdisk_type,
                )

            checker = registry.get_checker(target.netdisk_type)
            result = await self._execute_with_retry(target, checker, http_session)
            self._store_result_in_cache(target, result)
            self.error_counts[target.netdisk_type] = (
                0 if result.is_valid else self.error_counts.get(target.netdisk_type, 0) + 1
            )
            return result.to_dict()

    async def retry_failed_links(self, failed_results: List[Dict]) -> List[Dict]:
        if not failed_results:
            return []

        retry_results: List[Dict] = []
        for result in failed_results:
            if not self.is_retryable_error(result):
                retry_results.append(result)
                continue
            retry_results.append(await self.check_single_link(result["url"]))
        return retry_results

    async def retry_failed_links_with_identity(self, failed_results: List[Dict]) -> List[Dict]:
        if not failed_results:
            return []

        retry_results: List[Dict] = []
        for result in failed_results:
            if not self.is_retryable_error(result):
                retry_results.append(result)
                continue
            new_result = await self.check_single_link(result["url"])
            new_result["_input_index"] = result.get("_input_index")
            retry_results.append(new_result)
        return retry_results

    async def _resolve_targets(
        self,
        urls: List[str],
        http_session: aiohttp.ClientSession,
        *,
        max_concurrent: int,
        should_stop: Optional[Callable[[], bool | Awaitable[bool]]] = None,
    ) -> List[LinkTarget]:
        if not urls:
            return []

        normalized_urls = [normalize_candidate_url(url) or (url or "").strip() for url in urls]
        unique_inputs = list(dict.fromkeys(normalized_urls))
        input_targets: Dict[str, LinkTarget] = {}
        semaphore = asyncio.Semaphore(max(1, max_concurrent))

        async def resolve_one(input_url: str) -> Tuple[str, LinkTarget]:
            async with semaphore:
                target = await self._prepare_target(input_url, http_session)
                return input_url, target

        tasks = [asyncio.create_task(resolve_one(input_url)) for input_url in unique_inputs]
        try:
            for task in asyncio.as_completed(tasks):
                if await self._should_stop(should_stop):
                    raise LinkCheckStopped("task stop requested")
                input_url, target = await task
                input_targets[input_url] = target
        except Exception:
            self._cancel_pending_tasks(tasks)
            raise

        return [input_targets[input_url] for input_url in normalized_urls]

    async def check_multiple_links(self, urls: List[str], max_concurrent: int = 5) -> List[Dict]:
        return await self.check_multiple_links_with_progress(urls, max_concurrent=max_concurrent)

    async def check_multiple_links_with_progress(
        self,
        urls: List[str],
        max_concurrent: int = 5,
        progress_callback: Optional[Callable[[int, int, int, int], Awaitable[None]]] = None,
        result_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        should_stop: Optional[Callable[[], bool | Awaitable[bool]]] = None,
    ) -> List[Dict]:
        if not urls:
            if progress_callback is not None:
                await progress_callback(0, 0, 0, 0)
            return []

        normalized_inputs = [normalize_candidate_url(url) or (url or "").strip() for url in urls]
        async with await self._create_session(self.default_timeout) as http_session:
            all_results: List[Optional[Dict]] = [None] * len(urls)
            checked = 0
            valid = 0
            invalid = 0

            async def report_progress() -> None:
                if progress_callback is not None:
                    await progress_callback(checked, len(urls), valid, invalid)

            async def emit_result_event(
                index: int,
                output: Dict[str, Any],
                *,
                source: str,
                target: Optional[LinkTarget] = None,
            ) -> None:
                if result_callback is None:
                    return

                platform = ""
                if target is not None and target.netdisk_type:
                    platform = target.netdisk_type
                elif output.get("netdisk_type"):
                    platform = str(output["netdisk_type"])
                else:
                    platform = detect_platform_from_url(normalized_inputs[index])

                await result_callback(
                    {
                        "checked": checked,
                        "total": len(urls),
                        "source": source,
                        "url": output.get("url") or normalized_inputs[index],
                        "resolved_url": (
                            target.resolved_url
                            if target is not None
                            else output.get("resolved_url") or normalized_inputs[index]
                        ),
                        "platform": platform,
                        "status": output.get("status"),
                        "is_valid": bool(output.get("is_valid")),
                        "response_time": output.get("response_time"),
                        "error": output.get("error"),
                        "reason": output.get("reason"),
                        "checker": output.get("checker"),
                    }
                )

            async def finalize_result(
                index: int,
                output: Dict[str, Any],
                *,
                source: str,
                target: Optional[LinkTarget] = None,
            ) -> None:
                nonlocal checked, valid, invalid
                all_results[index] = output
                checked += 1
                if output["is_valid"]:
                    valid += 1
                else:
                    invalid += 1
                await emit_result_event(index, output, source=source, target=target)

            original_cache_hits: Dict[str, LinkCheckResult] = {}
            original_misses: List[str] = []
            for input_url in dict.fromkeys(normalized_inputs):
                cached_result = self._get_cached_result_for_keys([input_url])
                if cached_result is not None:
                    original_cache_hits[input_url] = cached_result
                else:
                    original_misses.append(input_url)

            original_history_hits = self._get_history_results(original_misses)
            remaining_indices: List[int] = []
            for index, input_url in enumerate(normalized_inputs):
                base_result = original_cache_hits.get(input_url) or original_history_hits.get(input_url)
                if base_result is None:
                    remaining_indices.append(index)
                    continue

                output = self._clone_result_for_url(base_result, url=input_url)
                source = "cache" if input_url in original_cache_hits else "history"
                await finalize_result(index, output, source=source)

            if checked:
                await report_progress()

            if not remaining_indices:
                return [result for result in all_results if result is not None]

            if await self._should_stop(should_stop):
                raise LinkCheckStopped("task stop requested")

            remaining_urls = [normalized_inputs[index] for index in remaining_indices]
            remaining_targets = await self._resolve_targets(
                remaining_urls,
                http_session,
                max_concurrent=max_concurrent,
                should_stop=should_stop,
            )

            grouped_targets: Dict[tuple[str, str], Dict[str, object]] = {}
            for relative_index, target in enumerate(remaining_targets):
                absolute_index = remaining_indices[relative_index]
                cache_key = (
                    target.netdisk_type,
                    canonical_target_key(target.resolved_url, fallback=target.original_url),
                )
                group = grouped_targets.setdefault(
                    cache_key,
                    {"target": target, "indices": [], "result": None},
                )
                group["indices"].append(absolute_index)

            platform_groups: Dict[str, List[Dict[str, object]]] = {}
            for group in grouped_targets.values():
                target = group["target"]
                platform_groups.setdefault(target.netdisk_type, []).append(group)

            history_lookup_keys: List[str] = []
            for group in grouped_targets.values():
                target = group["target"]
                target_cache_keys = self._build_target_cache_keys(target)
                cached_result = self._get_cached_result_for_keys(target_cache_keys)
                if cached_result is not None:
                    group["result"] = cached_result
                    group["result_source"] = "cache"
                    continue
                history_lookup_keys.extend(target_cache_keys)

            resolved_history_hits = self._get_history_results(history_lookup_keys)
            for group in grouped_targets.values():
                if group.get("result") is not None:
                    continue
                target = group["target"]
                for cache_key in self._build_target_cache_keys(target):
                    history_result = resolved_history_hits.get(cache_key)
                    if history_result is not None:
                        group["result"] = history_result
                        group["result_source"] = "history"
                        break

            for group in grouped_targets.values():
                group_result = group.get("result")
                if group_result is None:
                    continue
                target = group["target"]
                self.result_cache.set(self._build_target_cache_keys(target), group_result)
                for absolute_index in group["indices"]:
                    output = self._clone_result_for_url(
                        group_result,
                        url=normalized_inputs[absolute_index],
                        resolved_url=target.resolved_url,
                        netdisk_type=target.netdisk_type,
                    )
                    source = str(group.get("result_source") or "history")
                    await finalize_result(absolute_index, output, source=source, target=target)
            if checked and any(group.get("result") is not None for group in grouped_targets.values()):
                await report_progress()

            for platform, groups in platform_groups.items():
                if await self._should_stop(should_stop):
                    raise LinkCheckStopped("task stop requested")
                checker = self.registry.get_checker(platform)
                platform_limit = min(checker.get_concurrency_limit(), max(1, max_concurrent))
                semaphore = asyncio.Semaphore(platform_limit)

                async def check_group(group: Dict[str, object]) -> Tuple[Dict[str, object], LinkCheckResult]:
                    async with semaphore:
                        target = group["target"]
                        result = await self._execute_with_retry(target, checker, http_session)
                        self._store_result_in_cache(target, result)
                        return group, result

                pending_groups = [group for group in groups if group.get("result") is None]
                tasks = [asyncio.create_task(check_group(group)) for group in pending_groups]
                try:
                    for task in asyncio.as_completed(tasks):
                        if await self._should_stop(should_stop):
                            raise LinkCheckStopped("task stop requested")
                        group, result = await task
                        for index in group["indices"]:
                            cloned_result = result.clone_for_input(normalized_inputs[index]).to_dict()
                            cloned_result["_input_index"] = index
                            await finalize_result(index, cloned_result, source="network", target=group["target"])
                        self.error_counts[platform] = 0 if result.is_valid else self.error_counts.get(platform, 0) + 1
                        await report_progress()
                except Exception:
                    self._cancel_pending_tasks(tasks)
                    raise

            return [result for result in all_results if result is not None]

    def get_summary(self, results: List[Dict]) -> Dict:
        total = len(results)
        valid = sum(1 for result in results if result.get("is_valid"))
        invalid = total - valid

        netdisk_stats: Dict[str, Dict[str, float | int]] = {}
        status_counts: Dict[str, int] = {}
        for result in results:
            netdisk_type = result.get("netdisk_type", UNKNOWN_PLATFORM)
            netdisk_bucket = netdisk_stats.setdefault(
                netdisk_type,
                {"total": 0, "valid": 0, "invalid": 0, "uncertain": 0, "rate_limited": 0, "requires_code": 0},
            )
            netdisk_bucket["total"] += 1
            if result.get("is_valid"):
                netdisk_bucket["valid"] += 1
            else:
                netdisk_bucket["invalid"] += 1

            status = str(result.get("status") or "")
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1
                if status in netdisk_bucket:
                    netdisk_bucket[status] += 1

        response_times = [
            result["response_time"]
            for result in results
            if result.get("response_time") is not None
        ]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0

        return {
            "total_links": total,
            "valid_links": valid,
            "invalid_links": invalid,
            "success_rate": (valid / total * 100) if total > 0 else 0.0,
            "avg_response_time": avg_response_time,
            "netdisk_stats": netdisk_stats,
            "status_counts": status_counts,
        }
