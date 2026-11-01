from app.services.watchlists import DEMO_OWNER


def current_owner() -> str:
    """Demo profile. Every user-scoped query is already filtered by owner, so swapping this dependency
    for a real authenticated user id (Part 7) requires no changes to the repositories or routes.
    LIMITATION: all browsers share the single 'demo' profile; do not expose a demo deployment publicly."""
    return DEMO_OWNER
