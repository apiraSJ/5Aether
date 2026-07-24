"""
Plugins package.

Phase A ships one proof-of-life plugin (SystemInfoPlugin) to demonstrate the
full pipeline works end-to-end: config -> PluginLoader -> plugin registers a
command -> CommandBus dispatches it -> ResultPipeline fans out the result ->
EventBus receives 'CommandCompleted'.

Phase C/D will add real plugins here: KeyboardInputPlugin, MouseInputPlugin,
GestureInputPlugin, VoiceInputPlugin, HandVisionPlugin, ObjectVisionPlugin,
SpatialTrackingPlugin — each implementing the same PluginBase contract.
"""
