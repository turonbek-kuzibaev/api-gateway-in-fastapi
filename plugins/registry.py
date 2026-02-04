from typing import Any, Type

from .base import Plugin


class PluginRegistry:
    _plugins: dict[str, Type[Plugin]] = {}

    @classmethod
    def register(cls, name: str | None = None):
        def decorator(plugin_cls: Type[Plugin]):
            plugin_name = name or plugin_cls.name
            cls._plugins[plugin_name] = plugin_cls
            return plugin_cls
        return decorator

    @classmethod
    def get(cls, name: str) -> Type[Plugin] | None:
        return cls._plugins.get(name)

    @classmethod
    def create(cls, name: str, config: dict[str, Any]) -> Plugin | None:
        plugin_cls = cls.get(name)
        if plugin_cls is None:
            return None
        return plugin_cls(config)

    @classmethod
    def list_plugins(cls) -> list[str]:
        return list(cls._plugins.keys())

    @classmethod
    def all(cls) -> dict[str, Type[Plugin]]:
        return cls._plugins.copy()
