import sys
sys.path.insert(0, '.')

from core.engine import create_engine
from core.event_bus import EventBus, EventType
from command.command import Command, create_command
from command.handler import CommandHandler
from memory.storage import MemoryStorage
from context.context_manager import ContextManager

print('All imports successful!')

bus = EventBus()
storage = MemoryStorage('memory/test_memory.json')
ctx = ContextManager()
handler = CommandHandler(bus)

received = []
bus.subscribe(EventType.UI_OPEN_REQUESTED, lambda e: received.append(e))
bus.emit_simple(EventType.UI_OPEN_REQUESTED, {'mode': 'developer'})
print(f'Event bus test: {len(received)} events received')

cmd = create_command('open_ui', source='keyboard', mode='developer')
result = handler.execute(cmd)
print(f'Command test: {result.success}, data={result.data}')

storage.set('mode', 'test_mode')
print(f'Memory test: {storage.get("mode")}')

ctx.update(active_app='code', active_window='main.py')
print(f'Context test: {ctx.get_mode()}')

print('ALL TESTS PASSED!')