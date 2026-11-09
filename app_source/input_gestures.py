"""One active control shares ownership with the application's undo gesture.

Detach before callbacks: ending/cancelling a widget may re-enter the application
gesture methods, refresh a panel, or destroy the original widget.
"""


def claim_input(app, control):
    previous = getattr(app, '_active_input_control', None)
    if previous is not None and previous is not control:
        previous.finish_input()
    app._active_input_control = control


def release_input(app, control):
    if getattr(app, '_active_input_control', None) is control:
        app._active_input_control = None


def finish_active_input(app, *, cancel=False):
    control = getattr(app, '_active_input_control', None)
    if control is None:
        return False
    control.finish_input(cancel=cancel)
    return True
