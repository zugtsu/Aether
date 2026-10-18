import os
import tempfile

os.environ.setdefault("AETHER_HOME", tempfile.mkdtemp(prefix="aether-test-home-"))
