"""Manifest Discovery Loader for 5Aether Host Platform.

This module discovers and loads system modules (like Aether Mark-1)
via their manifest.yaml files, completely independent of PluginLoader.

Usage:
    from systems.manifest_discovery import load_mark1_adapter
    adapter = load_mark1_adapter()
    if adapter:
        health = adapter.get_health()
        start_result = adapter.start()
        adapter.stop()