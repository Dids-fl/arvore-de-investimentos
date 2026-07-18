# fundos/informe_diario_coletor.py

from pathlib import Path
import logging
import sqlite3

import pandas as pd

from .cvm_informe_diario_downloader import (
    download_informe_diario,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).parent

DB_PATH = (
    BASE_DIR
    / "data"
    / "informe_diario_cache.db"
)

# Tempo (ms) que uma conexão espera por um lock antes de desistir.
# Ajuda em pastas sincronizadas (OneDrive/Dropbox) e quando leitura e escrita
# acontecem em processos/conexões diferentes ao mesmo tempo.
BUSY_TIMEOUT_MS = 30_000

# Colunas (e ordem) usadas para inserir/atualizar registros na tabela.
COLUNAS_INFORME = [
    "CNPJ_Classe",
    "Data_Competencia",
    "Tipo_Classe",
    "Valor_Total",
    "Valor_Cota",
    "Patrimonio_Liquido",
    "Captacao_Dia",
    "Resgate_Dia",
    "Numero_Cotistas",
]

# Layout ATUAL do Informe Diário (pós Resolução CVM 175 - fundo/classe),
# em vigor desde o fim de 2023 / início de 2024.
MAPA_COLUNAS_NOVO = {
    "CNPJ_FUNDO_CLASSE": "CNPJ_Classe",
    "DT_COMPTC": "Data_Competencia",
    "TP_FUNDO_CLASSE": "Tipo_Classe",
    "VL_TOTAL": "Valor_Total",
    "VL_QUOTA": "Valor_Cota",
    "VL_PATRIM_LIQ": "Patrimonio_Liquido",
    "CAPTC_DIA": "Captacao_Dia",
    "RESG_DIA": "Resgate_Dia",
    "NR_COTST": "Numero_Cotistas",
}

# Layout ANTIGO (pré Resolução CVM 175), usado nos arquivos mensais mais
# antigos: os fundos ainda não eram reportados por "classe de cotas".
MAPA_COLUNAS_ANTIGO = {
    "CNPJ_FUNDO": "CNPJ_Classe",
    "DT_COMPTC": "Data_Competencia",
    "TP_FUNDO": "Tipo_Classe",
    "VL_TOTAL": "Valor_Total",
    "VL_QUOTA": "Valor_Cota",
    "VL_PATRIM_LIQ": "Patrimonio_Liquido",
    "CAPTC_DIA": "Captacao_Dia",
    "RESG_DIA": "Resgate_Dia",
    "NR_COTST": "Numero_Cotistas",
}

LAYOUTS_CONHECIDOS = [MAPA_COLUNAS_NOVO, MAPA_COLUNAS_ANTIGO]


class LayoutColunasDesconhecido(Exception):
    """Levantada quando o CSV da CVM não bate com nenhum layout de colunas conhecido."""


def _mapear_colunas(colunas_disponiveis):
    """
    Identifica qual layout de colunas o CSV está usando (novo ou antigo) e
    retorna o dicionário de renomeação correspondente, ou None se nenhum
    layout conhecido bater.
    """
    colunas_disponiveis = set(colunas_disponiveis)
    for mapa in LAYOUTS_CONHECIDOS:
        if set(mapa.keys()).issubset(colunas_disponiveis):
            return mapa
    return None


# ---------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------

