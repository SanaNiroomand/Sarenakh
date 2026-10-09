import os
import tempfile

# Must run before `app` is imported: isolated DB, no OpenAI calls at startup.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="sarenakh-test-")
os.environ["MODEL_CHECK"] = "off"
os.environ["COOKIE_SECURE"] = "false"
