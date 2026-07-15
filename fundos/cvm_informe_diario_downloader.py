# fundos/cvm_informe_diario_downloader.py

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

URL_BASE = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/"

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "informe_diario"

TIMEOUT = 120
MESES_HISTORICO = 36

SESSION = requests.Session()
atexit.register(SESSION.close)


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

def _garantir_pasta():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _nome_zip(ano, mes):
    return f"inf_diario_fi_{ano}{mes:02d}.zip"


def _nome_csv(ano, mes):
    return f"inf_diario_fi_{ano}{mes:02d}.csv"


def _zip_path(ano, mes):
    return DATA_DIR / _nome_zip(ano, mes)


def _csv_path(ano, mes):
    return DATA_DIR / _nome_csv(ano, mes)


def _arquivo_zip_existe(ano, mes):
    arquivo = _zip_path(ano, mes)
    return arquivo.exists() and arquivo.stat().st_size > 0


def _arquivo_csv_existe(ano, mes):
    arquivo = _csv_path(ano, mes)
    return arquivo.exists() and arquivo.stat().st_size > 0


def _url_zip(ano, mes):
    return URL_BASE + _nome_zip(ano, mes)


def _ultima_modificacao_servidor(ano, mes):
    try:
        response = SESSION.head(_url_zip(ano, mes), timeout=15, allow_redirects=True)
        response.raise_for_status()

        last_modified = response.headers.get("Last-Modified")
        if not last_modified:
            return None

        dt = parsedate_to_datetime(last_modified)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception as e:
        logger.warning(f"Não foi possível verificar a atualização: {e}")
        return None


def _precisa_atualizar(ano, mes):
    if not _arquivo_zip_existe(ano, mes):
        return True

    if not _arquivo_csv_existe(ano, mes):
        return True

    servidor = _ultima_modificacao_servidor(ano, mes)
    if servidor is None:
        return False

    local = datetime.fromtimestamp(_zip_path(ano, mes).stat().st_mtime, tz=timezone.utc)
    return servidor.timestamp() > (local.timestamp() + 1)


# ---------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------

def _baixar_zip(ano, mes):
    _garantir_pasta()
    logger.info(f"Baixando {_nome_zip(ano, mes)}...")

    tmp_path = None

    try:
        with NamedTemporaryFile(delete=False, suffix=".tmp", dir=DATA_DIR) as tmp:
            tmp_path = Path(tmp.name)

            with SESSION.get(_url_zip(ano, mes), stream=True, timeout=TIMEOUT) as response:
                response.raise_for_status()
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        tmp.write(chunk)

        if not zipfile.is_zipfile(tmp_path):
            raise RuntimeError("Arquivo baixado inválido.")

        shutil.move(tmp_path, _zip_path(ano, mes))
        logger.info("Download concluído.")

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------
# Extração
# ---------------------------------------------------------------------

def _extrair_zip(ano, mes):
    logger.info("Extraindo arquivos...")

    csv = _csv_path(ano, mes)
    if csv.exists():
        csv.unlink(missing_ok=True)

    with zipfile.ZipFile(_zip_path(ano, mes), "r") as z:
        z.extractall(DATA_DIR)

    logger.info("Extração concluída.")


# ---------------------------------------------------------------------
# Localização do CSV
# ---------------------------------------------------------------------

def _localizar_csv(ano, mes):
    esperado = _csv_path(ano, mes)

    if esperado.exists():
        return str(esperado)

    csvs = sorted(DATA_DIR.glob("*.csv"))

    if not csvs:
        raise FileNotFoundError("Nenhum CSV encontrado.")

    for csv in csvs:
        try:
            with open(csv, encoding="latin1") as f:
                header = f.readline()

            if "CNPJ_FUNDO" in header and "DT_COMPTC" in header:
                return str(csv)
        except Exception:
            pass

    logger.warning("CSV principal não encontrado. Utilizando o primeiro disponível.")
    return str(csvs[0])


# ---------------------------------------------------------------------
# API Pública
# ---------------------------------------------------------------------

def download_informe_diario(ano=None, mes=None, force=False):
    hoje = datetime.now()

    if ano is None:
        ano = hoje.year

    if mes is None:
        mes = hoje.month

    _garantir_pasta()

    if force or _precisa_atualizar(ano, mes):
        logger.info("Atualizando Informe Diário...")
        _baixar_zip(ano, mes)
        _extrair_zip(ano, mes)
    else:
        logger.info("Informe Diário já está atualizado.")

    return _localizar_csv(ano, mes)


# ---------------------------------------------------------------------
# Histórico (janela móvel)
# ---------------------------------------------------------------------

def _meses_historico(quantidade=MESES_HISTORICO):
    hoje = datetime.now()
    ano = hoje.year
    mes = hoje.month

    meses = []
    for _ in range(quantidade):
        meses.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1

    return meses


def _remover_antigos(meses_validos):
    removidos = []

    validos = {_nome_csv(a, m) for a, m in meses_validos}
    validos.update({_nome_zip(a, m) for a, m in meses_validos})

    for arquivo in DATA_DIR.iterdir():
        if arquivo.is_file() and arquivo.name.startswith("inf_diario_fi_"):
            if arquivo.name not in validos:
                arquivo.unlink(missing_ok=True)
                removidos.append(arquivo.name)

    return removidos


def download_historico(anos=3, force=False):
    quantidade = anos * 12
    meses = _meses_historico(quantidade)

    baixados = []
    mantidos = []

    hoje = datetime.now()

    for ano, mes in meses:
        try:
            if ano == hoje.year and mes == hoje.month:
                caminho = download_informe_diario(
                    ano=ano,
                    mes=mes,
                    force=force,
                )
                if caminho not in baixados:
                    baixados.append(caminho)

            elif not _csv_path(ano, mes).exists():
                caminho = download_informe_diario(
                    ano=ano,
                    mes=mes,
                    force=False,
                )
                baixados.append(caminho)

            else:
                mantidos.append(str(_csv_path(ano, mes)))

        except Exception as e:
            logger.warning(f"{ano}-{mes:02d}: {e}")

    removidos = _remover_antigos(meses)

    return {
        "baixados": baixados,
        "mantidos": mantidos,
        "removidos": removidos,
    }


# ---------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    resultado = download_historico(anos=3)

    print()
    print("=" * 80)
    print("SINCRONIZAÇÃO DO INFORME DIÁRIO")
    print("=" * 80)

    print()
    print(f"Baixados : {len(resultado['baixados'])}")
    print(f"Mantidos : {len(resultado['mantidos'])}")
    print(f"Removidos: {len(resultado['removidos'])}")

    if resultado["baixados"]:
        print("\nArquivos baixados:")
        for arquivo in resultado["baixados"]:
            print(f"  + {arquivo}")

    if resultado["removidos"]:
        print("\nArquivos removidos:")
        for arquivo in resultado["removidos"]:
            print(f"  - {arquivo}")

    print()
    print("=" * 80)
    print("HISTÓRICO PRONTO")
    print("=" * 80)