# renda_fixa/coletor.py
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def coletar_indicadores():
    """
    Obtém Selic e CDI atuais.
    Prioriza a Selic via Focus/SGS e define CDI = Selic - 0.1% (spread).
    Retorna (selic_decimal, cdi_decimal).
    """
    selic = None
    cdi = None

    # 1. Tenta Focus (mais confiável)
    try:
        url = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoTop5?$filter=Indicador%20eq%20'Selic'%20and%20tipoCalculado%20eq%20'C'&$top=1&$orderby=Data%20desc&$format=json"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get('value'):
            selic_raw = data['value'][0]['Media']
            # Se > 1, é percentual (ex: 14.25), divide por 100
            if selic_raw > 1:
                selic = selic_raw / 100
            else:
                selic = selic_raw
            logger.info(f"Selic obtida via Focus: {selic:.2%}")
    except Exception as e:
        logger.warning(f"Falha ao buscar Selic via Focus: {e}")

    # 2. Fallback: SGS para Selic
    if selic is None:
        try:
            url_selic = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
            resp = requests.get(url_selic, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if data:
                selic_raw = float(data[0]['valor'])
                if selic_raw > 1:
                    selic = selic_raw / 100
                else:
                    selic = selic_raw
                logger.info(f"Selic obtida via SGS: {selic:.2%}")
        except Exception as e:
            logger.warning(f"Falha ao buscar Selic via SGS: {e}")

    # 3. Se ainda não temos Selic, usa valor fixo
    if selic is None or selic < 0.01:
        logger.warning("Selic não obtida, usando valor fixo de 10,5% a.a.")
        selic = 0.105

    # 4. Define CDI como Selic - 0.1% (spread típico)
    cdi = selic - 0.001
    if cdi < 0.01:
        cdi = selic * 0.9  # fallback seguro

    logger.info(f"CDI definido como {cdi:.2%} (Selic {selic:.2%} - 0,1%)")
    return selic, cdi


def coletar_tesouro():
    """
    Obtém lista de títulos do Tesouro Direto via API CKAN.
    Retorna lista de dicionários ou None em caso de falha.
    """
    try:
        url = "https://www.tesourotransparente.gov.br/ckan/api/3/action/datastore_search?resource_id=df56aa73-08a1-4374-81fa-23656b1d2412&limit=100"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get('success'):
            records = data['result']['records']
            titulos = []
            for r in records:
                titulos.append({
                    'nome': r.get('titulo', 'Tesouro'),
                    'taxa': float(r.get('taxa_compra', 0)) if r.get('taxa_compra') else 0,
                    'vencimento': r.get('vencimento', ''),
                    'tipo': r.get('tipo_titulo', '')
                })
            logger.info(f"Tesouro: {len(titulos)} títulos obtidos")
            return titulos
    except Exception as e:
        logger.warning(f"Falha ao buscar Tesouro: {e}")
    return None