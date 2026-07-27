# produtos_estruturados/ranker.py
"""
Ranker de Produtos Estruturados (CRA, CRI, Debêntures), por perfil.

Pipeline (mesmo espírito de fundos/ranker_fundos.py):

1. CADASTRO      — produtos_estruturados.cadastro_coletor.obter_cadastro()
                    (securitizadoras -> CRAs/CRIs; debêntures ativas).
                    Cacheado ~1 semana.
2. NEGOCIAÇÃO    — produtos_estruturados.negociacao_coletor.obter_negociacao_agregada()
                    (janela de dias úteis em negociação balcão, agregada por ISIN).
3. INDICADORES + FILTRO + SCORE — cruza os dois, filtra por perfil
                    (produtos_estruturados.filtros) e calcula o score
                    ponderado (taxa, liquidez, prazo, isenção de IR).
"""

import logging

from .cadastro_coletor import obter_cadastro
from .negociacao_coletor import obter_negociacao_agregada
from .indicadores import montar_indicadores
from .filtros import filtrar_para_ranking

logger = logging.getLogger(__name__)

PERFIL_CONSERVADOR = 1
PERFIL_MODERADO = 2
PERFIL_AGRESSIVO = 3

# Ajustado com base em dados reais de produção (jul/2026): balcão de
# CRA/CRI/debênture é ilíquido, muitos ativos só negociam algumas vezes
# por mês. Uma janela de 20 dias deixava a maioria sem nenhum negócio
# registrado (score_liquidez=0). 60 dias captura melhor a atividade real
# sem ficar pesado demais (a B3 retorna ~150-160 mil negócios/mês em todo
# o balcão, filtrados para CRA/CRI/Debênture antes de qualquer cálculo).
DIAS_NEGOCIACAO_PADRAO = 60

# Pesos por perfil — conservador prioriza liquidez, agressivo prioriza taxa
PESOS = {
    PERFIL_CONSERVADOR: {"taxa": 0.30, "liquidez": 0.50, "prazo": 0.10, "ir": 0.10},
    PERFIL_MODERADO:    {"taxa": 0.45, "liquidez": 0.30, "prazo": 0.10, "ir": 0.15},
    PERFIL_AGRESSIVO:   {"taxa": 0.60, "liquidez": 0.15, "prazo": 0.10, "ir": 0.15},
}


def _limitar(valor, minimo=0, maximo=10):
    return max(minimo, min(valor, maximo))


def _score_taxa(taxa):
    """Taxa aqui é o spread/rentabilidade negociado (ex.: %CDI, IPCA+x%).
    Sem um benchmark único entre CRA/CRI/Debênture, normalizamos de forma
    simples: taxa em % a.a. equivalente, capado em 15% para o score máximo."""
    if taxa is None:
        return 0.0
    return _limitar((float(taxa) / 15) * 10)


def _score_prazo(prazo_dias, perfil):
    if prazo_dias is None:
        return 0.0
    if perfil == PERFIL_CONSERVADOR:
        # quanto mais curto, melhor (dentro do mínimo já filtrado)
        return _limitar(10 - (prazo_dias / 720) * 10)
    if perfil == PERFIL_AGRESSIVO:
        # prazos mais longos tendem a pagar mais prêmio
        return _limitar((prazo_dias / 1800) * 10)
    return 5.0  # moderado: neutro


def _score_ir(isento_ir):
    return 10.0 if isento_ir else 4.0  # isenção de IR é vantagem estrutural


def _calcular_score(ativo, perfil):
    pesos = PESOS[perfil]
    scores = {
        "taxa": _score_taxa(ativo.get("taxa")),
        "liquidez": _limitar(ativo.get("score_liquidez", 0.0)),
        "prazo": _score_prazo(ativo.get("prazo_dias"), perfil),
        "ir": _score_ir(ativo.get("isento_ir", False)),
    }
    total = sum(scores[k] * pesos[k] for k in pesos)

    # Penalidade: sem negociação recente (taxa é estimativa/inexistente)
    if not ativo.get("tem_negociacao_recente"):
        total *= 0.7

    # Penalidade adicional: CRA/CRI sem cadastro oficial (fallback via
    # negociação balcão) não tem vencimento confirmado — o investidor não
    # sabe o prazo real do papel. Isso é uma limitação de dados, não do
    # ativo em si, mas precisa refletir no score para não competir de
    # igual para igual com ativos com prazo confirmado.
    if ativo.get("sem_cadastro_oficial"):
        total *= 0.8

    return round(total, 2), scores


class RankerEstruturados:
    def __init__(self, perfil: int = PERFIL_MODERADO, tipos: set[str] | None = None,
                 dias_negociacao: int = DIAS_NEGOCIACAO_PADRAO):
        self.perfil = perfil
        self.tipos = tipos
        self.dias_negociacao = dias_negociacao
        self._ranking = None

    def limpar_cache(self):
        self._ranking = None

    def _gerar_ranking(self):
        cadastro = obter_cadastro()
        negociacao = obter_negociacao_agregada(dias=self.dias_negociacao)
        ativos = montar_indicadores(cadastro, negociacao)

        elegiveis = filtrar_para_ranking(ativos, self.perfil, tipos=self.tipos)
        logger.info(
            f"Produtos Estruturados: {len(ativos)} -> {len(elegiveis)} "
            f"elegíveis (perfil {self.perfil})."
        )

        ranking = []
        for ativo in elegiveis:
            score, subscores = _calcular_score(ativo, self.perfil)
            ranking.append({**ativo, "score": score, "subscores": subscores})

        ranking.sort(key=lambda x: x["score"], reverse=True)
        return ranking

    def _obter_ranking(self):
        if self._ranking is None:
            self._ranking = self._gerar_ranking()
        return self._ranking

    def gerar_ranking(self):
        return self._obter_ranking()

    def top(self, quantidade: int = 10):
        return self._obter_ranking()[:quantidade]

    def por_tipo(self, tipo: str, quantidade: int = 10):
        ranking = self._obter_ranking()
        return [a for a in ranking if a["tipo"] == tipo.upper()][:quantidade]


# ---------------------------------------------------------------------
# API pública (mesma convenção de fundos/ranker_fundos.py)
# ---------------------------------------------------------------------

def top_estruturados(quantidade=10, perfil=PERFIL_MODERADO, tipos=None, dias_negociacao=DIAS_NEGOCIACAO_PADRAO):
    return RankerEstruturados(perfil, tipos, dias_negociacao).top(quantidade)


def rankear_estruturados(perfil=PERFIL_MODERADO, limite=10, tipos=None, dias_negociacao=DIAS_NEGOCIACAO_PADRAO):
    """Função principal para o recomendador (ver recomendador_ativos.py)."""
    return RankerEstruturados(perfil, tipos, dias_negociacao).gerar_ranking()[:limite]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    ranking = top_estruturados(quantidade=10, perfil=PERFIL_MODERADO)

    print("\n" + "=" * 100)
    print("TOP 10 PRODUTOS ESTRUTURADOS (CRA / CRI / Debênture) — Perfil Moderado")
    print("=" * 100)
    for pos, ativo in enumerate(ranking, start=1):
        print(f"\n{pos:02d}º [{ativo['tipo']}] {ativo['identificador']}")
        print(f"    Score: {ativo['score']:.2f}  |  Taxa: {ativo.get('taxa')}  |  "
              f"Isento IR: {ativo['isento_ir']}  |  Prazo: {ativo.get('prazo_dias')} dias")