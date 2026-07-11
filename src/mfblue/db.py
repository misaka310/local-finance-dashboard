"""Compatibility facade for the split database modules.

New code should import from db_budget, db_assets, db_schema, or db_common when the
responsibility is known. Existing imports from mfblue.db remain supported.
"""

from . import db_assets as _db_assets
from . import db_budget as _db_budget
from . import db_common as _db_common
from . import db_schema as _db_schema

for _module in (_db_common, _db_budget, _db_schema, _db_assets):
    for _name, _value in vars(_module).items():
        if not _name.startswith("__"):
            globals()[_name] = _value

del _module, _name, _value
