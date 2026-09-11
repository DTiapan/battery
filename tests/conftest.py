import sys

# Ensure sqlite3 with extension loading support is available across test suites
for _mod in ("pysqlite3", "sqlean"):
    try:
        sqlite3_replacement = __import__(_mod)
        sys.modules["sqlite3"] = sqlite3_replacement
        break
    except ImportError:
        pass
