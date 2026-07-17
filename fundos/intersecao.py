# fundos/intersecao.py
"""
Módulo para criar e gerenciar um arquivo temporário com os dados cadastrais
apenas dos fundos que possuem histórico no Informe Diário (interseção).
"""

import pandas as pd
from pathlib import Path
import tempfile
import atexit
import os

from .cadastro_coletor import listar_fundos_ativos
from .informe_diario_coletor import listar_cnpjs_distintos

# ---------------------------------------------------------------------
# Funções principais
# ---------------------------------------------------------------------

def criar_arquivo_interseccao(salvar_em=None):
    """
    Cria um arquivo CSV com os dados cadastrais apenas dos CNPJs que
    estão presentes tanto no cadastro ativo quanto no informe diário.

    Args:
        salvar_em (str, optional): Caminho para salvar o arquivo.
            Se não fornecido, usa um arquivo temporário.

    Returns:
        Path: Caminho do arquivo criado.
    """
    # 1. Obtém CNPJs do cadastro ativo
    df_cad = listar_fundos_ativos()
    if df_cad.empty:
        raise ValueError("Cadastro de fundos ativos está vazio.")

    # 2. Obtém CNPJs distintos do informe
    df_inf_cnpjs = listar_cnpjs_distintos()
    if df_inf_cnpjs.empty:
        raise ValueError("Banco de informes diários está vazio.")

    cnpjs_cad = set(df_cad["CNPJ_Classe"])
    cnpjs_inf = set(df_inf_cnpjs["CNPJ_Classe"])

    # 3. Interseção
    intersecao = cnpjs_cad.intersection(cnpjs_inf)
    if not intersecao:
        raise ValueError("Nenhum CNPJ em comum entre cadastro e informe.")

    # 4. Filtra o cadastro para manter apenas os CNPJs da interseção
    df_filtrado = df_cad[df_cad["CNPJ_Classe"].isin(intersecao)]

    # 5. Salva em arquivo
    if salvar_em is None:
        # Cria um arquivo temporário com extensão .csv
        fd, caminho = tempfile.mkstemp(suffix=".csv", prefix="interseccao_")
        os.close(fd)
        caminho = Path(caminho)
    else:
        caminho = Path(salvar_em)

    df_filtrado.to_csv(caminho, index=False, sep=";", encoding="utf-8-sig")

    # Registra para deletar automaticamente ao final do programa (se for temporário)
    if salvar_em is None:
        atexit.register(lambda: _deletar_arquivo(caminho))

    return caminho


def _deletar_arquivo(caminho):
    """Deleta o arquivo se existir."""
    if caminho.exists():
        caminho.unlink(missing_ok=True)


def apagar_arquivo_interseccao(caminho):
    """Deleta o arquivo de interseção manualmente."""
    _deletar_arquivo(Path(caminho))


def carregar_interseccao_dataframe():
    """
    Retorna um DataFrame com os dados cadastrais dos fundos que têm histórico.
    Útil para análises rápidas sem criar arquivo.
    """
    from .cadastro_coletor import listar_fundos_ativos
    from .informe_diario_coletor import listar_cnpjs_distintos

    df_cad = listar_fundos_ativos()
    if df_cad.empty:
        return pd.DataFrame()

    df_inf_cnpjs = listar_cnpjs_distintos()
    if df_inf_cnpjs.empty:
        return pd.DataFrame()

    cnpjs_cad = set(df_cad["CNPJ_Classe"])
    cnpjs_inf = set(df_inf_cnpjs["CNPJ_Classe"])
    intersecao = cnpjs_cad.intersection(cnpjs_inf)

    return df_cad[df_cad["CNPJ_Classe"].isin(intersecao)]


# ---------------------------------------------------------------------
# Exemplo de uso (teste rápido)
# ---------------------------------------------------------------------

if __name__ == "__main__":
    # Cria o arquivo
    caminho = criar_arquivo_interseccao()
    print(f"Arquivo criado em: {caminho}")

    # Carrega para ver
    df = pd.read_csv(caminho, sep=";", encoding="utf-8-sig")
    print(f"Total de fundos com histórico: {len(df)}")
    print(df.head())

    # Apaga manualmente (se não quiser esperar o atexit)
    # apagar_arquivo_interseccao(caminho)