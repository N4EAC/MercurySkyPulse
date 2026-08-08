"""Plugin contracts, dependency resolution, permissions, and lifecycle kernel."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re
from types import MappingProxyType
from typing import Callable, Mapping, Protocol


PLUGIN_API_VERSION = 1
IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class ExtensionPoint(StrEnum):
    TRANSPORT = "transport"
    THEME = "theme"
    POSITION_SOURCE = "position-source"
    MAP_PROVIDER = "map-provider"
    BBS = "bbs"
    WEB_INTERFACE = "web-interface"
    LOGGING = "logging"
    ENCRYPTION_PROVIDER = "encryption-provider"
    APPLICATION_SERVICE = "application-service"


class PluginState(StrEnum):
    REGISTERED = "registered"
    ACTIVE = "active"
    BLOCKED = "blocked"
    FAILED = "failed"
    DISABLED = "disabled"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class ExtensionContribution:
    point: ExtensionPoint
    export: str
    priority: int = 0

    def __post_init__(self) -> None:
        if not IDENTIFIER.fullmatch(self.export) or not -1000 <= self.priority <= 1000:
            raise ValueError("Invalid plugin extension contribution")


@dataclass(frozen=True, slots=True)
class PluginManifest:
    id: str
    name: str
    version: str
    publisher: str
    api_min: int = 1
    api_max: int = 1
    built_in: bool = False
    dependencies: tuple[str, ...] = ()
    permissions: frozenset[str] = frozenset()
    extensions: tuple[ExtensionContribution, ...] = ()
    license_feature: str | None = None

    def __post_init__(self) -> None:
        if not IDENTIFIER.fullmatch(self.id) or not VERSION.fullmatch(self.version):
            raise ValueError("Invalid plugin identifier or semantic version")
        if not self.name.strip() or len(self.name) > 100 or not self.publisher.strip() or len(self.publisher) > 100:
            raise ValueError("Invalid plugin name or publisher")
        if self.api_min < 1 or self.api_max < self.api_min:
            raise ValueError("Invalid plugin API compatibility range")
        if len(set(self.dependencies)) != len(self.dependencies) or self.id in self.dependencies:
            raise ValueError("Invalid plugin dependencies")
        if any(not IDENTIFIER.fullmatch(item) for item in self.dependencies):
            raise ValueError("Invalid plugin dependency identifier")
        if any(not IDENTIFIER.fullmatch(item) for item in self.permissions):
            raise ValueError("Invalid plugin permission")
        exports = [item.export for item in self.extensions]
        if len(exports) != len(set(exports)):
            raise ValueError("Plugin extension exports must be unique")
        if self.license_feature and not IDENTIFIER.fullmatch(self.license_feature):
            raise ValueError("Invalid plugin license feature")


class Plugin(Protocol):
    def start(self, context: "PluginContext") -> Mapping[str, object]: ...
    def stop(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PluginContext:
    plugin_id: str
    permissions: frozenset[str]
    _dependencies: Mapping[str, Mapping[str, object]]

    def require_permission(self, permission: str) -> None:
        if permission not in self.permissions:
            raise PermissionError(f"Plugin {self.plugin_id} lacks permission {permission}")

    def dependency_export(self, plugin_id: str, export: str) -> object:
        if plugin_id not in self._dependencies:
            raise KeyError(f"Plugin {plugin_id} is not a declared active dependency")
        try:
            return self._dependencies[plugin_id][export]
        except KeyError as error:
            raise KeyError(f"Dependency {plugin_id} has no export {export}") from error


@dataclass(slots=True)
class PluginRecord:
    manifest: PluginManifest
    plugin: Plugin
    granted_permissions: frozenset[str]
    state: PluginState = PluginState.REGISTERED
    reason: str = ""
    exports: Mapping[str, object] = field(default_factory=dict)


class ObjectPlugin:
    """Trusted built-in adapter for an already-composed component set."""

    def __init__(self, exports: Mapping[str, object], stop: Callable[[], None] | None = None) -> None:
        self._exports = dict(exports)
        self._stop = stop

    def start(self, _context: PluginContext) -> Mapping[str, object]:
        return MappingProxyType(self._exports)

    def stop(self) -> None:
        if self._stop:
            self._stop()


class PluginRegistry:
    """Deterministic in-process kernel for trusted built-ins and test providers.

    Third-party packages are intentionally not loaded by this class yet.
    """

    def __init__(self, api_version: int = PLUGIN_API_VERSION,
                 enabled_license_features: frozenset[str] | None = None,
                 event_sink: Callable[[str], None] | None = None) -> None:
        self.api_version = api_version
        self.enabled_license_features = enabled_license_features
        self.event_sink = event_sink or (lambda _message: None)
        self._records: dict[str, PluginRecord] = {}
        self._activation_order: list[str] = []

    def register(self, manifest: PluginManifest, plugin: Plugin,
                 granted_permissions: frozenset[str] | None = None) -> None:
        if manifest.id in self._records:
            raise ValueError(f"Plugin {manifest.id} is already registered")
        grants = manifest.permissions if manifest.built_in and granted_permissions is None else (granted_permissions or frozenset())
        self._records[manifest.id] = PluginRecord(manifest, plugin, frozenset(grants))

    def activate_all(self) -> None:
        for plugin_id in self._resolve_order():
            record = self._records[plugin_id]
            if record.state is PluginState.ACTIVE:
                continue
            manifest = record.manifest
            if not manifest.api_min <= self.api_version <= manifest.api_max:
                self._set_state(record, PluginState.DISABLED, "Incompatible plugin API")
                continue
            missing_grants = manifest.permissions - record.granted_permissions
            if missing_grants:
                self._set_state(record, PluginState.DISABLED,
                                f"Permissions not granted: {', '.join(sorted(missing_grants))}")
                continue
            if (manifest.license_feature and self.enabled_license_features is not None
                    and manifest.license_feature not in self.enabled_license_features):
                self._set_state(record, PluginState.DISABLED, "License feature is not enabled")
                continue
            inactive = [item for item in manifest.dependencies
                        if self._records[item].state is not PluginState.ACTIVE]
            if inactive:
                self._set_state(record, PluginState.BLOCKED,
                                f"Inactive dependencies: {', '.join(inactive)}")
                continue
            dependencies = MappingProxyType({
                item: self._records[item].exports for item in manifest.dependencies
            })
            context = PluginContext(manifest.id, record.granted_permissions, dependencies)
            try:
                exports = dict(record.plugin.start(context))
                declared = {item.export for item in manifest.extensions}
                if not declared <= set(exports):
                    raise ValueError("Plugin did not provide all declared extension exports")
                record.exports = MappingProxyType(exports)
                self._activation_order.append(plugin_id)
                self._set_state(record, PluginState.ACTIVE)
            except Exception as error:  # Plugin boundary intentionally contains failures.
                self._set_state(record, PluginState.FAILED,
                                f"{type(error).__name__}: {error}"[:300])

    def stop_all(self) -> None:
        for plugin_id in reversed(self._activation_order):
            record = self._records[plugin_id]
            try:
                record.plugin.stop()
                self._set_state(record, PluginState.STOPPED)
            except Exception as error:
                self._set_state(record, PluginState.FAILED,
                                f"Stop failed: {type(error).__name__}: {error}"[:300])
        self._activation_order.clear()

    def export(self, plugin_id: str, name: str) -> object:
        record = self._records[plugin_id]
        if record.state is not PluginState.ACTIVE:
            raise RuntimeError(f"Plugin {plugin_id} is not active")
        return record.exports[name]

    def extensions(self, point: ExtensionPoint) -> list[tuple[PluginManifest, object]]:
        providers = []
        for record in self._records.values():
            if record.state is not PluginState.ACTIVE:
                continue
            for contribution in record.manifest.extensions:
                if contribution.point is point:
                    providers.append((contribution.priority, record.manifest,
                                      record.exports[contribution.export]))
        providers.sort(key=lambda item: (-item[0], item[1].id))
        return [(manifest, value) for _, manifest, value in providers]

    def snapshot(self) -> list[dict[str, object]]:
        return [{
            "id": record.manifest.id, "name": record.manifest.name,
            "version": record.manifest.version, "publisher": record.manifest.publisher,
            "built_in": record.manifest.built_in, "state": record.state.value,
            "reason": record.reason,
            "extensions": [item.point.value for item in record.manifest.extensions],
            "permissions": sorted(record.granted_permissions),
        } for record in sorted(self._records.values(), key=lambda item: item.manifest.id)]

    def _resolve_order(self) -> list[str]:
        missing = [(record.manifest.id, dependency)
                   for record in self._records.values()
                   for dependency in record.manifest.dependencies
                   if dependency not in self._records]
        if missing:
            owner, dependency = missing[0]
            raise ValueError(f"Plugin {owner} requires missing plugin {dependency}")
        order, visiting, visited = [], set(), set()

        def visit(plugin_id: str) -> None:
            if plugin_id in visiting:
                raise ValueError(f"Plugin dependency cycle includes {plugin_id}")
            if plugin_id in visited:
                return
            visiting.add(plugin_id)
            for dependency in sorted(self._records[plugin_id].manifest.dependencies):
                visit(dependency)
            visiting.remove(plugin_id)
            visited.add(plugin_id)
            order.append(plugin_id)

        for plugin_id in sorted(self._records):
            visit(plugin_id)
        return order

    def _set_state(self, record: PluginRecord, state: PluginState, reason: str = "") -> None:
        record.state, record.reason = state, reason
        detail = f": {reason}" if reason else ""
        self.event_sink(f"Plugin {record.manifest.id} {state.value}{detail}")
