import hashlib
import random
from abc import ABC, abstractmethod
from typing import Any

from .target import Target


class BalancingStrategy(ABC):
    @abstractmethod
    def select(self, targets: list[Target], context: dict[str, Any] | None = None) -> Target | None:
        pass


class RoundRobinStrategy(BalancingStrategy):
    def __init__(self):
        self._index = 0

    def select(self, targets: list[Target], context: dict[str, Any] | None = None) -> Target | None:
        healthy = [t for t in targets if t.is_healthy]
        if not healthy:
            return None

        target = healthy[self._index % len(healthy)]
        self._index = (self._index + 1) % len(healthy)
        return target


class WeightedRoundRobinStrategy(BalancingStrategy):
    def __init__(self):
        self._current_weights: dict[str, int] = {}

    def select(self, targets: list[Target], context: dict[str, Any] | None = None) -> Target | None:
        healthy = [t for t in targets if t.is_healthy]
        if not healthy:
            return None

        total_weight = sum(t.effective_weight for t in healthy)
        if total_weight == 0:
            return healthy[0] if healthy else None

        for t in healthy:
            addr = t.address
            self._current_weights[addr] = self._current_weights.get(addr, 0) + t.effective_weight

        best: Target | None = None
        best_weight = -1

        for t in healthy:
            addr = t.address
            if self._current_weights[addr] > best_weight:
                best_weight = self._current_weights[addr]
                best = t

        if best:
            self._current_weights[best.address] -= total_weight

        return best


class LeastConnectionsStrategy(BalancingStrategy):
    def select(self, targets: list[Target], context: dict[str, Any] | None = None) -> Target | None:
        healthy = [t for t in targets if t.is_healthy]
        if not healthy:
            return None

        return min(healthy, key=lambda t: t.active_connections)


class IPHashStrategy(BalancingStrategy):
    def select(self, targets: list[Target], context: dict[str, Any] | None = None) -> Target | None:
        healthy = [t for t in targets if t.is_healthy]
        if not healthy:
            return None

        client_ip = context.get("client_ip", "127.0.0.1") if context else "127.0.0.1"
        hash_value = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        index = hash_value % len(healthy)
        return healthy[index]


class RandomStrategy(BalancingStrategy):
    def select(self, targets: list[Target], context: dict[str, Any] | None = None) -> Target | None:
        healthy = [t for t in targets if t.is_healthy]
        if not healthy:
            return None

        weights = [t.effective_weight for t in healthy]
        total = sum(weights)
        if total == 0:
            return random.choice(healthy)

        return random.choices(healthy, weights=weights, k=1)[0]


class LoadBalancer:
    STRATEGIES = {
        "round-robin": RoundRobinStrategy,
        "weighted": WeightedRoundRobinStrategy,
        "least-connections": LeastConnectionsStrategy,
        "ip-hash": IPHashStrategy,
        "random": RandomStrategy,
    }

    def __init__(self, algorithm: str = "round-robin"):
        strategy_cls = self.STRATEGIES.get(algorithm, RoundRobinStrategy)
        self._strategy = strategy_cls()
        self._algorithm = algorithm

    @property
    def algorithm(self) -> str:
        return self._algorithm

    def select(self, targets: list[Target], context: dict[str, Any] | None = None) -> Target | None:
        return self._strategy.select(targets, context)

    @classmethod
    def available_algorithms(cls) -> list[str]:
        return list(cls.STRATEGIES.keys())
