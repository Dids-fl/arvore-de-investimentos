# renda_fixa/scraper_yubb.py
import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def scraper_yubb():
    """
    Faz scraping da página de renda fixa do Yubb.
    Retorna lista de dicionários no formato:
    {
        "ticker": str,
        "nome": str,
        "emissor": str,
        "tipo": "CDB"|"LCI"|"LCA",
        "taxa_bruta": float,  # spread em decimal (ex: 1.15 para 115% do CDI)
        "vencimento": "YYYY-MM-DD",
        "garantia": "FGC" ou "Sem FGC",
        "liquidez": str,
        "ir": "ISENTO" ou "15% (>720d)",
        "isento_ir": bool,
        "prazo_dias": int,
        "fonte": "Yubb"
    }
    """
    url = "https://yubb.com.br/investimentos"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    produtos = []
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ajuste os seletores conforme a estrutura atual do Yubb
        cards = soup.select('div.investment-card')  # exemplo, pode mudar
        
        for card in cards:
            try:
                emissor = card.select_one('div.emissor').text.strip()
                titulo = card.select_one('div.titulo').text.strip()
                taxa_text = card.select_one('div.taxa').text.strip()
                prazo_text = card.select_one('div.prazo').text.strip()
                
                taxa = extrair_taxa(taxa_text)          # retorna float (ex: 1.15)
                dias = extrair_prazo_em_dias(prazo_text)
                vencimento = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
                garantia = "FGC" if "FGC" in card.text else "Sem FGC"
                liquidez = card.select_one('div.liquidez')
                liquidez_text = liquidez.text.strip() if liquidez else "Diária"
                tipo = identificar_tipo(titulo)
                isento = tipo in ['LCI', 'LCA']
                
                produtos.append({
                    "ticker": f"{tipo}-{emissor[:5]}-{dias}",
                    "nome": titulo,
                    "emissor": emissor,
                    "tipo": tipo,
                    "taxa_bruta": taxa,   # spread (ex: 1.15)
                    "vencimento": vencimento,
                    "garantia": garantia,
                    "liquidez": liquidez_text,
                    "ir": "ISENTO" if isento else "15% (>720d)",
                    "isento_ir": isento,
                    "prazo_dias": dias,
                    "fonte": "Yubb"
                })
            except Exception as e:
                logger.warning(f"Erro ao parsear card: {e}")
                continue
        
        logger.info(f"Scraping Yubb: {len(produtos)} produtos encontrados.")
        return produtos
        
    except Exception as e:
        logger.error(f"Erro no scraping Yubb: {e}")
        return None

def extrair_taxa(texto):
    texto = texto.replace(',', '.').strip()
    match = re.search(r'(\d+[,.]?\d*)%?\s*do\s*CDI', texto, re.IGNORECASE)
    if match:
        return float(match.group(1)) / 100  # retorna 1.15 para 115%
    match = re.search(r'(\d+[,.]?\d*)%', texto)
    if match:
        return float(match.group(1)) / 100  # retorna 0.115 para 11.5%
    return 0.0

def extrair_prazo_em_dias(texto):
    texto = texto.lower().strip()
    if 'ano' in texto:
        anos = float(re.search(r'(\d+[,.]?\d*)', texto).group(1))
        return int(anos * 365)
    elif 'mês' in texto or 'mes' in texto:
        meses = float(re.search(r'(\d+[,.]?\d*)', texto).group(1))
        return int(meses * 30)
    elif 'dia' in texto:
        dias = float(re.search(r'(\d+[,.]?\d*)', texto).group(1))
        return int(dias)
    return 365

def identificar_tipo(titulo):
    titulo = titulo.upper()
    if "LCI" in titulo:
        return "LCI"
    elif "LCA" in titulo:
        return "LCA"
    elif "CDB" in titulo:
        return "CDB"
    elif "RDB" in titulo:
        return "RDB"
    return "Renda Fixa"