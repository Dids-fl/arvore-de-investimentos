# fundos/intersecao_previdenciaria.py
"""
Interseção dos fundos PREVIDENCIÁRIOS (FIEs de PGBL/VGBL): cadastro ativo na
tabela ``cad_fi_previdenciario`` ∩ CNPJs com dados no Informe Diário da CVM.

Espelha ``fundos/intersecao.py``. Os dados vêm dos arquivos abertos e
gratuitos da CVM e são atualizados pelos próprios coletores ao rodar o app.
"""

import pandas as pd

from .cadastro_coletor import listar_fundos_ativos_previdenciario
from .informe_diario_coletor import listar_cnpjs_distintos


def carregar_interseccao_previdenciaria_dataframe() -> pd.DataFrame:
    """Cadastro dos fundos previdenciários ativos que têm histórico diário.

    Devolve um DataFrame vazio quando o cadastro ou o informe estão vazios,
    para que o ranker registre o motivo em vez de quebrar.
    """
    df_cad = listar_fundos_ativos_previdenciario()
    if df_cad is None or df_cad.empty:
        return pd.DataFrame()

    df_inf_cnpjs = listar_cnpjs_distintos()
    if df_inf_cnpjs is None or df_inf_cnpjs.empty:
        return pd.DataFrame()

    intersecao = set(df_cad["CNPJ_Classe"]) & set(df_inf_cnpjs["CNPJ_Classe"])
    return df_cad[df_cad["CNPJ_Classe"].isin(intersecao)]