class InformeDiarioColetorCVM:
    def __init__(
        self,
        db_path=None,
        atualizar=True,
    ):
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, timeout=BUSY_TIMEOUT_MS / 1000)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")

        self._criar_tabelas()

        if atualizar:
            # Garante 3 anos de histórico no banco. Meses antigos que já
            # estão completos são pulados; apenas os mais recentes (que a
            # CVM ainda pode atualizar/retificar) são sempre reprocessados.
            self.carregar_historico(anos=3)

    # -------------------------------------------------------------

    def _criar_tabelas(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS informe_diario(
                CNPJ_Classe TEXT,
                Data_Competencia TEXT,
                Tipo_Classe TEXT,
                Valor_Total REAL,
                Valor_Cota REAL,
                Patrimonio_Liquido REAL,
                Captacao_Dia REAL,
                Resgate_Dia REAL,
                Numero_Cotistas INTEGER,
                PRIMARY KEY(CNPJ_Classe, Data_Competencia)
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_inf_cnpj_data
            ON informe_diario(CNPJ_Classe, Data_Competencia)
            """
        )

        self.conn.commit()

    # -------------------------------------------------------------

    def _processar_chunk(self, chunk):
        """
        Processa um chunk do CSV: renomeia colunas, normaliza, e faz
        upsert (INSERT OR REPLACE) no banco.

        Usamos INSERT OR REPLACE (em vez de chunk.to_sql com if_exists="append")
        porque a chave primária é (CNPJ_Classe, Data_Competencia). Como o
        coletor recarrega os últimos meses toda vez que é inicializado, um
        INSERT puro falharia com "UNIQUE constraint failed" assim que
        encontrasse um registro já existente — e a exceção derrubava o
        carregamento do mês inteiro, inclusive descartando dias novos
        publicados pela CVM. Com upsert, registros existentes são
        atualizados e novos registros são inseridos normalmente.
        """
        if chunk.empty:
            return 0

        # Identifica o layout de colunas (novo, pós Resolução 175, ou antigo)
        # e renomeia de acordo. Levanta LayoutColunasDesconhecido se nenhum
        # dos dois bater — isso é tratado em atualizar_informe para abortar
        # o mês de forma limpa, sem repetir o erro em todos os chunks.
        mapa = _mapear_colunas(chunk.columns)
        if mapa is None:
            raise LayoutColunasDesconhecido(
                f"Nenhum layout conhecido bateu. Colunas do CSV: {list(chunk.columns)}"
            )

        chunk = chunk.rename(columns=mapa)

        # Seleciona apenas as colunas necessárias
        chunk = chunk[COLUNAS_INFORME]

        # Remove linhas com CNPJ ou data inválidos
        chunk = chunk.dropna(subset=["CNPJ_Classe", "Data_Competencia"])

        # Normaliza CNPJ
        chunk["CNPJ_Classe"] = (
            chunk["CNPJ_Classe"]
            .astype(str)
            .str.replace("/", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.replace("-", "", regex=False)
            .str.zfill(14)
        )

        # Normaliza data
        chunk["Data_Competencia"] = pd.to_datetime(
            chunk["Data_Competencia"],
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")
        chunk = chunk.dropna(subset=["Data_Competencia"])

        # Converte colunas numéricas.
        #
        # Captacao_Dia, Resgate_Dia e Numero_Cotistas PODEM legitimamente ser 0,
        # então valores ausentes/inválidos viram 0 normalmente.
        #
        # Valor_Total, Valor_Cota e Patrimonio_Liquido NUNCA fazem sentido como
        # 0 para um fundo real — se vierem vazios/inválidos no CSV da CVM, é dado
        # ruim. Zerá-los (como antes) corrompia o cálculo de retorno diário
        # (pct_change vira +inf ao dividir por uma cota zerada), o que gerava
        # RuntimeWarning e Sharpe/Sortino = NaN silenciosamente. Por isso agora
        # a linha inteira é descartada em vez de zerada.
        numericas_pode_zero = ["Captacao_Dia", "Resgate_Dia", "Numero_Cotistas"]
        numericas_nao_pode_zero = ["Valor_Total", "Valor_Cota", "Patrimonio_Liquido"]

        for col in numericas_pode_zero:
            chunk[col] = (
                pd.to_numeric(chunk[col], errors="coerce")
                .fillna(0)
                .clip(lower=0)
            )

        for col in numericas_nao_pode_zero:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

        antes = len(chunk)
        chunk = chunk[
            (chunk["Valor_Cota"] > 0) & (chunk["Patrimonio_Liquido"] > 0)
        ]
        removidos = antes - len(chunk)
        if removidos:
            logger.debug(
                f"{removidos} linha(s) descartada(s) por Valor_Cota/Patrimonio_Liquido inválido (0, negativo ou vazio)."
            )

        # Remove duplicatas dentro do próprio chunk
        chunk = chunk.drop_duplicates(
            subset=["CNPJ_Classe", "Data_Competencia"],
            keep="last",
        )

        if chunk.empty:
            return 0

        # Upsert manual via INSERT OR REPLACE
        placeholders = ", ".join(["?"] * len(COLUNAS_INFORME))
        colunas_sql = ", ".join(COLUNAS_INFORME)
        sql = f"INSERT OR REPLACE INTO informe_diario ({colunas_sql}) VALUES ({placeholders})"

        registros = list(chunk[COLUNAS_INFORME].itertuples(index=False, name=None))

        cursor = self.conn.cursor()
        cursor.executemany(sql, registros)
        self.conn.commit()

        return len(registros)

    # -------------------------------------------------------------

    def atualizar_informe(
        self,
        ano=None,
        mes=None,
        force=False,
    ):
        """
        Baixa e carrega (upsert) um mês específico do Informe Diário.
        Seguro para rodar múltiplas vezes: registros existentes são
        atualizados, não duplicados nem rejeitados.
        """
        csv_path = download_informe_diario(
            ano=ano,
            mes=mes,
            force=force,
        )

        logger.info(f"Carregando Informe Diário {ano}-{mes:02d}...")

        chunk_size = 50000
        total_registros = 0
        chunks_com_erro = 0

        for chunk in pd.read_csv(
            csv_path,
            sep=";",
            encoding="latin1",
            low_memory=False,
            chunksize=chunk_size,
        ):
            try:
                total_registros += self._processar_chunk(chunk)
            except Exception:
                chunks_com_erro += 1
                logger.exception(
                    f"Erro ao processar um chunk de {ano}-{mes:02d} "
                    f"(chunk ignorado, seguindo para o próximo)"
                )

        if chunks_com_erro:
            logger.warning(
                f"  {chunks_com_erro} chunk(s) com erro em {ano}-{mes:02d} "
                f"(ver traceback acima)."
            )

        logger.info(f"  {total_registros} registros gravados para {ano}-{mes:02d}.")

    # -------------------------------------------------------------

    def carregar_ultimos_meses(self, quantidade=3):
        """
        Carrega (upsert) os últimos 'quantidade' meses de Informe Diário,
        SEMPRE reprocessando cada um (útil para forçar atualização de um
        período curto). Para carregar um histórico longo (anos) de forma
        eficiente, prefira `carregar_historico`.
        """
        meses = self._gerar_lista_meses(quantidade)
        meses_carregados = 0

        for ano, mes in meses:
            try:
                self.atualizar_informe(ano=ano, mes=mes, force=False)
                meses_carregados += 1
            except Exception:
                logger.exception(f"Erro ao carregar {ano}-{mes:02d}")

        logger.info(f"Carregados {meses_carregados} meses de Informe Diário.")

    # -------------------------------------------------------------

    def _gerar_lista_meses(self, quantidade):
        """Retorna os últimos 'quantidade' meses (ano, mes), do mais recente ao mais antigo."""
        from datetime import datetime

        hoje = datetime.now()
        ano, mes = hoje.year, hoje.month

        meses = []
        for _ in range(quantidade):
            meses.append((ano, mes))
            mes -= 1
            if mes == 0:
                mes = 12
                ano -= 1

        return meses

    # -------------------------------------------------------------

    def mes_ja_carregado(self, ano, mes):
        """Verifica se já existe ao menos um registro para o mês informado no banco."""
        data_inicio = f"{ano:04d}-{mes:02d}-01"
        if mes == 12:
            prox = f"{ano + 1:04d}-01-01"
        else:
            prox = f"{ano:04d}-{mes + 1:02d}-01"

        row = self.conn.execute(
            """
            SELECT 1 FROM informe_diario
            WHERE Data_Competencia >= ? AND Data_Competencia < ?
            LIMIT 1
            """,
            (data_inicio, prox),
        ).fetchone()

        return row is not None

    # -------------------------------------------------------------

    def carregar_historico(self, anos=3, meses_recentes_forcar=3, force=False):
        """
        Garante que os últimos `anos` anos de Informe Diário estejam
        carregados no banco, de forma eficiente:

        - Os `meses_recentes_forcar` meses mais recentes são SEMPRE
          reprocessados (a CVM publica atualizações diárias no mês corrente
          e às vezes retifica o mês anterior).
        - Meses mais antigos que já têm dados no banco são PULADOS (não
          reprocessa milhões de linhas de novo a cada execução).
        - Meses antigos que ainda não foram carregados (ex.: primeira
          execução, ou um gap) são carregados normalmente.

        Use force=True para ignorar o cache e reprocessar tudo (ex.: depois
        de suspeitar de dados corrompidos).
        """
        quantidade = anos * 12
        meses = self._gerar_lista_meses(quantidade)

        carregados = 0
        pulados = 0
        com_erro = 0

        for i, (ano, mes) in enumerate(meses):
            recente = i < meses_recentes_forcar

            if not recente and not force and self.mes_ja_carregado(ano, mes):
                pulados += 1
                continue

            try:
                self.atualizar_informe(ano=ano, mes=mes, force=force)
                carregados += 1
            except Exception:
                com_erro += 1
                logger.exception(f"Erro ao carregar {ano}-{mes:02d}")

        logger.info(
            f"Histórico ({anos} ano(s)): {carregados} mês(es) carregado(s)/atualizado(s), "
            f"{pulados} já presente(s) e pulado(s), {com_erro} com erro."
        )

    # -------------------------------------------------------------
    # MÉTODOS DE CONSULTA
    # -------------------------------------------------------------

    def listar(self):
        return pd.read_sql_query("SELECT * FROM informe_diario", self.conn)

    def buscar_ultimo_registro(self, cnpj):
        cnpj = (
            str(cnpj)
            .replace(".", "")
            .replace("/", "")
            .replace("-", "")
            .zfill(14)
        )

        df = pd.read_sql_query(
            """
            SELECT *
            FROM informe_diario
            WHERE CNPJ_Classe = ?
            ORDER BY Data_Competencia DESC
            LIMIT 1
            """,
            self.conn,
            params=(cnpj,),
        )

        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def buscar_historico(self, cnpj, limite=252):
        """
        Retorna os últimos 'limite' registros do fundo.
        """
        cnpj = (
            str(cnpj)
            .replace(".", "")
            .replace("/", "")
            .replace("-", "")
            .zfill(14)
        )

        df = pd.read_sql_query(
            """
            SELECT *
            FROM informe_diario
            WHERE CNPJ_Classe = ?
            ORDER BY Data_Competencia DESC
            LIMIT ?
            """,
            self.conn,
            params=(cnpj, limite),
        )

        if df.empty:
            return df

        df = df.sort_values("Data_Competencia")
        return df

    def buscar_historico_completo(self, cnpj):
        cnpj = (
            str(cnpj)
            .replace(".", "")
            .replace("/", "")
            .replace("-", "")
            .zfill(14)
        )

        return pd.read_sql_query(
            """
            SELECT *
            FROM informe_diario
            WHERE CNPJ_Classe = ?
            ORDER BY Data_Competencia
            """,
            self.conn,
            params=(cnpj,),
        )

    # -------------------------------------------------------------
    # OTIMIZAÇÃO EM LOTE PARA RANKING (COM CHUNKING)
    # -------------------------------------------------------------

    def listar_historicos(self, lista_cnpjs, limite=252):
        """
        Retorna histórico dos últimos 'limite' registros para MÚLTIPLOS fundos
        em uma ÚNICA consulta SQL, dividindo em chunks para evitar limite de 999 variáveis.
        """
        if not lista_cnpjs:
            return pd.DataFrame()

        cnpjs_padronizados = []
        for cnpj in lista_cnpjs:
            cnpj = (
                str(cnpj)
                .replace(".", "")
                .replace("/", "")
                .replace("-", "")
                .zfill(14)
            )
            cnpjs_padronizados.append(cnpj)

        # SQLite tem limite de ~999 variáveis por consulta
        chunk_size = 500
        dfs = []

        for i in range(0, len(cnpjs_padronizados), chunk_size):
            chunk = cnpjs_padronizados[i:i+chunk_size]
            placeholders = ",".join(["?" for _ in chunk])
            query = f"""
                SELECT *
                FROM (
                    SELECT *,
                        ROW_NUMBER() OVER (
                            PARTITION BY CNPJ_Classe
                            ORDER BY Data_Competencia DESC
                        ) AS rn
                    FROM informe_diario
                    WHERE CNPJ_Classe IN ({placeholders})
                ) sub
                WHERE rn <= ?
                ORDER BY CNPJ_Classe, Data_Competencia
            """
            params = chunk + [limite]
            try:
                df_chunk = pd.read_sql_query(query, self.conn, params=params)
                if not df_chunk.empty:
                    dfs.append(df_chunk)
            except Exception:
                logger.exception(f"Erro no chunk {i // chunk_size}")

        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)

    # -------------------------------------------------------------

    def listar_metricas_agregadas(self, lista_cnpjs):
        """
        Calcula, DIRETO NO SQL (sem carregar as linhas diárias em pandas),
        as métricas agregadas por CNPJ necessárias para o pré-filtro
        qualitativo (fundos.filtros.FiltroFundos):

        - Dias_Historico: quantidade de dias com registro no banco
        - Patrimonio_Liquido: PL do registro mais recente (mais atual que
          o valor estático do cadastro)
        - Ultimo_Cotistas: número de cotistas do registro mais recente
        - Proporcao_Resgate: soma de resgates / PL médio no período

        Isso permite filtrar dezenas de milhares de fundos rapidamente,
        antes de buscar o histórico diário completo (caro) só dos
        fundos que sobrarem.
        """
        if not lista_cnpjs:
            return pd.DataFrame()

        cnpjs_padronizados = []
        for cnpj in lista_cnpjs:
            cnpj = (
                str(cnpj)
                .replace(".", "")
                .replace("/", "")
                .replace("-", "")
                .zfill(14)
            )
            cnpjs_padronizados.append(cnpj)

        chunk_size = 500
        dfs = []

        for i in range(0, len(cnpjs_padronizados), chunk_size):
            chunk = cnpjs_padronizados[i:i + chunk_size]
            placeholders = ",".join(["?" for _ in chunk])
            query = f"""
                WITH base AS (
                    SELECT
                        CNPJ_Classe,
                        Patrimonio_Liquido,
                        Numero_Cotistas,
                        Resgate_Dia,
                        ROW_NUMBER() OVER (
                            PARTITION BY CNPJ_Classe
                            ORDER BY Data_Competencia DESC
                        ) AS rn
                    FROM informe_diario
                    WHERE CNPJ_Classe IN ({placeholders})
                )
                SELECT
                    CNPJ_Classe,
                    COUNT(*) AS Dias_Historico,
                    SUM(Resgate_Dia) AS Resgate_Total,
                    AVG(Patrimonio_Liquido) AS PL_Medio,
                    MAX(CASE WHEN rn = 1 THEN Patrimonio_Liquido END) AS Patrimonio_Liquido,
                    MAX(CASE WHEN rn = 1 THEN Numero_Cotistas END) AS Ultimo_Cotistas
                FROM base
                GROUP BY CNPJ_Classe
            """
            try:
                df_chunk = pd.read_sql_query(query, self.conn, params=chunk)
                if not df_chunk.empty:
                    dfs.append(df_chunk)
            except Exception:
                logger.exception(f"Erro ao calcular métricas agregadas no chunk {i // chunk_size}")

        if not dfs:
            return pd.DataFrame()

        df = pd.concat(dfs, ignore_index=True)
        df["Proporcao_Resgate"] = df["Resgate_Total"] / (df["PL_Medio"] + 1e-9)

        return df[[
            "CNPJ_Classe",
            "Dias_Historico",
            "Patrimonio_Liquido",
            "Ultimo_Cotistas",
            "Proporcao_Resgate",
        ]]

    # -------------------------------------------------------------
    # MÉTODOS LEGADO (mantidos para compatibilidade)
    # -------------------------------------------------------------

    def buscar_por_cnpj(self, cnpj):
        return self.buscar_historico_completo(cnpj)

    def ultimo_registro(self, cnpj):
        return self.buscar_ultimo_registro(cnpj)

    def total_registros(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM informe_diario"
        ).fetchone()[0]

    def listar_cnpjs_distintos(self):
        """
        Retorna apenas os CNPJs distintos presentes no informe.
        Muito mais eficiente que listar_informe() que carrega todos os registros.
        """
        df = pd.read_sql_query(
            "SELECT DISTINCT CNPJ_Classe FROM informe_diario",
            self.conn,
        )
        return df

    def fechar(self):
        if self.conn:
            self.conn.close()

    def __del__(self):
        try:
            if getattr(self, "conn", None):
                self.conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------

_instance = None


def get_informe_coletor():
    global _instance
    if _instance is None:
        _instance = InformeDiarioColetorCVM()
    return _instance


# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------

def listar_informe():
    return get_informe_coletor().listar()


def buscar_informe(cnpj):
    return get_informe_coletor().buscar_por_cnpj(cnpj)


def buscar_historico(cnpj, limite=252):
    return get_informe_coletor().buscar_historico(cnpj, limite)


def buscar_historico_completo(cnpj):
    return get_informe_coletor().buscar_historico_completo(cnpj)


def buscar_ultimo_registro(cnpj):
    return get_informe_coletor().buscar_ultimo_registro(cnpj)


def listar_historicos(lista_cnpjs, limite=252):
    return get_informe_coletor().listar_historicos(lista_cnpjs, limite)


def listar_metricas_agregadas(lista_cnpjs):
    return get_informe_coletor().listar_metricas_agregadas(lista_cnpjs)


def total_registros():
    return get_informe_coletor().total_registros()


def listar_cnpjs_distintos():
    """Retorna DataFrame com CNPJs distintos no informe (leve e rápido)."""
    return get_informe_coletor().listar_cnpjs_distintos()


def carregar_ultimos_meses(quantidade=3):
    """Carrega os últimos N meses de Informe Diário (sempre reprocessando)."""
    return get_informe_coletor().carregar_ultimos_meses(quantidade)


def carregar_historico(anos=3, meses_recentes_forcar=3, force=False):
    """Garante N anos de histórico no banco, pulando meses antigos já carregados."""
    return get_informe_coletor().carregar_historico(anos, meses_recentes_forcar, force)


# ---------------------------------------------------------------------
# Teste rápido
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s - %(message)s",
    )

    # Carrega os últimos 3 meses
    carregar_ultimos_meses(3)

    # Testa um CNPJ
    cnpj = "00017024000153"

    try:
        df = buscar_historico(cnpj, limite=30)
        print(f"Últimos 30 registros: {len(df)}")
        if not df.empty:
            print(df[["Data_Competencia", "Valor_Cota"]].tail(5))

        ultimo = buscar_ultimo_registro(cnpj)
        if ultimo:
            print(f"\nÚltimo registro:")
            print(f"  Data: {ultimo['Data_Competencia']}")
            print(f"  Cota: {ultimo['Valor_Cota']}")
            print(f"  Patrimônio: {ultimo['Patrimonio_Liquido']}")

    except Exception as e:
        logger.exception(e)