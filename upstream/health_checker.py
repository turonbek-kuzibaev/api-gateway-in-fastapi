import asyncio
import time
from dataclasses import dataclass, field

import httpx

from models import HealthCheckConfig
from .target import Target


@dataclass
class HealthChecker:
    config: HealthCheckConfig
    targets: list[Target] = field(default_factory=list)

    _running: bool = field(default=False, init=False)
    _task: asyncio.Task | None = field(default=None, init=False)
    _client: httpx.AsyncClient | None = field(default=None, init=False)

    async def start(self) -> None:
        if not self.config.enabled or self._running:
            return

        self._running = True
        self._client = httpx.AsyncClient(timeout=self.config.timeout)
        self._task = asyncio.create_task(self._run_checks())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._client:
            await self._client.aclose()
            self._client = None

    async def _run_checks(self) -> None:
        while self._running:
            await self._check_all_targets()
            await asyncio.sleep(self.config.interval)

    async def _check_all_targets(self) -> None:
        tasks = [self._check_target(target) for target in self.targets]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_target(self, target: Target) -> None:
        if not self._client:
            return

        target.last_check_time = time.time()
        url = f"{target.url}{self.config.path}"

        try:
            if self.config.type.value == "http":
                response = await self._client.get(url)
                is_healthy = response.status_code in self.config.expected_statuses
            else:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target.host, target.port),
                    timeout=self.config.timeout,
                )
                writer.close()
                await writer.wait_closed()
                is_healthy = True

            if is_healthy:
                target.consecutive_successes += 1
                target.consecutive_failures = 0
                if target.consecutive_successes >= self.config.healthy_threshold:
                    target.mark_healthy()
            else:
                self._record_unhealthy(target)

        except Exception:
            self._record_unhealthy(target)

    def _record_unhealthy(self, target: Target) -> None:
        target.consecutive_failures += 1
        target.consecutive_successes = 0
        if target.consecutive_failures >= self.config.unhealthy_threshold:
            target.mark_unhealthy()

    def add_target(self, target: Target) -> None:
        if target not in self.targets:
            self.targets.append(target)

    def remove_target(self, target: Target) -> None:
        if target in self.targets:
            self.targets.remove(target)

    async def check_now(self, target: Target) -> bool:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)

        await self._check_target(target)
        return target.is_healthy
