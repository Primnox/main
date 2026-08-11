# backend/verify_imports.py
modules = [
    'settings_manager', 'memory', 'notes_manager', 'screen_reader',
    'sensor_vision', 'vad_listener', 'brain', 'context_builder',
    'core', 'server', 'meeting_recorder', 'feed_manager',
    'skills.base_skill', 'skills.skill_router',
    'automation', 'privacy_mirror', 'spatial_engine'
]

print("Primnox V2 - Dependency Check\n" + "="*30)

failed = []
for m in modules:
    try:
        __import__(m)
        print(f'OK: {m}')
    except ImportError as e:
        print(f'MISSING: {m} -> {e.name}')
        failed.append((m, e))
    except Exception as e:
        print(f'ERR: {m} -> {e!r}')
        failed.append((m, e))

if failed:
    print('\nSummary: Some dependencies are missing or broken.')
else:
    print('\nAll imports OK. System ready for Sovereign V2 deployment.')
