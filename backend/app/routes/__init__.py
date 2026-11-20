from . import actions, assistant, auth, backups, diagnostics, files, integrations, settings, system


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
    ):
        app.include_router(module.create_router(app))
