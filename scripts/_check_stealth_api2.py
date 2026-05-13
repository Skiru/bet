from playwright_stealth import Stealth
import inspect
print("Stealth signature:", inspect.signature(Stealth.__init__))
print("Stealth methods:", [m for m in dir(Stealth) if not m.startswith('_')])

# Check stealth submodule
from playwright_stealth import stealth as stealth_mod
print("\nstealth submodule:", dir(stealth_mod))
for name, obj in inspect.getmembers(stealth_mod):
    if callable(obj) and not name.startswith('_'):
        print(f"  callable: {name}")
