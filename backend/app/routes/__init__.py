"""API blueprints (all mounted under /api)."""

from .account import bp as account_bp
from .auth import bp as auth_bp
from .health import bp as health_bp
from .instruments import bp as instruments_bp
from .orders import bp as orders_bp
from .portfolio import bp as portfolio_bp
from .security import bp as security_bp
from .blockchain import bp as blockchain_bp
from .transactions import bp as transactions_bp

BLUEPRINTS = [
    health_bp,
    auth_bp,
    account_bp,
    instruments_bp,
    portfolio_bp,
    orders_bp,
    transactions_bp,
    security_bp,
    blockchain_bp,
]
