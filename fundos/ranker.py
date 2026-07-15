# fundos/ranker.py

import logging

from .cadastro_coletor import (
    listar_fundos_ativos,
)

from .indicadores import (
    calcular_indicadores,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------

PERFIL_CONSERVADOR = 1
PERFIL_MODERADO = 2
PERFIL_AGRESSIVO = 3


# ---------------------------------------------------------------------
# Pesos
# ---------------------------------------------------------------------

PESOS = {

    PERFIL_CONSERVADOR: {

        "retorno_12m": 0.20,

        "volatilidade": 0.35,

        "drawdown": 0.25,

        "fluxo": 0.10,

        "patrimonio": 0.10,

    },

    PERFIL_MODERADO: {

        "retorno_12m": 0.35,

        "volatilidade": 0.25,

        "drawdown": 0.15,

        "fluxo": 0.15,

        "patrimonio": 0.10,

    },

    PERFIL_AGRESSIVO: {

        "retorno_12m": 0.50,

        "volatilidade": 0.10,

        "drawdown": 0.10,

        "fluxo": 0.20,

        "patrimonio": 0.10,

    },

}


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

def _numero(valor):

    try:

        if valor is None:
            return 0.0

        return float(valor)

    except Exception:

        return 0.0


def _limitar(

    valor,

    minimo,

    maximo,

):

    return max(

        minimo,

        min(

            valor,

            maximo,

        ),

    )


# ---------------------------------------------------------------------
# Normalizações
# ---------------------------------------------------------------------

def _score_retorno(

    retorno,

):

    if retorno is None:
        return 0.0

    retorno = _numero(retorno)

    # -50% -> 0
    # +50% -> 10

    score = (

        (retorno + 0.50)

        / 1.00

    ) * 10

    return _limitar(

        score,

        0,

        10,

    )


def _score_volatilidade(

    volatilidade,

):

    if volatilidade is None:
        return 0.0

    volatilidade = _numero(volatilidade)

    # Quanto menor, melhor

    score = 10 - (

        volatilidade * 20

    )

    return _limitar(

        score,

        0,

        10,

    )


def _score_drawdown(

    drawdown,

):

    if drawdown is None:
        return 0.0

    drawdown = abs(

        _numero(drawdown)

    )

    score = 10 - (

        drawdown * 20

    )

    return _limitar(

        score,

        0,

        10,

    )

# ---------------------------------------------------------------------
# Continuação das normalizações
# ---------------------------------------------------------------------

def _score_fluxo(
    fluxo,
):
    """
    Fluxo líquido positivo indica entrada
    de investidores.
    """

    if fluxo is None:
        return 0.0

    fluxo = _numero(fluxo)

    if fluxo <= 0:
        return 5.0

    score = 5 + min(
        fluxo / 100_000_000,
        5,
    )

    return _limitar(
        score,
        0,
        10,
    )


def _score_patrimonio(
    patrimonio,
):
    """
    Fundos maiores tendem a ser mais
    consolidados.
    """

    if patrimonio is None:
        return 0.0

    patrimonio = _numero(
        patrimonio
    )

    if patrimonio <= 0:
        return 0

    if patrimonio >= 10_000_000_000:
        return 10

    if patrimonio >= 5_000_000_000:
        return 9

    if patrimonio >= 1_000_000_000:
        return 8

    if patrimonio >= 500_000_000:
        return 7

    if patrimonio >= 100_000_000:
        return 6

    return 5


# ---------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------

def calcular_score(
    indicadores,
    perfil=PERFIL_MODERADO,
):

    pesos = PESOS[
        perfil
    ]

    score_retorno = _score_retorno(

        indicadores[
            "retorno_12m"
        ]

    )

    score_volatilidade = (
        _score_volatilidade(

            indicadores[
                "volatilidade"
            ]

        )
    )

    score_drawdown = (
        _score_drawdown(

            indicadores[
                "drawdown"
            ]

        )
    )

    score_fluxo = (
        _score_fluxo(

            indicadores[
                "fluxo_liquido"
            ]

        )
    )

    score_patrimonio = (
        _score_patrimonio(

            indicadores[
                "patrimonio_atual"
            ]

        )
    )

    score = (

        score_retorno
        * pesos["retorno_12m"]

        +

        score_volatilidade
        * pesos["volatilidade"]

        +

        score_drawdown
        * pesos["drawdown"]

        +

        score_fluxo
        * pesos["fluxo"]

        +

        score_patrimonio
        * pesos["patrimonio"]

    )

    return {

        "score": round(
            score,
            2,
        ),

        "retorno": round(
            score_retorno,
            2,
        ),

        "volatilidade": round(
            score_volatilidade,
            2,
        ),

        "drawdown": round(
            score_drawdown,
            2,
        ),

        "fluxo": round(
            score_fluxo,
            2,
        ),

        "patrimonio": round(
            score_patrimonio,
            2,
        ),

    }

# ---------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------

class RankerFundos:

    def __init__(
        self,
        perfil=PERFIL_MODERADO,
    ):

        self.perfil = perfil

    # -------------------------------------------------------------

    def _rankear_fundo(
        self,
        fundo,
    ):

        indicadores = calcular_indicadores(
            fundo["CNPJ_Classe"]
        )

        score = calcular_score(

            indicadores,

            self.perfil,

        )

        return {

            "cnpj": indicadores["cnpj"],

            "nome": indicadores["nome"],

            "classe": indicadores["classe"],

            "tipo": indicadores["tipo"],

            "score": score["score"],

            "subscores": {

                "retorno": score["retorno"],

                "volatilidade":
                    score["volatilidade"],

                "drawdown":
                    score["drawdown"],

                "fluxo":
                    score["fluxo"],

                "patrimonio":
                    score["patrimonio"],

            },

            "indicadores": indicadores,

        }

    # -------------------------------------------------------------

    def gerar_ranking(
        self,
    ):

        fundos = listar_fundos_ativos()

        ranking = []

        total = len(fundos)

        logger.info(
            "Rankeando %d fundos...",
            total,
        )

        for indice, fundo in fundos.iterrows():

            try:

                ranking.append(

                    self._rankear_fundo(
                        fundo
                    )

                )

            except Exception as e:

                logger.debug(

                    "%s -> %s",

                    fundo[
                        "CNPJ_Classe"
                    ],

                    e,

                )

        ranking.sort(

            key=lambda x: x["score"],

            reverse=True,

        )

        return ranking
    
# -------------------------------------------------------------
# Filtros
# -------------------------------------------------------------

    def top(
        self,
        quantidade=20,
    ):

        ranking = self.gerar_ranking()

        return ranking[
            :quantidade
        ]


    def buscar_cnpj(
        self,
        cnpj,
    ):

        ranking = self.gerar_ranking()

        cnpj = (
            str(cnpj)
            .replace(".", "")
            .replace("/", "")
            .replace("-", "")
            .zfill(14)
        )

        for fundo in ranking:

            if fundo["cnpj"] == cnpj:

                return fundo

        return None


    def buscar_nome(
        self,
        texto,
    ):

        ranking = self.gerar_ranking()

        texto = texto.upper()

        encontrados = []

        for fundo in ranking:

            nome = fundo["nome"]

            if nome is None:
                continue

            if texto in nome.upper():

                encontrados.append(
                    fundo
                )

        return encontrados


    def por_classe(
        self,
        classe,
    ):

        ranking = self.gerar_ranking()

        classe = classe.upper()

        encontrados = []

        for fundo in ranking:

            nome_classe = (
                fundo["classe"]
                or ""
            ).upper()

            if classe in nome_classe:

                encontrados.append(
                    fundo
                )

        return encontrados


# -------------------------------------------------------------
# Estatísticas
# -------------------------------------------------------------

    def estatisticas(self):

        ranking = self.gerar_ranking()

        if not ranking:

            return {}

        scores = [

            fundo["score"]

            for fundo in ranking

        ]

        return {

            "fundos": len(
                ranking
            ),

            "score_medio": round(

                sum(scores)

                / len(scores),

                2,

            ),

            "score_maximo": max(
                scores
            ),

            "score_minimo": min(
                scores
            ),

        }
    
# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------

def gerar_ranking(
    perfil=PERFIL_MODERADO,
):
    """
    Gera o ranking completo.
    """

    return RankerFundos(
        perfil
    ).gerar_ranking()


def top_fundos(
    quantidade=20,
    perfil=PERFIL_MODERADO,
):
    """
    Retorna os melhores fundos.
    """

    return RankerFundos(
        perfil
    ).top(
        quantidade
    )


def buscar_fundo_cnpj(
    cnpj,
    perfil=PERFIL_MODERADO,
):

    return RankerFundos(
        perfil
    ).buscar_cnpj(
        cnpj
    )


def buscar_fundo_nome(
    nome,
    perfil=PERFIL_MODERADO,
):

    return RankerFundos(
        perfil
    ).buscar_nome(
        nome
    )


def fundos_por_classe(
    classe,
    perfil=PERFIL_MODERADO,
):

    return RankerFundos(
        perfil
    ).por_classe(
        classe
    )


# ---------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------

if __name__ == "__main__":

    logging.basicConfig(

        level=logging.INFO,

        format="%(levelname)s - %(message)s",

    )

    ranking = top_fundos(
        quantidade=10,
        perfil=PERFIL_MODERADO,
    )

    print()

    print("=" * 100)
    print("TOP 10 FUNDOS")
    print("=" * 100)

    for posicao, fundo in enumerate(
        ranking,
        start=1,
    ):

        print()

        print(
            f"{posicao:02d}º"
        )

        print(
            f"Nome : {fundo['nome']}"
        )

        print(
            f"Classe : {fundo['classe']}"
        )

        print(
            f"Score : {fundo['score']:.2f}"
        )

        print(
            "Subscores:"
        )

        for chave, valor in fundo[
            "subscores"
        ].items():

            print(
                f"   {chave:15}: {valor:.2f}"
            )

    print()

    print("=" * 100)