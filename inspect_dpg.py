import dearpygui.dearpygui as dpg
print('version', getattr(dpg, '__version__', 'unknown'))
for name in ['render_dearpygui','start_dearpygui','create_context','setup_dearpygui','show_viewport','create_viewport','set_primary_window','add_dynamic_texture','add_static_texture','cleanup_dearpygui']:
    print(name, hasattr(dpg, name))
