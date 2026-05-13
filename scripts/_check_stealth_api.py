import playwright_stealth
print(dir(playwright_stealth))
print("---")
print(playwright_stealth.__version__ if hasattr(playwright_stealth, '__version__') else 'no version')
# Check submodules
import inspect
for name, obj in inspect.getmembers(playwright_stealth):
    if callable(obj) and not name.startswith('_'):
        print(f"  callable: {name}")
