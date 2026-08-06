# renda_fixa/ranker.py
import logging
import re
import unicodedata
from datetime import datetime, timezone

from .coletor import coletar_tesouro

logger = logging.getLogger(__name__)


def _ano_vencimento(vencimento) -> int | None:
    if isinstance(vencimento, datetime):
        return vencimento.year
    if isinstance(vencimento, str):
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(
                    vencimento,
                    formato,
                ).replace(tzinfo=timezone.utc).year
            except ValueError:
                continue
    return None


def _codigo_tesouro(nome: str, tipo: str) -> str:
    texto = unicodedata.normalize("NFKD", f"{tipo} {nome}")
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    texto = re.sub(r"\s+", " ", texto.upper())
    juros_semestrais = "JUROS SEMESTRAIS" in texto
    if "SELIC" in texto:
        return "SELIC"
    if "IPCA" in texto:
        return "IPCA-JS" if juros_semestrais else "IPCA"
    if "PREFIX" in texto:
        return "PREFIX-JS" if juros_semestrais else "PREFIX"
    return "TESOURO"


def _data_referencia(valor=None) -> datetime:
    if valor is None:
        return datetime.now(timezone.utc)
    if isinstance(valor, datetime):
        return (
            valor.replace(tzinfo=timezone.utc)
            if valor.tzinfo is None
            else valor.astimezone(timezone.utc)
        )
    if isinstance(valor, str):
        return datetime.fromisoformat(valor).replace(tzinfo=timezone.utc)
    raise TypeError("data_referencia deve ser datetime, texto ISO ou None.")


def _calcular_prazo_dias(vencimento, data_referencia=None):
    if not vencimento:
        return 9999
    try:
        if isinstance(vencimento, str):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    venc = datetime.strptime(
                        vencimento, fmt
                    ).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                return 9999
        else:
            venc = vencimento

        if isinstance(venc, datetime) and venc.tzinfo is None:
            venc = venc.replace(tzinfo=timezone.utc)

        hoje = _data_referencia(data_referencia)
        return (venc - hoje).days
    except (TypeError, ValueError, OverflowError):
        return 9999


def _compatibilidade_prazo(prazo_dias, prazo_anos) -> float:
    if prazo_anos is None:
        return 10.0
    horizonte = max(float(prazo_anos) * 365.25, 365.25)
    distancia_relativa = abs(float(prazo_dias) - horizonte) / horizonte
    return max(0.0, min(10.0, 10.0 * (1.0 - distancia_relativa)))


def _calcular_score(produto, perfil, prazo_anos=None):
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

    score_retorno = float(max(0, min((taxa_ajustada * 100) * 0.5, 10)))
    if prazo_anos is None:
        return score_retorno
    score_prazo = _compatibilidade_prazo(prazo, prazo_anos)
    return round(score_retorno * 0.65 + score_prazo * 0.35, 2)


def _processar_tesouro(titulos_brutos, data_referencia=None):
    if not titulos_brutos:
        return []
    produtos = []
    for t in titulos_brutos:
        nome = t.get('nome', 'Tesouro')
        taxa = t.get('taxa', 0)
        venc = t.get('vencimento')
        tipo = t.get('tipo', 'Tesouro')
        ano = _ano_vencimento(venc)
        codigo = _codigo_tesouro(nome, tipo)
        ticker = f"TD-{codigo}-{ano}" if ano else f"TD-{codigo}"
        nome_exibicao = (
            nome if ano is None or str(ano) in nome else f"{nome} {ano}"
        )
        produtos.append({
            "ticker": ticker,
            "nome": nome_exibicao,
            "emissor": "Tesouro Nacional",
            "tipo": tipo,
            "taxa_bruta": taxa,
            "vencimento": venc,
            "garantia": "Governo Federal",
            "liquidez": "D+1",
            "ir": "Regressivo: 22,5% a 15% conforme o prazo",
            "isento_ir": False,
            "prazo_dias": _calcular_prazo_dias(venc, data_referencia),
            "fonte": "Tesouro API"
        })
    return produtos


def rankear_rf(
    perfil: int = 2,
    limite: int = 5,
    *,
    prazo_anos: float | None = None,
    data_referencia=None,
):
    """
    Retorna recomendações de Renda Fixa (apenas Tesouro Direto).

    Sem fallback fixo: se SELIC/CDI não puderem ser obtidos online,
    propaga DadosIndisponiveisError (o chamador — recomendador_ativos —
    decide como comunicar isso ao usuário). Se o Tesouro Direto não
    retornar títulos, retorna lista vazia (não é uma falha de fonte,
    apenas ausência de produtos elegíveis no momento).
    """

    titulos = coletar_tesouro()
    if not titulos:
        logger.warning("Nenhum título do Tesouro obtido (fonte online sem dados no momento).")
        return []

    produtos = _processar_tesouro(titulos, data_referencia)
    produtos = [produto for produto in produtos if produto["prazo_dias"] > 0]
    for p in produtos:
        p["score"] = _calcular_score(p, perfil, prazo_anos)
        p["compatibilidade_prazo"] = round(
            _compatibilidade_prazo(p["prazo_dias"], prazo_anos),
            2,
        )
    return sorted(produtos, key=lambda x: x.get("score", 0), reverse=True)[:limite]
