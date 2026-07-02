# renda_fixa/coletor.py
import logging
import requests
import pandas as pd
from io import StringIO
from datetime import datetime

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 1. INDICADORES (Selic e CDI) via SGS
# ──────────────────────────────────────────────────────────────

def coletar_indicadores():
    """
    Obtém Selic (Série 432) e calcula CDI (Selic - 0,1%).
    Retorna (selic_decimal, cdi_decimal).
    """
    try:
        url_selic = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        resp = requests.get(url_selic, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data:
            selic_raw = float(data[0]['valor'])
            # Se vier em percentual (ex: 14.25), converte para decimal
            if selic_raw > 1:
                selic = selic_raw / 100
            else:
                selic = selic_raw
            logger.info(f"Selic obtida via SGS: {selic:.2%}")
            # CDI = Selic - 0,1% (spread típico)
            cdi = max(selic - 0.001, 0.01)
            logger.info(f"CDI definido como {cdi:.2%}")
            return selic, cdi
    except Exception as e:
        logger.warning(f"Falha na SGS: {e}")

    # Fallback fixo (caso a API falhe)
    logger.warning("Usando valores fixos: Selic 10,5%, CDI 10,5%")
    return 0.105, 0.105


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

    except Exception as e:
        logger.error(f"Falha ao obter Tesouro via package_show: {e}")
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