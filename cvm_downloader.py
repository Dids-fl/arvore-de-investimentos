import requests
import zipfile
from pathlib import Path

# Cadastro oficial da CVM
URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"

ZIP_NAME = "registro_fundo_classe.zip"


def download_cadastro():
    print("Baixando cadastro da CVM...")

    response = requests.get(URL, timeout=120)
    response.raise_for_status()

    Path(ZIP_NAME).write_bytes(response.content)

    print("Download concluído.")

    print("Extraindo arquivos...")

    with zipfile.ZipFile(ZIP_NAME, "r") as zip_ref:
        zip_ref.extractall(".")

    print("Arquivos extraídos com sucesso!")