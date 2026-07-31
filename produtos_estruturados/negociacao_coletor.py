# produtos_estruturados/negociacao_coletor.py
"""
Coleta negociações em balcão (mercados.b3.B3.negociacao_balcao) filtradas
para CRA, CRI e Debênture, agregadas por código ISIN ao longo de uma janela
de dias úteis.

A B3 só permite consultar UM dia por chamada, então iteramos uma janela
(padrão: 20 dias úteis ~ 1 mês) e agregamos: última taxa negociada, preço
médio, volume acumulado e nº de negócios (proxy de liquidez).
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from mercados.b3 import B3

logger = logging.getLogger(__name__)

# Códigos reais confirmados em produção (jul/2026), via inspeção direta
# do campo `instrumento` retornado por negociacao_balcao(): a B3 usa
# SIGLAS curtas, não os nomes por extenso. O código antigo comparava
# "DEBENTURE" (nome por extenso) contra o valor real "DEB" (sigla) — como
# "DEBENTURE" nunca é substring de "DEB", isso zerava 100% das debêntures
# capturadas, sem gerar nenhum erro (falha silenciosa).
#
# Outros códigos que aparecem na mesma consulta (fora do escopo desta
# categoria, mas documentados aqui para referência futura): CFF (Cédula
# de Crédito Financeiro?), COE, CPR, LF, LIG, CDCA, CBIO, LFSN, NC, LFSC.
INSTRUMENTOS_ALVO = {"CRA", "CRI", "DEB"}


def _dias_uteis(dias: int, referencia: date | None = None,):
    """Gera até `dias` datas de calendário anteriores à referência
    (filtragem fina de fim de semana é feita implicitamente: a B3 retorna
    404 para dias sem pregão e o coletor apenas ignora)."""
    referencia = referencia or datetime.now(timezone.utc).date()
    for i in range(1, dias + 1):
        yield referencia - timedelta(days=i)


def coletar_negociacao_balcao(dias: int = 20,referencia: date | None = None,):
    """
    Retorna lista de negociações (dataclasses NegociacaoBalcao) dos últimos
    `dias` dias corridos, já filtradas para instrumentos de interesse
    (CRA/CRI/Debênture).
    """
    b3 = B3()
    negociacoes = []

    for dia in _dias_uteis(dias, referencia):
        try:
            for neg in b3.negociacao_balcao(dia):
                instrumento = (neg.instrumento or "").strip().upper()
                if instrumento in INSTRUMENTOS_ALVO:
                    negociacoes.append(neg)
        except Exception as e:
            logger.warning(f"Falha ao coletar negociação balcão de {dia}: {e}")
            continue

    logger.info(
        f"Negociação balcão: {len(negociacoes)} negócios coletados em {dias} dias."
    )
    return negociacoes

def agregar_por_isin(negociacoes):
    """
    Agrega a lista de NegociacaoBalcao por código ISIN, retornando um dict:
    {isin: {"taxa_ultima": ..., "preco_medio": ..., "volume_total": ...,
            "n_negocios": ..., "emissor": ..., "instrumento": ...,
            "data_ultima": ...}}
    """
    por_isin = defaultdict(list)
    for neg in negociacoes:
        if neg.codigo_isin:
            por_isin[neg.codigo_isin].append(neg)

    agregado = {}
    for isin, negs in por_isin.items():
        negs_ordenados = sorted(negs, key=lambda n: n.datahora)
        ultima = negs_ordenados[-1]
        volume_total = sum(float(n.volume) for n in negs if n.volume is not None)
        precos = [float(n.preco) for n in negs if n.preco is not None]

        agregado[isin] = {
            "isin": isin,
            "instrumento": ultima.instrumento,
            "emissor": ultima.emissor,
            "taxa_ultima": float(ultima.taxa) if ultima.taxa is not None else None,
            "preco_medio": sum(precos) / len(precos) if precos else None,
            "volume_total": volume_total,
            "n_negocios": len(negs),
            "data_ultima": ultima.datahora,
        }

    return agregado


def obter_negociacao_agregada(dias: int = 20,referencia: date | None = None,):
    """API pública: coleta + agrega em uma chamada só."""
    negociacoes = coletar_negociacao_balcao(dias=dias, referencia=referencia)
    return agregar_por_isin(negociacoes)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    agregado = obter_negociacao_agregada(dias=20)
    print(f"{len(agregado)} ativos com negociação recente (CRA/CRI/Debênture).")
    for isin, dados in list(agregado.items())[:5]:
        print(isin, dados)