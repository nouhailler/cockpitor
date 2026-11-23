from . import (
    actions,
    assistant,
    auth,
    backups,
    diagnostics,
    files,
    integrations,
    remote,
    settings,
    system,
)


def register_routes(app):
    for module in (
        auth,
        actions,
        assistant,
        system,
        integrations,
        settings,
        diagnostics,
        files,
        backups,
        remote,
    ):
        app.include_router(module.create_router(app))
