# fundos/preparar_dados_ranking.py
"""
Prepara os dados MENSAIS (formato longo: uma linha por CNPJ + mês) dos fundos
da interseção e salva em um arquivo temporário (Parquet).

Este script NÃO calcula o ranking — apenas extrai e organiza, mês a mês, as
métricas relevantes de cada fundo (cota final, PL, cotistas, fluxo líquido).
O cálculo de ranking (retorno, volatilidade, Sharpe, etc.) deve ser feito
depois, lendo o arquivo gerado aqui via `carregar_dados_ranking()`.
"""

import atexit
import glob
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from .intersecao import carregar_interseccao_dataframe
from .informe_diario_coletor import DB_PATH

logger = logging.getLogger(__name__)

# SQLite tem um limite de ~999 variáveis por consulta (SQLITE_MAX_VARIABLE_NUMBER).
# Sem esse chunking, uma interseção grande de CNPJs pode estourar o limite.
CHUNK_CNPJS = 500

# Tempo (ms) que a conexão de LEITURA espera por um lock antes de desistir.
# Importante quando o banco está em pasta sincronizada (OneDrive/Dropbox) ou
# quando outro processo (ex.: o coletor atualizando os últimos meses) está
# escrevendo no mesmo arquivo ao mesmo tempo.
BUSY_TIMEOUT_MS = 30_000


def _conectar_leitura():
    conn = sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


def listar_meses_disponiveis():
    """Retorna lista de tuplas (ano, mes) com os meses disponíveis no banco de informes."""
    conn = _conectar_leitura()
    try:
        query = """
            SELECT DISTINCT strftime('%Y', Data_Competencia) AS ano,
                            strftime('%m', Data_Competencia) AS mes
            FROM informe_diario
            ORDER BY ano, mes
        """
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    return [(int(r["ano"]), int(r["mes"])) for _, r in df.iterrows()]


def _listar_por_mes_chunk(conn, data_inicio, data_fim, cnpjs_chunk):
    placeholders = ",".join(["?"] * len(cnpjs_chunk))
    query = f"""
        SELECT CNPJ_Classe, Data_Competencia, Valor_Cota, Patrimonio_Liquido,
               Numero_Cotistas, Captacao_Dia, Resgate_Dia
        FROM informe_diario
        WHERE Data_Competencia BETWEEN ? AND ?
          AND CNPJ_Classe IN ({placeholders})
    """
    params = [data_inicio, data_fim, *cnpjs_chunk]
    return pd.read_sql_query(query, conn, params=params)


