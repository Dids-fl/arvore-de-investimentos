"""
Busca dinâmica de produtos de Renda Fixa em fontes online.
Substitui a lista fixa de spreads por dados reais do mercado.

Fontes:
  - Tesouro Direto (API oficial com data)
  - Yubb (agregador de CDB/LCI/LCA) – scraping com seletores robustos
  - B3 (CRI/CRA e Debêntures) – scraping
  - Fallback fixo via rf_mercado
"""

import time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from datetime import datetime
import re

from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Cache ──────────────────────────────────────────────────────────────────────
_CACHE_RF = None
_CACHE_TTL = 3600  # 1 hora
_CACHE_TIMESTAMP = 0

# ── Parâmetros de segurança e liquidez ──────────────────────────────────────
BONUS_SEGURANCA = {
    "Governo federal": 8,
    "FGC": 5,
    "FGC até R$250k": 5,
    "Sem FGC": 0,
    "Sem garantia": 0,
}
BONUS_LIQUIDEZ = {
    "Diária": 4,
    "D+1": 4,
    "D+0": 4,
    "D+0/D+1": 4,
    "Carência mínima": 2,
    "Até 1 ano": 2,
    "Secundária": 0,
    "Restrita": 0,
}
IR_LONG_PRAZO = 0.15

# ── Funções auxiliares ────────────────────────────────────────────────────────

def _parse_float(val: str) -> float:
    if not val:
        return 0.0
    val = val.replace('%', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(val)
    except:
        return 0.0

def _calcular_retorno_real(ret_bruto: float, ipca: float, deducoes: float = 0,
                           ir: float = 0.15, isento_ir: bool = False) -> float:
    ganho = ret_bruto - deducoes
    if isento_ir:
        ret_liq = ganho
    else:
        ret_liq = deducoes + ganho * (1 - ir)
    return (1 + ret_liq) / (1 + ipca) - 1

# ── 1. Tesouro Direto (API oficial com data) ──────────────────────────────────

def get_tesouro_direto() -> List[Dict]:
    try:
        hoje = datetime.now().strftime("%Y-%m-%d")
        url = f"https://www.tesourotransparente.gov.br/ckan/api/3/action/td_json?data={hoje}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        titulos = data.get("result", {}).get("data", [])
        produtos = []
        for item in titulos:
            titulo = item.get("Titulo", "")
            if not titulo:
                continue
            taxa_str = item.get("TaxaCompra", "0")
            taxa = float(taxa_str.replace(',', '.')) if taxa_str else 0.0
            tipo = "SELIC" if "SELIC" in titulo else "IPCA+" if "IPCA" in titulo else "Prefixado"
            produtos.append({
                "ticker": f"TD-{tipo}",
                "nome": titulo,
                "taxa_bruta": taxa / 100.0,
                "vencimento": item.get("Vencimento", ""),
                "garantia": "Governo federal",
                "liquidez": "D+1",
                "ir": "15% sobre ganhos (>720 dias)",
                "isento_ir": False,
                "tipo": tipo,
            })
        logger.info(f"Tesouro Direto: {len(produtos)} títulos encontrados.")
        return produtos
    except Exception as e:
        logger.warning(f"Erro ao buscar Tesouro Direto: {e}")
        return []

# ── 2. Yubb (agregador de CDB/LCI/LCA) ──────────────────────────────────────

def get_yubb_renda_fixa() -> List[Dict]:
    try:
        url = "https://www.yubb.com.br/renda-fixa"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        produtos = []
        # Tenta diferentes seletores
        table = (soup.find('table', {'class': 'table'}) or
                 soup.find('table', {'id': 'table'}) or
                 soup.find('table', {'class': 'table-striped'}) or
                 soup.find('table'))
        if not table:
            logger.warning("Yubb: tabela não encontrada.")
            return []
        rows = table.find_all('tr')[1:]
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 6:
                continue
            tipo = cols[0].text.strip()
            nome = cols[1].text.strip()
            taxa_str = cols[2].text.strip()
            prazo = cols[3].text.strip()
            garantia_text = cols[4].text.strip()
            liquidez_text = cols[5].text.strip()

            taxa = _parse_float(taxa_str) / 100.0
            isento = "LCI" in tipo or "LCA" in tipo
            garantia = "FGC" if "FGC" in garantia_text else "Sem FGC"
            liquidez = "Diária" if "Diária" in liquidez_text else "Carência"
            ticker = f"{tipo.replace(' ', '')[:4]}{prazo[:3]}"

            produtos.append({
                "ticker": ticker,
                "nome": f"{tipo} {nome}",
                "taxa_bruta": taxa,
                "prazo": prazo,
                "garantia": garantia,
                "liquidez": liquidez,
                "ir": "ISENTO" if isento else "15% sobre ganhos (>720 dias)",
                "isento_ir": isento,
                "tipo": tipo,
            })
        logger.info(f"Yubb: {len(produtos)} produtos encontrados.")
        return produtos
    except Exception as e:
        logger.warning(f"Erro ao buscar Yubb: {e}")
        return []

# ── 3. B3 – CRI/CRA e Debêntures ─────────────────────────────────────────────

def get_b3_cri_cra() -> List[Dict]:
    try:
        url = "https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-fixa/agro-e-imobiliarios/lista-completa.htm"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        produtos = []
        table = soup.find('table', {'class': 'table'}) or soup.find('table')
        if not table:
            return []
        for row in table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) < 4:
                continue
            nome = cols[0].text.strip()
            tipo = cols[1].text.strip()
            taxa_str = cols[2].text.strip()
            vencimento = cols[3].text.strip()
            taxa = _parse_float(taxa_str) / 100.0
            produtos.append({
                "ticker": f"{tipo[:3]}{nome[:4]}",
                "nome": f"{tipo} {nome}",
                "taxa_bruta": taxa,
                "vencimento": vencimento,
                "garantia": "Sem FGC",
                "liquidez": "Secundária",
                "ir": "ISENTO",
                "isento_ir": True,
                "tipo": tipo,
            })
        logger.info(f"B3 CRI/CRA: {len(produtos)} produtos encontrados.")
        return produtos
    except Exception as e:
        logger.warning(f"Erro ao buscar B3 CRI/CRA: {e}")
        return []

