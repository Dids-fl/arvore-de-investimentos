# renda_fixa/ranker.py
import logging
import random
from datetime import datetime, timedelta
from .coletor import coletar_indicadores, coletar_tesouro
from .fallback import get_fallback

try:
    from .scraper_yubb import scraper_yubb
except ImportError:
    scraper_yubb = None
    logging.warning("scraper_yubb não disponível. Instale BeautifulSoup e requests.")

logger = logging.getLogger(__name__)

# Emissores fictícios para produtos gerados (caso Yubb não retorne)
EMISSORES_FICTICIOS = [
    "Banco XP", "BTG Pactual", "Banco Inter", "Nu Invest",
    "C6 Bank", "Banco Sofisa", "Banco Original", "Banco Pan",
    "Banco Daycoval", "ModalMais", "Will Bank", "RCI Brasil"
]

def _calcular_prazo_dias(vencimento):
    if not vencimento:
        return 9999
    try:
        if isinstance(vencimento, str):
            venc = datetime.strptime(vencimento, "%Y-%m-%d")
        else:
            venc = vencimento
        hoje = datetime.now()
        return max((venc - hoje).days, 1)
    except Exception:
        return 9999

def _calcular_score(produto, perfil, cdi_atual):
    taxa = produto.get("taxa_bruta", 0.0)
    isento = produto.get("isento_ir", False)
    garantia = produto.get("garantia", "Sem garantia")
    liquidez = produto.get("liquidez", "Baixa")
    prazo = produto.get("prazo_dias", 9999)
    tipo = produto.get("tipo", "")

    # Se a taxa for < 0.01 (1%), tenta corrigir com base no CDI
    if taxa < 0.01 and cdi_atual and cdi_atual > 0.01:
        nome = produto.get("nome", "")
        if "CDI" in nome:
            try:
                # Extrai o percentual do nome (ex: "CDB 115% CDI" -> 1.15)
                pct = float(nome.split("%")[0].split(" ")[-1]) / 100
                taxa = cdi_atual * pct
            except:
                taxa = cdi_atual
        elif "LCI" in nome or "LCA" in nome:
            taxa = cdi_atual * 0.90
        else:
            taxa = cdi_atual

    # Se taxa > 1, é spread sobre CDI
    if taxa > 1 and cdi_atual:
        taxa_ajustada = taxa * cdi_atual
    else:
        taxa_ajustada = taxa

    # Para Tesouro IPCA, adiciona IPCA estimado (6%)
    if "IPCA" in tipo:
        taxa_ajustada += 0.06

    # Ajustes por perfil
    if perfil == 1:  # Conservador
        if isento:
            taxa_ajustada += 0.015
        if "FGC" in garantia:
            taxa_ajustada += 0.005
        if "D+0" in liquidez or "Diária" in liquidez:
            taxa_ajustada += 0.005
        if prazo > 730:
            taxa_ajustada -= 0.02
        if "Sem garantia" in garantia:
            taxa_ajustada -= 0.03
    elif perfil == 3:  # Agressivo
        if prazo > 1095:
            taxa_ajustada += 0.01
        if isento:
            taxa_ajustada -= 0.01
        if "D+0" in liquidez or "Diária" in liquidez:
            taxa_ajustada -= 0.005
    else:  # Moderado (padrão)
        if isento:
            taxa_ajustada += 0.01
        if "FGC" in garantia:
            taxa_ajustada += 0.002
        if prazo > 1095:
            taxa_ajustada -= 0.005

    # Score: transforma taxa anual em nota de 0 a 10
    # Ex: 10% = 5, 15% = 7.5, 20% = 10
    score = (taxa_ajustada * 100) * 0.5
    return float(max(0, min(score, 10)))

def _gerar_produtos_bancarios(cdi_atual):
    if not cdi_atual or cdi_atual <= 0:
        cdi_atual = 0.105
    hoje = datetime.now()
    produtos = []

    spreads = [
        ("CDB-100", "CDB 100% CDI", "CDB", 1.00, 365, "Diária", False),
        ("CDB-110", "CDB 110% CDI", "CDB", 1.10, 540, "Diária", False),
        ("CDB-115", "CDB 115% CDI", "CDB", 1.15, 730, "Diária (carência 30d)", False),
        ("LCI-90",  "LCI 90% CDI",  "LCI", 0.90, 540, "Carência 6 meses", True),
        ("LCA-92",  "LCA 92% CDI",  "LCA", 0.92, 540, "Carência 6 meses", True),
    ]

    for ticker, nome, tipo, spread, dias, liquidez, isento in spreads:
        emissor = random.choice(EMISSORES_FICTICIOS)
        produtos.append({
            "ticker": ticker,
            "nome": nome,
            "emissor": emissor,
            "tipo": tipo,
            "taxa_bruta": cdi_atual * spread,
            "vencimento": (hoje + timedelta(days=dias)).strftime("%Y-%m-%d"),
            "garantia": "FGC",
            "liquidez": liquidez,
            "ir": "ISENTO" if isento else "15% (>720d)",
            "isento_ir": isento,
            "prazo_dias": dias,
            "fonte": "Gerado"
        })
    return produtos

