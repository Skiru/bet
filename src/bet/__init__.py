import sys

# Strip only the source/scripts paths of the frozen forensic repo, but preserve site-packages and venv.
sys.path = [
    p for p in sys.path
    if "projects/bet/src" not in p
    and p != "/Users/mkoziol/projects/bet"
    and p != "/Users/mkoziol/projects/bet/scripts"
]
