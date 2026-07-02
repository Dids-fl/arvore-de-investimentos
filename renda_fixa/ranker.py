# renda_fixa/ranker.py
import logging
from datetime import datetime
from .coletor import coletar_indicadores, coletar_tesouro

logger = logging.getLogger(__name__)


def _calcular_prazo_dias(vencimento):
    if not vencimento:
        return 9999
    try:
        if isinstance(vencimento, str):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    venc = datetime.strptime(vencimento, fmt)
                    break
                except ValueError:
                    continue
            else:
                return 9999
        else:
            venc = vencimento
        hoje = datetime.now()
        return max((venc - hoje).days, 1)
    except Exception:
        return 9999


def _calcular_score(produto, perfil):
    taxa = produto.get("taxa_bruta", 0.0)
    garantia = produto.get("garantia", "Sem garantia")
    liquidez = produto.get("liquidez", "Baixa")
    prazo = produto.get("prazo_dias", 9999)
    tipo = produto.get("tipo", "")

    taxa_ajustada = taxa
    if "IPCA" in tipo:
        taxa_ajustada += 0.06

    if perfil == 1:  # Conservador
        if "Governo Federal" in garantia:
            taxa_ajustada += 0.005
        if "D+0" in liquidez or "D+1" in liquidez:
            taxa_ajustada += 0.005
        if prazo > 730:
            taxa_ajustada -= 0.02
    elif perfil == 3:  # Agressivo
        if prazo > 1095:
            taxa_ajustada += 0.01
    else:  # Moderado (perfil 2)
        if prazo > 1095:
            taxa_ajustada -= 0.005

    score = (taxa_ajustada * 100) * 0.5
    return float(max(0, min(score, 10)))


def _processar_tesouro(titulos_brutos):
    if not titulos_brutos:
        return []
    produtos = []
    for t in titulos_brutos:
        nome = t.get('nome', 'Tesouro')
        taxa = t.get('taxa', 0)
        venc = t.get('vencimento')
        tipo = t.get('tipo', 'Tesouro')
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
            "fonte": "Tesouro API"
        })
    return produtos


def rankear_rf(perfil: int = 2, limite: int = 5):
    """
    Retorna recomendações de Renda Fixa (apenas Tesouro Direto).
    Se a API falhar, retorna lista vazia.
    """
    try:
        selic, cdi = coletar_indicadores()
        if not cdi or cdi < 0.01:
            cdi = 0.105
        titulos = coletar_tesouro()

        if titulos:
            produtos = _processar_tesouro(titulos)
            for p in produtos:
                p["prazo_dias"] = _calcular_prazo_dias(p.get("vencimento"))
                p["score"] = _calcular_score(p, perfil)
            return sorted(produtos, key=lambda x: x.get("score", 0), reverse=True)[:limite]
        else:
            logger.warning("Nenhum título do Tesouro obtido.")
            return []

    except Exception as e:
        logger.error(f"Erro ao obter recomendações de Renda Fixa: {e}")
        return []