PLUGIN_ID = 'error_history_case'
PLUGIN_NAME = 'Error History Case'
def on_message(event, ctx):
    raise RuntimeError('boom-' + event.text)