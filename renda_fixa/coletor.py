# renda_fixa/coletor.py
import logging
from io import StringIO

import pandas as pd
import requests

from utils.exceptions import DadosIndisponiveisError

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 1. INDICADORES (Selic e CDI) via SGS
# ──────────────────────────────────────────────────────────────

_URL_SGS_ULTIMO = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1"
    "?formato=json"
)
SGS_SELIC_META = 432
SGS_CDI_ANUAL = 4389  # CDI anualizado base 252 (% a.a.)


def _ultimo_valor_sgs(serie: int, rotulo: str) -> float:
    """Último valor de uma série SGS, convertido de % para decimal."""
    try:
        resp = requests.get(_URL_SGS_ULTIMO.format(serie=serie), timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise DadosIndisponiveisError(f"{rotulo} (BCB/SGS série {serie})", str(e)) from e

    if not data:
        raise DadosIndisponiveisError(
            f"{rotulo} (BCB/SGS série {serie})", "resposta vazia da API"
        )
    try:
        return float(str(data[0]["valor"]).replace(",", ".")) / 100
    except (KeyError, ValueError, TypeError, IndexError) as e:
        raise DadosIndisponiveisError(
            f"{rotulo} (BCB/SGS série {serie})", f"valor inválido na resposta: {e}"
        ) from e


def coletar_indicadores():
    """
    Obtém a meta Selic (SGS 432) e o CDI anualizado (SGS 4389).
    Retorna (selic_decimal, cdi_decimal).

    Se apenas a série do CDI falhar, o CDI é estimado como Selic − 0,10 p.p.
    (diferença histórica típica entre a meta e a taxa DI), com aviso no log.
    Se a Selic falhar, levanta DadosIndisponiveisError: não há número fixo
    de reserva.
    """
    selic = _ultimo_valor_sgs(SGS_SELIC_META, "SELIC")
    logger.info(f"Selic obtida via SGS: {selic:.2%}")

    try:
        cdi = _ultimo_valor_sgs(SGS_CDI_ANUAL, "CDI")
        logger.info(f"CDI obtido via SGS: {cdi:.2%}")
    except DadosIndisponiveisError as e:
        cdi = max(selic - 0.001, 0.0)
        logger.warning(f"CDI indisponível ({e}); estimado como Selic − 0,10 p.p.: {cdi:.2%}")
    return selic, cdi


# ──────────────────────────────────────────────────────────────
# 2. TESOURO DIRETO via package_show (MÉTODO ROBUSTO)
# ──────────────────────────────────────────────────────────────

def coletar_tesouro_via_package_show():
    """
    Consulta o CKAN do Tesouro Nacional via package_show,
    obtém dinamicamente a URL do arquivo CSV e retorna a lista de títulos.
    """
    try:
        # 1. Obtém os metadados do pacote (usando o slug permanente)
        url_package = (
            "https://www.tesourotransparente.gov.br/ckan/api/3/action/"
            "package_show?id=taxas-dos-titulos-ofertados-pelo-tesouro-direto"
        )
        resp = requests.get(url_package, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('success'):
            logger.error("Falha na requisição package_show")
            return None

        # 2. Localiza o recurso CSV correto (filtro robusto)
        resources = data['result']['resources']
        csv_resource = None
        for r in resources:
            formato = r.get('format', '').upper()
            nome = r.get('url', '').lower()
            # Garante que é CSV e que contém o nome esperado
            if formato == 'CSV' and 'precotaxatesourodireto' in nome:
                csv_resource = r
                break

        if not csv_resource:
            logger.error("Nenhum recurso CSV encontrado no pacote")
            return None

        # 3. Baixa o arquivo CSV
        csv_url = csv_resource['url']
        logger.info(f"Baixando CSV via package_show: {csv_url}")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(csv_url, headers=headers, timeout=15)
        response.raise_for_status()

        # 4. Lê o CSV (separador ; e vírgula como decimal)
        df = pd.read_csv(StringIO(response.text), sep=";", decimal=",")

        # 5. Converte e filtra a data mais recente
        df['Data Base'] = pd.to_datetime(df['Data Base'], format='%d/%m/%Y')
        data_mais_recente = df['Data Base'].max()
        df_atual = df[df['Data Base'] == data_mais_recente]

        # 6. Converte para o formato esperado pelo sistema
        titulos = []
        for _, row in df_atual.iterrows():
            tipo = row['Tipo Titulo']
            # Define o indexador
            if 'IPCA' in tipo:
                indexador = 'IPCA'
            elif 'Selic' in tipo:
                indexador = 'SELIC'
            elif 'Prefixado' in tipo:
                indexador = 'Prefixado'
            else:
                indexador = 'Outro'

            # Taxa de compra (já vem em percentual, ex: 6,50 → 6.50)
            taxa_str = str(row['Taxa Compra Manha']).replace(',', '.')
            taxa = float(taxa_str) / 100   # sempre divide por 100 para decimal

            titulos.append({
                'nome': row['Tipo Titulo'],
                'taxa': taxa,
                'vencimento': row['Data Vencimento'],
                'tipo': indexador,
                'data_base': data_mais_recente.strftime('%Y-%m-%d')
            })

        logger.info(f"Tesouro via package_show: {len(titulos)} títulos obtidos (base {data_mais_recente.date()})")
        return titulos

    except (
        requests.RequestException,
        pd.errors.ParserError,
        KeyError,
        TypeError,
        ValueError,
    ) as e:
        logger.error("Falha ao obter Tesouro via package_show: %s", e)
        return None


# ──────────────────────────────────────────────────────────────
# 3. WRAPPER (fallback automático)
# ──────────────────────────────────────────────────────────────

def coletar_tesouro():
    """
    Função pública para obter títulos do Tesouro.
    Tenta package_show; se falhar, retorna None (o ranker usará fallback).
    """
    return coletar_tesouro_via_package_show()