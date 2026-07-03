# fundos/ranker.py
import logging
from .coletor import listar_fundos, buscar_cotas_em_lote

logger = logging.getLogger(__name__)

def _obter_coluna(df, possiveis):
    for col in possiveis:
        if col in df.columns:
            return col
    raise KeyError(f"Nenhuma das colunas {possiveis} encontrada no DataFrame.")

def _calcular_score(fundo, perfil):
    rent = fundo.get("rentabilidade_12m", 0)
    taxa_adm = fundo.get("taxa_adm", 0)
    classe = fundo.get("classe", "")
    rent_liquida = rent - taxa_adm
    bonus = 0
    if perfil == 1:  # Conservador
        if classe and "Renda Fixa" in classe:
            bonus = 0.05
        else:
            bonus = -0.10
        if taxa_adm > 0.01:
            bonus -= 0.02
    elif perfil == 3:  # Agressivo
        if classe and ("Ações" in classe or "Multimercado" in classe):
            bonus = 0.08
        else:
            bonus = -0.05
    else:  # Moderado
        if classe and "Multimercado" in classe:
            bonus = 0.02
    score_final = rent_liquida + bonus
    nota = (score_final * 100)
    return float(max(0, min(nota, 10)))

def rankear_fundos(perfil: int = 2, limite: int = 10):
    try:
        df_cadastro = listar_fundos(limit=200)
        if df_cadastro.empty:
            logger.warning("Nenhum fundo encontrado no cadastro.")
            return []

        # Identifica colunas chave dinamicamente
        cnpj_col = _obter_coluna(df_cadastro, ['CNPJ_FUNDO', 'CNPJ', 'cnpj'])
        nome_col = _obter_coluna(df_cadastro, ['DENOM_SOCIAL', 'NOME', 'nome'])
        classe_col = _obter_coluna(df_cadastro, ['CLASSE', 'CLASSE_ANBIMA'])
        patrimonio_col = _obter_coluna(df_cadastro, ['VL_PATRIM_LIQ', 'PATRIM_LIQ', 'PATRIMONIO'])

        cnpjs_validos = df_cadastro[cnpj_col].tolist()
        df_cotas = buscar_cotas_em_lote(cnpjs_validos, dias=365)
        if df_cotas.empty:
            logger.warning("Nenhuma cota encontrada para os fundos.")
            return []

        # Identifica colunas de cotas
        cnpj_cotas_col = _obter_coluna(df_cotas, ['CNPJ_FUNDO', 'CNPJ', 'cnpj'])
        data_col = _obter_coluna(df_cotas, ['DT_COMPTC', 'DATA'])
        cota_col = _obter_coluna(df_cotas, ['VL_QUOTA', 'COTA'])

        fundos = []
        for cnpj, group in df_cotas.groupby(cnpj_cotas_col):
            dados_cad = df_cadastro[df_cadastro[cnpj_col] == cnpj].iloc[0]
            group = group.sort_values(data_col)
            if len(group) < 2:
                continue
            cota_inicial = group.iloc[0][cota_col]
            cota_final = group.iloc[-1][cota_col]
            if cota_inicial <= 0:
                continue
            rentabilidade = (cota_final / cota_inicial) - 1
            classe = str(dados_cad.get(classe_col, ''))
            patrimonio = float(dados_cad.get(patrimonio_col, 0))
            taxa_adm = 0.01  # estimativa
            fundos.append({
                "cnpj": cnpj,
                "nome": dados_cad.get(nome_col, 'Fundo'),
                "classe": classe,
                "taxa_adm": taxa_adm,
                "patrimonio": patrimonio,
                "rentabilidade_12m": float(rentabilidade),
            })

        if not fundos:
            logger.warning("Nenhum fundo com rentabilidade calculada.")
            return []

        for f in fundos:
            f["score"] = _calcular_score(f, perfil)

        return sorted(fundos, key=lambda x: x.get("score", 0), reverse=True)[:limite]

    except Exception as e:
        logger.error(f"Erro no rankeamento: {e}")
        return []