def _processar_tesouro(titulos_brutos):
    if not titulos_brutos:
        return []
    produtos = []
    for t in titulos_brutos:
        nome = t.get('nome', 'Tesouro')
        taxa = t.get('taxa', 0)
        if taxa > 1:
            taxa = taxa / 100
        venc = t.get('vencimento')
        tipo = "Tesouro"
        if "IPCA" in nome:
            tipo = "Tesouro IPCA"
        elif "Prefixado" in nome:
            tipo = "Tesouro Prefixado"
        elif "Selic" in nome:
            tipo = "Tesouro Selic"
        produtos.append({
            "ticker": f"TD-{nome.replace(' ', '')[:10]}",
            "nome": nome,
            "emissor": "Tesouro Nacional",
            "tipo": tipo,
            "taxa_bruta": taxa,
            "vencimento": venc,
            "garantia": "Governo Federal",
            "liquidez": "D+1",
            "ir": "15% (>720d)",
            "isento_ir": False,
            "prazo_dias": _calcular_prazo_dias(venc),
            "fonte": "Tesouro"
        })
    return produtos

def rankear_rf(perfil: int = 2, limite: int = 5, usar_yubb: bool = True):
    produtos = []

    # 1. Scraping Yubb (opcional)
    if usar_yubb and scraper_yubb is not None:
        try:
            produtos = scraper_yubb()
            if produtos:
                logger.info(f"Obtidos {len(produtos)} produtos via Yubb.")
                _, cdi = coletar_indicadores()
                if not cdi or cdi < 0.01:
                    cdi = 0.105
                for p in produtos:
                    # Corrige taxa se estiver incorreta
                    if p["taxa_bruta"] < 0.01 and cdi > 0.01:
                        nome = p.get("nome", "")
                        if "CDI" in nome:
                            try:
                                pct = float(nome.split("%")[0].split(" ")[-1]) / 100
                                p["taxa_bruta"] = cdi * pct
                            except:
                                p["taxa_bruta"] = cdi
                    elif p["taxa_bruta"] > 1:
                        p["taxa_bruta"] = p["taxa_bruta"] * cdi
                    p["prazo_dias"] = _calcular_prazo_dias(p.get("vencimento"))
                    p["score"] = _calcular_score(p, perfil, cdi)
                return sorted(produtos, key=lambda x: x.get("score", 0), reverse=True)[:limite]
        except Exception as e:
            logger.warning(f"Scraping Yubb falhou: {e}")

    # 2. APIs oficiais
    try:
        selic, cdi = coletar_indicadores()
        if not cdi or cdi < 0.01:
            cdi = 0.105
        titulos = coletar_tesouro()

        if titulos:
            produtos.extend(_processar_tesouro(titulos))
        produtos.extend(_gerar_produtos_bancarios(cdi))

        if produtos:
            for p in produtos:
                # Garante que a taxa esteja correta
                if p.get("taxa_bruta", 0) < 0.01 and cdi > 0.01:
                    nome = p.get("nome", "")
                    if "CDI" in nome:
                        try:
                            pct = float(nome.split("%")[0].split(" ")[-1]) / 100
                            p["taxa_bruta"] = cdi * pct
                        except:
                            p["taxa_bruta"] = cdi
                p["prazo_dias"] = _calcular_prazo_dias(p.get("vencimento"))
                p["score"] = _calcular_score(p, perfil, cdi)
            return sorted(produtos, key=lambda x: x.get("score", 0), reverse=True)[:limite]
    except Exception as e:
        logger.error(f"Erro nas APIs oficiais: {e}")

    # 3. Fallback fixo
    logger.warning("Usando fallback fixo para Renda Fixa.")
    fallback = get_fallback()
    _, cdi = coletar_indicadores()
    if not cdi or cdi < 0.01:
        cdi = 0.105
    for p in fallback:
        if p.get("taxa_bruta", 0) < 0.01 and cdi > 0.01:
            if "CDI" in p.get("nome", ""):
                try:
                    spread = float(p["nome"].split("%")[0].split(" ")[-1]) / 100
                    p["taxa_bruta"] = cdi * spread
                except:
                    p["taxa_bruta"] = cdi
        p["score"] = _calcular_score(p, perfil, cdi)
    return sorted(fallback, key=lambda x: x.get("score", 0), reverse=True)[:limite]