def listar_por_mes(ano, mes, cnpjs):
    """
    Retorna dados do Informe Diário para um mês específico, filtrado pelos CNPJs
    informados. A lista de CNPJs é dividida em blocos de CHUNK_CNPJS para não
    estourar o limite de variáveis do SQLite.
    """
    if not cnpjs:
        return pd.DataFrame()

    data_inicio = f"{ano:04d}-{mes:02d}-01"
    if mes == 12:
        prox = f"{ano + 1:04d}-01-01"
    else:
        prox = f"{ano:04d}-{mes + 1:02d}-01"
    data_fim = (datetime.strptime(prox, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    conn = _conectar_leitura()
    try:
        partes = []
        for i in range(0, len(cnpjs), CHUNK_CNPJS):
            bloco = cnpjs[i:i + CHUNK_CNPJS]
            df_bloco = _listar_por_mes_chunk(conn, data_inicio, data_fim, bloco)
            if not df_bloco.empty:
                partes.append(df_bloco)
    finally:
        conn.close()

    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def extrair_metricas_mensais(df_mes):
    """
    A partir de um DataFrame com dados de um mês, extrai para cada CNPJ:
    - Última cota do mês
    - Último patrimônio líquido
    - Último número de cotistas
    - Captação líquida (Captacao_Dia - Resgate_Dia) acumulada no mês
    """
    if df_mes.empty:
        return pd.DataFrame()

    df_mes = df_mes.sort_values(["CNPJ_Classe", "Data_Competencia"])

    ultimo = (
        df_mes.groupby("CNPJ_Classe")
        .last()[["Valor_Cota", "Patrimonio_Liquido", "Numero_Cotistas"]]
        .reset_index()
        .rename(columns={
            "Valor_Cota": "Cota_Final",
            "Patrimonio_Liquido": "PL_Final",
            "Numero_Cotistas": "Cotistas_Final",
        })
    )

    fluxo = (
        df_mes.groupby("CNPJ_Classe")[["Captacao_Dia", "Resgate_Dia"]]
        .sum()
        .assign(Fluxo_Liquido_Mensal=lambda d: d["Captacao_Dia"] - d["Resgate_Dia"])
        .reset_index()[["CNPJ_Classe", "Fluxo_Liquido_Mensal"]]
    )

    return ultimo.merge(fluxo, on="CNPJ_Classe", how="left")


def preparar_dados_ranking(arquivo_saida=None, meses_limite=36):
    """
    Prepara os dados mensais (formato longo: uma linha por CNPJ + mês) para os
    fundos da interseção e salva em Parquet.

    Args:
        arquivo_saida (str, optional): Caminho de saída. Se None, cria um
            arquivo temporário .parquet (deletado automaticamente ao final
            do processo via atexit).
        meses_limite (int): Quantos meses (mais recentes) processar. Padrão
            36 (3 anos), alinhado ao histórico mantido pelo coletor. Use um
            valor menor (ex.: 12) se quiser um ranking baseado só no último ano.

    Returns:
        Path: Caminho do arquivo Parquet gerado.
    """
    df_cad = carregar_interseccao_dataframe()
    if df_cad.empty:
        raise ValueError("Interseção vazia.")
    cnpjs = df_cad["CNPJ_Classe"].tolist()
    logger.info("Total de CNPJs na interseção: %d", len(cnpjs))

    meses = listar_meses_disponiveis()
    if not meses:
        raise ValueError("Nenhum mês disponível no banco de informes.")

    meses_ordenados = sorted(sorted(meses, reverse=True)[:meses_limite])
    logger.info("Meses a processar: %s", meses_ordenados)

    linhas = []
    for ano, mes in meses_ordenados:
        logger.info("Processando %s-%02d...", ano, mes)
        try:
            df_mes = listar_por_mes(ano, mes, cnpjs)
        except Exception:
            # logger.exception grava o traceback completo — essencial para
            # descobrir a causa real (ex.: "database is locked",
            # "disk image is malformed", etc.) em vez de só "Execution failed".
            logger.exception("Erro ao carregar %s-%02d", ano, mes)
            continue

        if df_mes.empty:
            logger.info("  Sem dados para %s-%02d, pulando.", ano, mes)
            continue

        metricas = extrair_metricas_mensais(df_mes)
        if metricas.empty:
            continue

        metricas["Ano"] = ano
        metricas["Mes"] = mes
        metricas["Data_Referencia"] = f"{ano}-{mes:02d}-01"
        linhas.append(metricas)

    if not linhas:
        raise ValueError("Nenhum dado válido para gerar o arquivo de ranking.")

    df_final = pd.concat(linhas, ignore_index=True)
    df_final = df_final.sort_values(["CNPJ_Classe", "Ano", "Mes"]).reset_index(drop=True)
    logger.info("Total de linhas (CNPJ x mês): %d", len(df_final))

    if arquivo_saida is None:
        fd, caminho = tempfile.mkstemp(suffix=".parquet", prefix="dados_ranking_")
        os.close(fd)
        caminho = Path(caminho)
        atexit.register(lambda: caminho.unlink(missing_ok=True))
    else:
        caminho = Path(arquivo_saida)

    df_final.to_parquet(caminho, index=False)
    logger.info("Dados salvos em: %s", caminho)
    return caminho


def carregar_dados_ranking(arquivo=None):
    """
    Carrega os dados mensais preparados (formato longo) de um Parquet.
    Se `arquivo` for None, procura o temporário mais recente ou gera um novo.
    """
    if arquivo is None:
        tmp_files = glob.glob(os.path.join(tempfile.gettempdir(), "dados_ranking_*.parquet"))
        if tmp_files:
            arquivo = max(tmp_files, key=os.path.getctime)
        else:
            return preparar_dados_ranking()
    return pd.read_parquet(arquivo)


# ---------------------------------------------------------------------
# Teste rápido
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    caminho = preparar_dados_ranking(meses_limite=36)
    print(f"Arquivo gerado: {caminho}")
    df = pd.read_parquet(caminho)
    print(f"Shape: {df.shape}")
    print(df.head(10))
    print(df["CNPJ_Classe"].nunique(), "fundos distintos")