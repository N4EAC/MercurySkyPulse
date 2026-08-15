from __future__ import annotations

import unittest
from dataclasses import fields
from types import SimpleNamespace

from application.plugins import (
    ExtensionContribution, ExtensionPoint, ObjectPlugin, PluginContext,
    PluginManifest, PluginRegistry, PluginState,
)
from presentation.plugin_bootstrap import create_builtin_registry


def manifest(plugin_id: str, *, dependencies=(), permissions=frozenset(),
             point=ExtensionPoint.APPLICATION_SERVICE, export="service", priority=0,
             api_min=1, api_max=1) -> PluginManifest:
    return PluginManifest(
        plugin_id, plugin_id.title(), "1.0.0", "Test Publisher",
        api_min=api_min, api_max=api_max, dependencies=dependencies,
        permissions=permissions,
        extensions=(ExtensionContribution(point, export, priority),),
    )


class RecordingPlugin:
    def __init__(self, name, events, value=None, fail=False) -> None:
        self.name, self.events, self.value, self.fail = name, events, value, fail

    def start(self, context: PluginContext):
        self.events.append(f"start:{self.name}")
        if self.fail:
            raise RuntimeError("plugin crashed")
        return {"service": self.value if self.value is not None else self.name}

    def stop(self):
        self.events.append(f"stop:{self.name}")


class PluginTests(unittest.TestCase):
    def test_manifest_and_extension_points_have_no_entitlement_or_encryption_hooks(self) -> None:
        self.assertNotIn("license_feature", {item.name for item in fields(PluginManifest)})
        self.assertNotIn("encryption-provider", {item.value for item in ExtensionPoint})

    def test_dependencies_start_first_and_stop_in_reverse(self) -> None:
        events = []
        registry = PluginRegistry()
        registry.register(manifest("core.base"), RecordingPlugin("base", events))
        registry.register(manifest("feature.child", dependencies=("core.base",)),
                          RecordingPlugin("child", events))
        registry.activate_all()
        self.assertEqual(events, ["start:base", "start:child"])
        self.assertEqual(registry.export("feature.child", "service"), "child")
        registry.stop_all()
        self.assertEqual(events[-2:], ["stop:child", "stop:base"])

    def test_plugin_failure_is_contained_and_dependents_are_blocked(self) -> None:
        registry = PluginRegistry()
        events = []
        registry.register(manifest("core.failure"), RecordingPlugin("failure", events, fail=True))
        registry.register(manifest("feature.dependent", dependencies=("core.failure",)),
                          RecordingPlugin("dependent", events))
        registry.register(manifest("feature.independent"), RecordingPlugin("independent", events))
        registry.activate_all()
        states = {item["id"]: item["state"] for item in registry.snapshot()}
        self.assertEqual(states["core.failure"], PluginState.FAILED.value)
        self.assertEqual(states["feature.dependent"], PluginState.BLOCKED.value)
        self.assertEqual(states["feature.independent"], PluginState.ACTIVE.value)

    def test_permissions_are_deny_by_default(self) -> None:
        registry = PluginRegistry()
        registry.register(manifest("third.permission", permissions=frozenset({"local.http"})),
                          ObjectPlugin({"service": object()}))
        registry.activate_all()
        states = {item["id"]: item["state"] for item in registry.snapshot()}
        self.assertEqual(states["third.permission"], PluginState.DISABLED.value)

    def test_extension_providers_are_ordered_by_priority_then_id(self) -> None:
        registry = PluginRegistry()
        registry.register(manifest("map.secondary", point=ExtensionPoint.MAP_PROVIDER,
                                   priority=1), ObjectPlugin({"service": "secondary"}))
        registry.register(manifest("map.primary", point=ExtensionPoint.MAP_PROVIDER,
                                   priority=10), ObjectPlugin({"service": "primary"}))
        registry.activate_all()
        self.assertEqual([value for _, value in registry.extensions(ExtensionPoint.MAP_PROVIDER)],
                         ["primary", "secondary"])

    def test_missing_exports_and_incompatible_api_disable_provider(self) -> None:
        registry = PluginRegistry(api_version=1)
        registry.register(manifest("bad.export"), ObjectPlugin({"other": object()}))
        registry.register(manifest("future.plugin", api_min=2, api_max=3),
                          ObjectPlugin({"service": object()}))
        registry.activate_all()
        states = {item["id"]: item["state"] for item in registry.snapshot()}
        self.assertEqual(states["bad.export"], PluginState.FAILED.value)
        self.assertEqual(states["future.plugin"], PluginState.DISABLED.value)

    def test_duplicate_registration_and_dependency_cycles_are_rejected(self) -> None:
        registry = PluginRegistry()
        registry.register(manifest("cycle.one", dependencies=("cycle.two",)),
                          ObjectPlugin({"service": 1}))
        registry.register(manifest("cycle.two", dependencies=("cycle.one",)),
                          ObjectPlugin({"service": 2}))
        with self.assertRaisesRegex(ValueError, "cycle"):
            registry.activate_all()
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(manifest("cycle.one"), ObjectPlugin({"service": 3}))

    def test_current_components_register_as_seven_builtin_plugins(self) -> None:
        events = []
        snapshot = SimpleNamespace(append_log=events.append)
        location = SimpleNamespace(receiver=object(), exporter=object())
        registry = create_builtin_registry(
            event_sink=events.append, mercury_transport=object(), beacon_transport=object(),
            location_service=location, bbs_service=object(),
            web_server=object(), web_snapshot=snapshot,
        )
        records = registry.snapshot()
        self.assertEqual(len(records), 7)
        self.assertTrue(all(item["built_in"] and item["state"] == "active" for item in records))
        self.assertEqual(len(registry.extensions(ExtensionPoint.TRANSPORT)), 1)


if __name__ == "__main__":
    unittest.main()
