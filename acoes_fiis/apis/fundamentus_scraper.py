"""
Módulo para extrair dados fundamentalistas do Fundamentus.com.br
e lista de tickers da B3, sem salvar arquivos intermediários.
"""

from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Cabeçalho para evitar bloqueio
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

BASE_URL = 'http://www.fundamentus.com.br'

# ── Funções auxiliares ──────────────────────────────────────────────────────

def _to_float(val) -> float:
    """Converte string do Fundamentus (com . e ,) para float."""
    if val is None:
        return 0.0
    s = str(val).strip().replace(" ", "")
    if not s or s in ("-", "?", "N/A", ""):
        return 0.0
    s = s.replace("%", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0

def get_raw_data(url: str) -> bytes:
    """Faz requisição HTTP e retorna o conteúdo."""
    r = requests.get(url, headers=HEADERS)
    r.encoding = 'utf-8'
    if r.status_code != 200:
        raise RuntimeError(f"Falha ao acessar {url}, status: {r.status_code}")
    return r.content

# ── 1. Bulk: todas as ações em UMA requisição ──────────────────────────────

def get_all_bulk() -> dict[str, dict]:
    """
    Scraping de resultado.php — retorna TODAS as ações em UMA requisição.
    NÃO imprime nada. Retorna {} se falhar.
    """
    try:
        url = f"{BASE_URL}/resultado.php"
        html = get_raw_data(url)
        soup = BeautifulSoup(html, features="html.parser")  # html.parser é mais seguro

        table = soup.find("table", {"id": "resultado"})
        if not table:
            return {}

        # Usa pandas para ler a tabela diretamente
        df = pd.read_html(
            StringIO(str(table)),
            decimal=',',
            thousands='.',
        )[0]

        # Mapeamento de colunas (cabeçalho em português → campo interno)
        col_map = {
            'Papel': 'ticker',
            'Cotação': 'cotacao',
            'P/L': 'pl',
            'P/VP': 'pvp',
            'PSR': 'psr',
            'Div.Yield': 'dy',
            'P/Ativo': 'p_ativo',
            'P/Cap.Giro': 'p_cap_giro',
            'P/EBIT': 'p_ebit',
            'P/Ativ Circ.Liq': 'p_acl',
            'EV/EBIT': 'ev_ebit',
            'EV/EBITDA': 'ev_ebitda',
            'Mrg Ebit': 'margem_ebit',
            'Mrg. Líq.': 'margem_liquida',
            'Liq. Corr.': 'liq_corrente',
            'ROIC': 'roic',
            'ROE': 'roe',
            'Liq.2meses': 'liquidez',
            'Patrim. Líq': 'patrimônio',
            'Dív.Líq/ Patrim.': 'divida_patrimônio',
            'Cresc. Rec.5a': 'receita_cagr_5a',
        }

        resultado = {}
        for _, row in df.iterrows():
            entry = {}
            for col_pt, col_en in col_map.items():
                if col_pt in df.columns:
                    val = row[col_pt]
                    if col_pt == 'Papel':
                        entry[col_en] = str(val).strip().upper()
                    else:
                        entry[col_en] = _to_float(val)

            ticker = entry.get('ticker', '')
            if ticker and ticker.isalnum() and len(ticker) <= 7:
                resultado[ticker] = entry

        return resultado

    except (requests.exceptions.RequestException, TypeError, ValueError, AttributeError, OSError):
        return {}

# ── 2. Detalhe: dados específicos de um ticker ─────────────────────────────

def get_fundamentus_data(ticker: str) -> dict[str, str]:
    """
    Extrai dados fundamentalistas detalhados de um ticker específico.
    Retorna {} se falhar.
    """
    try:
        url = f'{BASE_URL}/detalhes.php?papel={ticker}'
        html = get_raw_data(url)
        soup = BeautifulSoup(html, features="html.parser")
        tables = soup.findAll("table")
        if not tables:
            return {}

        df_list = pd.read_html(StringIO(str(tables).replace('?', '')), decimal=',', thousands='.')
        df_final = pd.concat(df_list, ignore_index=True)

        json_data = {}
        for i in range(0, df_final.shape[1], 2):
            keys = df_final.iloc[:, i]
            values = df_final.iloc[:, i + 1]
            for key, value in zip(keys, values):
                if pd.notna(key) and pd.notna(value):
                    json_data[key] = value

        return json_data

    except (requests.exceptions.RequestException, TypeError, ValueError, AttributeError, OSError):
        return {}

# ── 3. Lista de tickers ─────────────────────────────────────────────────────

def get_all_tickers() -> list[dict[str, str]]:
    bulk = get_all_bulk()
    return [{'codigo': t, 'nome': '', 'razao_social': ''} for t in bulk]

def get_ticker_list() -> list[str]:
    return list(get_all_bulk().keys())

# ── 4. FIIs (universo dedicado; nunca inferido apenas pelo ticker) ─────────

def get_fiis_bulk() -> dict[str, dict]:
    """Carrega exclusivamente a tabela dedicada de fundos imobiliários."""
    try:
        html = get_raw_data(f"{BASE_URL}/fii_resultado.php")
        soup = BeautifulSoup(html, features="html.parser")
        tabela = soup.find("table", {"id": "resultado"})
        if not tabela:
            return {}
        dataframe = pd.read_html(
            StringIO(str(tabela)),
            decimal=",",
            thousands=".",
        )[0]
        dataframe.columns = [str(coluna).strip() for coluna in dataframe.columns]
        colunas = {
            "Papel": "ticker",
            "Segmento": "tipo",
            "Cotação": "cotacao",
            "Dividend Yield": "dy",
            "Div.Yield": "dy",
            "P/VP": "pvp",
            "Liquidez": "liquidez",
            "Liquidez 2 meses": "liquidez",
            "Vacância Média": "vacancia",
            "Valor de Mercado": "valor_mercado",
        }
        resultado: dict[str, dict] = {}
        for _, linha in dataframe.iterrows():
            item = {
                "tipo_ativo": "fii",
                "fonte_classificacao": "Fundamentus/FIIs",
            }
            for origem, destino in colunas.items():
                if origem not in dataframe.columns:
                    continue
                valor = linha[origem]
                item[destino] = (
                    str(valor).strip().upper()
                    if destino == "ticker"
                    else str(valor).strip()
                    if destino == "tipo"
                    else _to_float(valor)
                )
            ticker = item.get("ticker", "")
            if ticker and ticker.isalnum() and len(ticker) <= 7:
                resultado[ticker] = item
        return resultado
    except (
        requests.exceptions.RequestException,
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        OSError,
    ):
        return {}
