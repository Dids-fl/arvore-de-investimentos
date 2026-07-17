# fundos/preparar_dados_ranking.py
"""
Script para extrair dados mensais dos informes diários para cada CNPJ da interseção,
agregar métricas relevantes e salvar em um arquivo temporário para uso posterior no ranking.
"""

import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import logging
import tempfile
import atexit
import os

from .intersecao import carregar_interseccao_dataframe
from .informe_diario_coletor import DB_PATH

logger = logging.getLogger(__name__)


def listar_meses_disponiveis():
    """Retorna lista de tuplas (ano, mes) com os meses disponíveis no banco de informes."""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT DISTINCT strftime('%Y', Data_Competencia) as ano, strftime('%m', Data_Competencia) as mes FROM informe_diario ORDER BY ano, mes"
    df = pd.read_sql_query(query, conn)
    conn.close()
    meses = [(int(row['ano']), int(row['mes'])) for _, row in df.iterrows()]
    return meses


def listar_por_mes(ano, mes, cnpjs=None):
    """
    Retorna dados do Informe Diário para um mês específico, opcionalmente filtrado por CNPJs.
    """
    conn = sqlite3.connect(DB_PATH)
    data_inicio = f"{ano:04d}-{mes:02d}-01"
    if mes == 12:
        data_fim = f"{ano+1:04d}-01-01"
    else:
        data_fim = f"{ano:04d}-{mes+1:02d}-01"
    data_fim = (datetime.strptime(data_fim, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    query = """
        SELECT CNPJ_Classe, Data_Competencia, Valor_Cota, Patrimonio_Liquido, Numero_Cotistas,
               Captacao_Dia, Resgate_Dia
        FROM informe_diario
        WHERE Data_Competencia BETWEEN ? AND ?
    """
    params = [data_inicio, data_fim]

    if cnpjs:
        placeholders = ",".join(["?" for _ in cnpjs])
        query += f" AND CNPJ_Classe IN ({placeholders})"
        params.extend(cnpjs)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


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

    # Ordena por data para garantir que o último registro seja o mais recente
    df_mes = df_mes.sort_values(["CNPJ_Classe", "Data_Competencia"])

    # Agrupa por CNPJ e pega o último registro de cada mês
    ultimo = df_mes.groupby("CNPJ_Classe").last().reset_index()
    ultimo = ultimo[["CNPJ_Classe", "Valor_Cota", "Patrimonio_Liquido", "Numero_Cotistas"]]
    ultimo.rename(columns={
        "Valor_Cota": "Cota_Final",
        "Patrimonio_Liquido": "PL_Final",
        "Numero_Cotistas": "Cotistas_Final"
    }, inplace=True)

    # Calcula captação líquida mensal
    captacao = df_mes.groupby("CNPJ_Classe").apply(
        lambda g: (g["Captacao_Dia"].sum() - g["Resgate_Dia"].sum())
    ).reset_index(name="Fluxo_Liquido_Mensal")

    # Junta as métricas
    metricas = ultimo.merge(captacao, on="CNPJ_Classe", how="left")
    return metricas


def preparar_dados_ranking(arquivo_saida=None, meses_limite=12):
    """
    Prepara os dados agregados para ranking.
    
    Args:
        arquivo_saida (str, optional): Caminho para salvar o arquivo. 
            Se None, usa um arquivo temporário que será deletado ao final.
        meses_limite (int): Número máximo de meses a considerar (mais recentes).
    
    Returns:
        Path: Caminho do arquivo salvo.
    """
    # 1. Obtém CNPJs da interseção
    df_cad = carregar_interseccao_dataframe()
    if df_cad.empty:
        raise ValueError("Interseção vazia.")
    cnpjs = df_cad["CNPJ_Classe"].tolist()
    logger.info(f"Total de CNPJs na interseção: {len(cnpjs)}")

    # 2. Lista meses disponíveis
    meses = listar_meses_disponiveis()
    if not meses:
        raise ValueError("Nenhum mês disponível no banco de informes.")
    
    # Pega apenas os últimos 'meses_limite' meses
    meses = sorted(meses, reverse=True)[:meses_limite]
    meses_ordenados = sorted(meses)  # ordem cronológica para cálculo de retorno
    logger.info(f"Meses a processar: {meses_ordenados}")

    # 3. Dicionário para acumular séries temporais por CNPJ
    series = {cnpj: {"datas": [], "cotas": [], "pl": [], "cotistas": [], "fluxo": []} for cnpj in cnpjs}

    # 4. Processa mês a mês (na ordem cronológica)
    for ano, mes in meses_ordenados:
        logger.info(f"Processando {ano}-{mes:02d}...")
        try:
            df_mes = listar_por_mes(ano, mes, cnpjs)
        except Exception as e:
            logger.warning(f"Erro ao carregar {ano}-{mes:02d}: {e}")
            continue

        if df_mes.empty:
            continue

        # Extrai métricas mensais
        metricas = extrair_metricas_mensais(df_mes)
        if metricas.empty:
            continue

        # Adiciona aos dicionários
        data_ref = f"{ano}-{mes:02d}-01"
        for _, row in metricas.iterrows():
            cnpj = row["CNPJ_Classe"]
            if cnpj not in series:
                continue
            series[cnpj]["datas"].append(data_ref)
            series[cnpj]["cotas"].append(row["Cota_Final"])
            series[cnpj]["pl"].append(row["PL_Final"])
            series[cnpj]["cotistas"].append(row["Cotistas_Final"])
            series[cnpj]["fluxo"].append(row["Fluxo_Liquido_Mensal"])

    # 5. Constrói DataFrame final com métricas agregadas por CNPJ
    dados = []
    for cnpj, s in series.items():
        if len(s["datas"]) == 0:
            continue
        
        # Últimos valores (mês mais recente)
        ult_cota = s["cotas"][-1]
        ult_pl = s["pl"][-1]
        ult_cotistas = s["cotistas"][-1]
        
        # Retorno acumulado no período (último mês / primeiro mês - 1)
        if len(s["cotas"]) >= 2:
            cota_inicial = s["cotas"][0]
            cota_final = s["cotas"][-1]
            if cota_inicial != 0:
                retorno_periodo = (cota_final / cota_inicial) - 1
            else:
                retorno_periodo = None
        else:
            retorno_periodo = None
        
        # Fluxo líquido total
        fluxo_total = sum(s["fluxo"])
        
        # Patrimônio médio
        pl_medio = sum(s["pl"]) / len(s["pl"]) if s["pl"] else 0
        
        dados.append({
            "CNPJ_Classe": cnpj,
            "Cota_Atual": ult_cota,
            "PL_Atual": ult_pl,
            "Cotistas_Atuais": ult_cotistas,
            "Retorno_Periodo": retorno_periodo,
            "Fluxo_Liquido_Total": fluxo_total,
            "PL_Medio": pl_medio,
            "Meses_Historico": len(s["datas"]),
            "Series_Cotas": s["cotas"],
            "Series_Datas": s["datas"],
        })

    df_final = pd.DataFrame(dados)
    logger.info(f"Total de fundos com dados agregados: {len(df_final)}")

    if df_final.empty:
        raise ValueError("Nenhum dado válido para gerar ranking.")

    # 6. Salva em arquivo
    if arquivo_saida is None:
        # Cria arquivo temporário com extensão .parquet
        fd, caminho = tempfile.mkstemp(suffix=".parquet", prefix="dados_ranking_")
        os.close(fd)
        caminho = Path(caminho)
        atexit.register(lambda: caminho.unlink(missing_ok=True))
    else:
        caminho = Path(arquivo_saida)

    # Salva em formato Parquet (compacto e rápido)
    df_final.to_parquet(caminho, index=False)
    logger.info(f"Dados salvos em: {caminho}")
    return caminho


def carregar_dados_ranking(arquivo=None):
    """
    Carrega os dados de ranking de um arquivo (parquet) e retorna um DataFrame.
    Se arquivo for None, tenta carregar de um arquivo temporário existente ou chama preparar_dados_ranking().
    """
    if arquivo is None:
        # Tenta encontrar um arquivo temporário (ex: dados_ranking_*.parquet)
        import glob
        tmp_files = glob.glob("dados_ranking_*.parquet")
        if tmp_files:
            arquivo = max(tmp_files, key=os.path.getctime)
        else:
            return preparar_dados_ranking()
    return pd.read_parquet(arquivo)


# ---------------------------------------------------------------------
# Teste rápido
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    caminho = preparar_dados_ranking(meses_limite=6)
    print(f"Arquivo gerado: {caminho}")
    df = pd.read_parquet(caminho)
    print(f"Shape: {df.shape}")
    print(df.head())