from . import assistant, auth, diagnostics, integrations, settings, system


def register_routes(app):
    for module in (auth, assistant, system, integrations, settings, diagnostics):
        app.include_router(module.create_router(app))