def get_b3_debentures() -> List[Dict]:
    try:
        url = "https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-fixa/debentures/"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        produtos = []
        table = soup.find('table', {'class': 'table'}) or soup.find('table')
        if not table:
            return []
        for row in table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) < 4:
                continue
            nome = cols[0].text.strip()
            emissor = cols[1].text.strip() if len(cols) > 1 else ""
            taxa_str = cols[2].text.strip() if len(cols) > 2 else "0"
            vencimento = cols[3].text.strip() if len(cols) > 3 else ""
            taxa = _parse_float(taxa_str) / 100.0
            isenta = "incentivada" in nome.lower() or "Lei 12.431" in nome.lower()
            produtos.append({
                "ticker": f"DEB{nome[:4]}",
                "nome": f"{nome} {emissor}".strip(),
                "taxa_bruta": taxa,
                "vencimento": vencimento,
                "garantia": "Sem FGC",
                "liquidez": "Secundária",
                "ir": "ISENTO" if isenta else "15% sobre ganhos",
                "isento_ir": isenta,
                "tipo": "Debênture",
            })
        logger.info(f"B3 Debêntures: {len(produtos)} produtos encontrados.")
        return produtos
    except Exception as e:
        logger.warning(f"Erro ao buscar B3 Debêntures: {e}")
        return []

# ── 4. Função principal ──────────────────────────────────────────────────────

def get_all_rf_products() -> List[Dict]:
    global _CACHE_RF, _CACHE_TIMESTAMP

    if _CACHE_RF is not None and (time.time() - _CACHE_TIMESTAMP) < _CACHE_TTL:
        return _CACHE_RF

    produtos = []
    produtos.extend(get_tesouro_direto())
    produtos.extend(get_yubb_renda_fixa())
    produtos.extend(get_b3_cri_cra())
    produtos.extend(get_b3_debentures())

    # Remove duplicatas
    vistos = set()
    unicos = []
    for p in produtos:
        key = (p.get("ticker"), p.get("nome"))
        if key not in vistos:
            vistos.add(key)
            unicos.append(p)

    _CACHE_RF = unicos
    _CACHE_TIMESTAMP = time.time()
    logger.info(f"Total de produtos RF dinâmicos: {len(unicos)}")
    return unicos

# ── 5. Ranking RF ─────────────────────────────────────────────────────────────

def rankear_rf(perfil: int, n: int = 5, selic: float = 0.1425, ipca: float = 0.044) -> List[Dict]:
    produtos = get_all_rf_products()
    if not produtos:
        logger.warning("Nenhum produto RF encontrado. Usando fallback fixo.")
        from rf_fundos.rf_mercado import calcular_rf as fallback_rf
        fallback = fallback_rf(selic, ipca)
        permitidos = {
            1: ["SELIC", "CDB-DI", "LCI/LCA"],
            2: ["SELIC", "CDB-DI", "LCI/LCA", "IPCA+", "DEBN"],
            3: ["IPCA+", "DEBN", "CRI/CRA", "CDB-DI"],
        }
        filtrados = [p for p in fallback if p.get("ticker") in permitidos.get(perfil, [])]
        return sorted(filtrados, key=lambda x: -x.get("score", 0))[:n]

    # Calcula score para cada produto
    for p in produtos:
        taxa_bruta = p.get("taxa_bruta", 0)
        if taxa_bruta == 0:
            p["score"] = 0
            continue

        isento = p.get("isento_ir", False)
        ir = 0 if isento else IR_LONG_PRAZO
        ret_real = _calcular_retorno_real(taxa_bruta, ipca, 0, ir, isento)

        bonus_seg = BONUS_SEGURANCA.get(p.get("garantia", ""), 0)
        bonus_liq = BONUS_LIQUIDEZ.get(p.get("liquidez", ""), 0)
        score = (ret_real * 100 * 6) + bonus_seg + bonus_liq
        p["score"] = round(max(0, min(100, score)), 1)
        p["ret_real_pct"] = round(ret_real * 100, 2)
        p["ret_bruto_pct"] = round(taxa_bruta * 100, 2)

    # Filtra por perfil
    if perfil == 1:
        filtrados = [p for p in produtos if p.get("garantia") in ["Governo federal", "FGC"] and p.get("liquidez") in ["Diária", "D+1", "D+0"]]
    elif perfil == 2:
        filtrados = [p for p in produtos if p.get("liquidez") != "Restrita"]
    else:
        filtrados = produtos

    return sorted(filtrados, key=lambda x: -x.get("score", 0))[:n]