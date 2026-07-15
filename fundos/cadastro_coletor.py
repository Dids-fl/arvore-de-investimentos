# fundos/cadastro_coletor.py

from pathlib import Path
import logging
import sqlite3

import pandas as pd

from .cvm_cadastro_downloader import download_cadastro

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).parent

DB_PATH = BASE_DIR / "data" / "fundos_cache.db"


# ---------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------


class ColetorFundosCVM:
    def __init__(
        self,
        db_path=None,
        atualizar=True,
    ):
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # Melhor desempenho do SQLite
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")

        self._criar_tabelas()

        if atualizar:
            self.atualizar_cadastro()

    # -------------------------------------------------------------

    def _criar_tabelas(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cad_fi(
                CNPJ_Classe TEXT PRIMARY KEY,
                Denominacao_Social TEXT,
                Situacao TEXT,
                Tipo_Classe TEXT,
                Classificacao TEXT,
                Classificacao_Anbima TEXT,
                Indicador_Desempenho TEXT,
                Publico_Alvo TEXT,
                Classe_ESG TEXT,
                Forma_Condominio TEXT,
                Patrimonio_Liquido REAL,
                Data_Registro TEXT,
                Data_Inicio TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_nome
            ON cad_fi(Denominacao_Social)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_classe
            ON cad_fi(Classificacao_Anbima)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_situacao
            ON cad_fi(Situacao)
            """
        )

        self.conn.commit()

    # -------------------------------------------------------------

    def atualizar_cadastro(
        self,
        force=False,
    ):
        csv_path = download_cadastro(force=force)

        logger.info("Carregando cadastro da CVM...")

        df = pd.read_csv(
            csv_path,
            sep=";",
            encoding="latin1",
            low_memory=False,
        )

        colunas = [
            "CNPJ_Classe",
            "Denominacao_Social",
            "Situacao",
            "Tipo_Classe",
            "Classificacao",
            "Classificacao_Anbima",
            "Indicador_Desempenho",
            "Publico_Alvo",
            "Classe_ESG",
            "Forma_Condominio",
            "Patrimonio_Liquido",
            "Data_Registro",
            "Data_Inicio",
        ]

        existentes = [
            coluna
            for coluna in colunas
            if coluna in df.columns
        ]

        df = df[existentes]
        df = df.dropna(subset=["CNPJ_Classe"])
        df = df.drop_duplicates(
            subset="CNPJ_Classe",
            keep="first",
        )

        # Garante que o CNPJ seja sempre texto
        df["CNPJ_Classe"] = (
            df["CNPJ_Classe"]
            .astype(str)
            .str.zfill(14)
        )

        df["Patrimonio_Liquido"] = (
            pd.to_numeric(
                df["Patrimonio_Liquido"],
                errors="coerce",
            )
            .fillna(0)
            .clip(lower=0)
        )

        with self.conn:
            self.conn.execute("DELETE FROM cad_fi")
            df.to_sql(
                "cad_fi",
                self.conn,
                if_exists="append",
                index=False,
            )

        logger.info("%d fundos carregados.", len(df))

    # -------------------------------------------------------------

    def listar_fundos(self):
        query = """
        SELECT *
        FROM cad_fi
        """

        return pd.read_sql_query(query, self.conn)

    # -------------------------------------------------------------

    def listar_fundos_ativos(self):
        query = """
        SELECT *
        FROM cad_fi
        WHERE upper(Situacao) = 'EM FUNCIONAMENTO NORMAL'
        """

        return pd.read_sql_query(query, self.conn)

    # -------------------------------------------------------------

    def buscar_por_nome(self, texto):
        query = """
        SELECT *
        FROM cad_fi
        WHERE upper(Denominacao_Social) LIKE upper(?)
        ORDER BY Denominacao_Social
        """

        return pd.read_sql_query(
            query,
            self.conn,
            params=(f"%{texto}%",),
        )

    # -------------------------------------------------------------

    def buscar_por_cnpj(self, cnpj):
        cnpj = str(cnpj).zfill(14)

        query = """
        SELECT *
        FROM cad_fi
        WHERE CNPJ_Classe=?
        """

        df = pd.read_sql_query(query, self.conn, params=(cnpj,))

        if df.empty:
            return None

        return df.iloc[0].to_dict()

    # -------------------------------------------------------------

    def listar_por_classe(self, classe):
        query = """
        SELECT *
        FROM cad_fi
        WHERE upper(Classificacao_Anbima) LIKE upper(?)
           OR upper(Classificacao) LIKE upper(?)
        ORDER BY Patrimonio_Liquido DESC
        """

        return pd.read_sql_query(
            query,
            self.conn,
            params=(f"%{classe}%", f"%{classe}%"),
        )

    # -------------------------------------------------------------

    def total_fundos(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cad_fi")
        return cursor.fetchone()[0]

    # -------------------------------------------------------------

    def fechar(self):
        if self.conn:
            self.conn.close()

    # -------------------------------------------------------------

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


def get_coletor():
    global _instance
    if _instance is None:
        _instance = ColetorFundosCVM()
    return _instance


# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------

def listar_fundos():
    return get_coletor().listar_fundos()


def listar_fundos_ativos():
    return get_coletor().listar_fundos_ativos()


def buscar_por_nome(nome):
    return get_coletor().buscar_por_nome(nome)


def buscar_por_cnpj(cnpj):
    return get_coletor().buscar_por_cnpj(cnpj)


def listar_por_classe(classe):
    return get_coletor().listar_por_classe(classe)


def total_fundos():
    return get_coletor().total_fundos()