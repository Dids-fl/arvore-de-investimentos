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

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")

        self._criar_tabelas()

        if atualizar:
            # Carrega os últimos 3 meses por padrão
            self.carregar_ultimos_meses(3)

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
        Processa um chunk do CSV: renomeia colunas, normaliza, e insere no banco.
        """
        if chunk.empty:
            return

        # Renomeia colunas
        chunk = chunk.rename(
            columns={
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
        )

        # Seleciona apenas as colunas necessárias
        colunas = [
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
        chunk = chunk[colunas]

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

        # Converte colunas numéricas
        numericas = [
            "Valor_Total",
            "Valor_Cota",
            "Patrimonio_Liquido",
            "Captacao_Dia",
            "Resgate_Dia",
            "Numero_Cotistas",
        ]
        for col in numericas:
            chunk[col] = (
                pd.to_numeric(chunk[col], errors="coerce")
                .fillna(0)
                .clip(lower=0)
            )

        # Remove duplicatas dentro do chunk
        chunk = chunk.drop_duplicates(
            subset=["CNPJ_Classe", "Data_Competencia"],
            keep="last",
        )

        # Insere no banco (ignora duplicatas)
        chunk.to_sql(
            "informe_diario",
            self.conn,
            if_exists="append",
            index=False,
        )

    # -------------------------------------------------------------

    def atualizar_informe(
        self,
        ano=None,
        mes=None,
        force=False,
    ):
        """
        Baixa e carrega um mês específico do Informe Diário.
        Não deleta dados existentes — insere apenas os novos.
        """
        csv_path = download_informe_diario(
            ano=ano,
            mes=mes,
            force=force,
        )

        logger.info(f"Carregando Informe Diário {ano}-{mes:02d}...")

        # Lê o CSV em chunks para evitar estouro de memória
        chunk_size = 50000
        total_registros = 0

        for chunk in pd.read_csv(
            csv_path,
            sep=";",
            encoding="latin1",
            low_memory=False,
            chunksize=chunk_size,
        ):
            self._processar_chunk(chunk)
            total_registros += len(chunk)
            logger.debug(f"  Processado chunk com {len(chunk)} registros")

        logger.info(f"  {total_registros} registros inseridos para {ano}-{mes:02d}.")

    # -------------------------------------------------------------

    def carregar_ultimos_meses(self, quantidade=3):
        """
        Carrega os últimos 'quantidade' meses de Informe Diário.
        """
        from datetime import datetime, timedelta

        hoje = datetime.now()
        meses_carregados = 0

        for i in range(quantidade):
            data = hoje - timedelta(days=i * 30)
            ano, mes = data.year, data.month

            try:
                self.atualizar_informe(ano=ano, mes=mes, force=False)
                meses_carregados += 1
            except Exception as e:
                logger.warning(f"Erro ao carregar {ano}-{mes:02d}: {e}")

        logger.info(f"Carregados {meses_carregados} meses de Informe Diário.")

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
            except Exception as e:
                logger.warning(f"Erro no chunk: {e}")

        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)

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


def total_registros():
    return get_informe_coletor().total_registros()


def listar_cnpjs_distintos():
    """Retorna DataFrame com CNPJs distintos no informe (leve e rápido)."""
    return get_informe_coletor().listar_cnpjs_distintos()


def carregar_ultimos_meses(quantidade=3):
    """Carrega os últimos N meses de Informe Diário."""
    return get_informe_coletor().carregar_ultimos_meses(quantidade)


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