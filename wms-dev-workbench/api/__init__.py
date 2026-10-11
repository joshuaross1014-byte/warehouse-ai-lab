"""API blueprints. Each module = one tab in the UI. Register them all in app.py."""
from .schema import bp as schema_bp
from .objects import bp as objects_bp
from .trace import bp as trace_bp
from .ops import bp as ops_bp
from .sql import bp as sql_bp
from .diff import bp as diff_bp

ALL = (schema_bp, objects_bp, trace_bp, ops_bp, sql_bp, diff_bp)
