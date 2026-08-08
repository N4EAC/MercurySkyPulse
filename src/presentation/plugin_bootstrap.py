"""Trusted built-in plugin registration at the desktop composition boundary."""

from __future__ import annotations

from application.plugins import (
    ExtensionContribution, ExtensionPoint, ObjectPlugin, PluginManifest,
    PluginRegistry,
)

from .themes import apply_appearance


def create_builtin_registry(*, license_features: frozenset[str], event_sink,
                            mercury_transport, beacon_transport, location_service,
                            bbs_service, web_server, web_snapshot) -> PluginRegistry:
    registry = PluginRegistry(
        enabled_license_features=license_features, event_sink=event_sink
    )
    builtins = (
        (_manifest("core.mercury", "Mercury Transport", "mercury.transport",
                   ExtensionPoint.TRANSPORT, "transport"),
         ObjectPlugin({"transport": mercury_transport, "beacon-transport": beacon_transport})),
        (_manifest("core.themes", "GUI Themes", "ui.theme",
                   ExtensionPoint.THEME, "themes"),
         ObjectPlugin({"themes": apply_appearance})),
        (_manifest("core.gps", "GPS Position Source", "location.read",
                   ExtensionPoint.POSITION_SOURCE, "gps"),
         ObjectPlugin({"gps": location_service.receiver})),
        (_manifest("core.mapping", "Mapping Export", "filesystem.export",
                   ExtensionPoint.MAP_PROVIDER, "mapping"),
         ObjectPlugin({"mapping": location_service.exporter})),
        (_manifest("core.bbs", "BBS", "application.bbs", ExtensionPoint.BBS,
                   "bbs", dependencies=("core.mercury",)),
         ObjectPlugin({"bbs": bbs_service})),
        (_manifest("core.web", "Local Web Interface", "local.http",
                   ExtensionPoint.WEB_INTERFACE, "web"),
         ObjectPlugin({"web": web_server, "snapshot": web_snapshot})),
        (_manifest("core.logging", "Application Logging", "logging.write",
                   ExtensionPoint.LOGGING, "logging"),
         ObjectPlugin({"logging": web_snapshot.append_log})),
    )
    for manifest, plugin in builtins:
        registry.register(manifest, plugin)
    registry.activate_all()
    return registry


def _manifest(plugin_id: str, name: str, permission: str,
              point: ExtensionPoint, export: str,
              dependencies: tuple[str, ...] = ()) -> PluginManifest:
    return PluginManifest(
        plugin_id, name, "0.1.0", "MercurySkyPulse", built_in=True,
        dependencies=dependencies, permissions=frozenset({permission}),
        extensions=(ExtensionContribution(point, export),),
    )
