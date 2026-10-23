# Las pruebas usan una carpeta de datos temporal (nunca tu data/ real).
import os
import tempfile

os.environ["EDI_DATA_DIR"] = tempfile.mkdtemp(prefix="edi-test-")
os.environ.setdefault("EDI_CONFIG_DIR", os.path.join(os.path.dirname(__file__), "..", "config"))
os.environ["EDI_TS_PORT"] = "8768"
os.environ["TAILSCALE_CLI"] = "/nonexistent/tailscale"   # por defecto: «sin Tailscale instalado»
