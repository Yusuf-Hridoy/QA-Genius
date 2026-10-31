"""The test suite runs the app the way a developer runs it.

The API docs and the /dev check pages exist only when QAG_DEV=1, so the
suite says so before anything imports the app. The one test that proves
they are gone in production builds its own app with the flag cleared.
"""

import os

os.environ.setdefault("QAG_DEV", "1")
