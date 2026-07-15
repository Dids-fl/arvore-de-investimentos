# fundos/cvm_cadastro_downloader.py

from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from tempfile import NamedTemporaryFile
import logging
import requests
import zipfile
import shutil
import atexit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------

URL_CADASTRO = (
    "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/"
    "registro_fundo_classe.zip"
)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

ZIP_PATH = DATA_DIR / "registro_fundo_classe.zip"

TIMEOUT = 120

SESSION = requests.Session()
atexit.register(SESSION.close)


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

def _garantir_pasta():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _arquivo_csv_existe():
    return any(csv.stat().st_size > 0 for csv in DATA_DIR.glob("*.csv"))


def _arquivo_zip_existe():
    return ZIP_PATH.exists() and ZIP_PATH.stat().st_size > 0


def _ultima_modificacao_servidor():
    try:
        response = SESSION.head(
            URL_CADASTRO,
            timeout=15,
            allow_redirects=True,
        )
        response.raise_for_status()

        last_modified = response.headers.get("Last-Modified")
        if not last_modified:
            return None

        dt = parsedate_to_datetime(last_modified)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception as e:
        logger.warning(f"Não foi possível verificar atualização da CVM: {e}")
        return None


def _precisa_atualizar():
    if not _arquivo_zip_existe():
        return True

    if not _arquivo_csv_existe():
        return True

    servidor = _ultima_modificacao_servidor()

    if servidor is None:
        logger.info("Não foi possível verificar se há uma versão mais recente.")
        return False

    local = datetime.fromtimestamp(ZIP_PATH.stat().st_mtime, tz=timezone.utc)
    atualizar = servidor.timestamp() > (local.timestamp() + 1)
    return atualizar


# ---------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------

def _baixar_zip():
    _garantir_pasta()
    logger.info("Baixando cadastro da CVM...")

    tmp_path = None

    try:
        with NamedTemporaryFile(delete=False, suffix=".tmp", dir=DATA_DIR) as tmp:
            tmp_path = Path(tmp.name)

            with SESSION.get(URL_CADASTRO, stream=True, timeout=TIMEOUT) as response:
                response.raise_for_status()
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        tmp.write(chunk)

        if not zipfile.is_zipfile(tmp_path):
            raise RuntimeError("O arquivo baixado não é um ZIP válido.")

        shutil.move(tmp_path, ZIP_PATH)
        logger.info("Download concluído.")

    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------
# Extração
# ---------------------------------------------------------------------

def _extrair_zip():
    logger.info("Extraindo arquivos...")

    for csv in DATA_DIR.glob("*.csv"):
        csv.unlink(missing_ok=True)

    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(DATA_DIR)

    logger.info("Extração concluída.")


# ---------------------------------------------------------------------
# Localização do CSV correto
# ---------------------------------------------------------------------

def _localizar_csv():
    csvs = sorted(DATA_DIR.glob("*.csv"))

    if not csvs:
        raise FileNotFoundError("Nenhum CSV encontrado.")

    for csv in csvs:
        try:
            with open(csv, encoding="latin1") as f:
                header = f.readline()

            if "CNPJ_Classe" in header and "Denominacao_Social" in header:
                return str(csv)
        except Exception:
            pass

    logger.warning("Não foi possível identificar o CSV principal. Utilizando o primeiro.")
    return str(csvs[0])


# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------

def download_cadastro(force=False):
    _garantir_pasta()

    if force or _precisa_atualizar():
        logger.info("Atualizando cadastro...")
        _baixar_zip()
        _extrair_zip()
    else:
        logger.info("Cadastro já está atualizado.")

    return _localizar_csv()


# ---------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    caminho = download_cadastro()
    print()
    print("Cadastro disponível em:")
    print(caminho)