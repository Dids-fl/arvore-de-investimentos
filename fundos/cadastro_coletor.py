# fundos/cadastro_coletor.py

from pathlib import Path
import logging
import sqlite3
import threading

import pandas as pd

from .cvm_cadastro_downloader import download_cadastro

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).parent

DB_PATH = BASE_DIR / "data" / "fundos_cache.db"

# Caminho do CSV de subclasses, usado para identificar subclasses
# previdenciárias (campo Previdenciario = 'S').
SUBCLASSE_CSV_PATH = BASE_DIR / "data" / "registro_subclasse.csv"


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

        # DEBUG
        print("=" * 100)
        print(f"Banco SQLite: {self.db_path.resolve()}")
        print("=" * 100)

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

        # Tabela principal: fundos NÃO previdenciários (herda comportamento antigo)
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

        # Tabela irmã: apenas fundos previdenciários
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cad_fi_previdenciario(
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
            CREATE INDEX IF NOT EXISTS idx_nome_prev
            ON cad_fi_previdenciario(Denominacao_Social)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_situacao_prev
            ON cad_fi_previdenciario(Situacao)
            """
        )

        self.conn.commit()

    # -------------------------------------------------------------

    def _carregar_cnpjs_previdenciarios(self, df_cad, subclasse_csv_path):
        """
        Retorna um set com os CNPJ_Classe que atendem a pelo menos um dos
        critérios:

        1. Possui subclasse previdenciária (Previdenciario = 'S' em
           registro_subclasse.csv, cruzando via ID_Registro_Classe).
        2. Classificacao_Anbima contém a substring "Previd"
           (case-insensitive, ex: "Previdência Multimercado").

        Se não for possível ler o arquivo de subclasses ou se não houver
        a coluna necessária, o critério 1 é ignorado e apenas o critério 2
        é aplicado. Se ambos falharem, retorna set vazio (não filtra nada).
        """
        cnpjs = set()

        # ---------------------------------------------------------
        # Critério 1: subclasse previdenciária (registro_subclasse.csv)
        # ---------------------------------------------------------
        subclasse_csv_path = Path(subclasse_csv_path)
        if subclasse_csv_path.exists():
            try:
                df_sub = pd.read_csv(
                    subclasse_csv_path,
                    sep=";",
                    encoding="latin1",
                    low_memory=False,
                )

                colunas_necessarias = {"ID_Registro_Classe", "Previdenciario"}
                if colunas_necessarias.issubset(df_sub.columns):
                    df_sub["Previdenciario"] = (
                        df_sub["Previdenciario"]
                        .astype(str)
                        .str.strip()
                        .str.upper()
                    )

                    ids_prev = set(
                        df_sub.loc[
                            df_sub["Previdenciario"] == "S",
                            "ID_Registro_Classe",
                        ]
                    )

                    if "ID_Registro_Classe" in df_cad.columns:
                        cnpjs.update(
                            df_cad.loc[
                                df_cad["ID_Registro_Classe"].isin(ids_prev),
                                "CNPJ_Classe",
                            ]
                            .dropna()
                            .astype(str)
                            .str.zfill(14)
                            .tolist()
                        )
                        logger.info(
                            "Critério subclasse: %d CNPJs identificados como previdenciários.",
                            len(cnpjs),
                        )
                    else:
                        logger.warning(
                            "Coluna ID_Registro_Classe ausente no cadastro. "
                            "Ignorando critério de subclasse."
                        )
                else:
                    logger.warning(
                        "registro_subclasse.csv não possui as colunas esperadas "
                        "(ID_Registro_Classe, Previdenciario). Ignorando critério de subclasse."
                    )
            except Exception as e:
                logger.warning(
                    f"Erro ao processar registro_subclasse.csv: {e}. "
                    "Ignorando critério de subclasse."
                )
        else:
            logger.warning(
                f"Arquivo de subclasses não encontrado em {subclasse_csv_path}. "
                "Ignorando critério de subclasse."
            )

        # ---------------------------------------------------------
        # Critério 2: Classificacao_Anbima contém "Previd"
        # ---------------------------------------------------------
        if "Classificacao_Anbima" in df_cad.columns:
            mask = df_cad["Classificacao_Anbima"].astype(str).str.contains(
                "Previd", case=False, na=False
            )
            cnpjs_anbima = set(
                df_cad.loc[mask, "CNPJ_Classe"]
                .dropna()
                .astype(str)
                .str.zfill(14)
                .tolist()
            )
            logger.info(
                "Critério Classificacao_Anbima: %d CNPJs contêm 'Previd'.",
                len(cnpjs_anbima),
            )
            cnpjs.update(cnpjs_anbima)
        else:
            logger.warning(
                "Coluna Classificacao_Anbima não encontrada no cadastro. "
                "Ignorando critério de classificação ANBIMA."
            )

        logger.info("Total de CNPJs previdenciários identificados: %d", len(cnpjs))
        return cnpjs

    # -------------------------------------------------------------

    def atualizar_cadastro(
        self,
        force=False,
        subclasse_csv_path=None,
    ):
        csv_path = download_cadastro(force=force)
        subclasse_csv_path = Path(subclasse_csv_path or SUBCLASSE_CSV_PATH)

        logger.info("Carregando cadastro da CVM...")

        df = pd.read_csv(
            csv_path,
            sep=";",
            encoding="latin1",
            low_memory=False,
        )

        colunas = [
            "CNPJ_Classe",
            "ID_Registro_Classe",       # necessário para critério de subclasse
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

        # -----------------------------------------------------
        # Separação: previdenciários vs não previdenciários
        # -----------------------------------------------------
        cnpjs_previdenciarios = self._carregar_cnpjs_previdenciarios(df, subclasse_csv_path)
        df = df.drop(columns=["ID_Registro_Classe"], errors="ignore")

        if cnpjs_previdenciarios:
            df_previdenciario = df[
                df["CNPJ_Classe"].isin(cnpjs_previdenciarios)
            ].copy()
            df_nao_previdenciario = df[
                ~df["CNPJ_Classe"].isin(cnpjs_previdenciarios)
            ].copy()
        else:
            # Se não encontrou nenhum critério, mantém o comportamento antigo:
            # tudo vai para cad_fi (não previdenciário), tabela irmã vazia.
            df_previdenciario = df.iloc[0:0].copy()
            df_nao_previdenciario = df

        with self.conn:
            print(df_nao_previdenciario.columns.tolist())
            self.conn.execute("DELETE FROM cad_fi")
            df_nao_previdenciario.to_sql(
                "cad_fi",
                self.conn,
                if_exists="append",
                index=False,
            )

            self.conn.execute("DELETE FROM cad_fi_previdenciario")
            df_previdenciario.to_sql(
                "cad_fi_previdenciario",
                self.conn,
                if_exists="append",
                index=False,
            )

        logger.info(
            "%d fundos carregados (%d não previdenciários em cad_fi, "
            "%d previdenciários em cad_fi_previdenciario).",
            len(df),
            len(df_nao_previdenciario),
            len(df_previdenciario),
        )

    # -------------------------------------------------------------

    def listar_fundos(self, limit=None):
        query = "SELECT * FROM cad_fi"
        if limit is not None:
            query += f" LIMIT {limit}"
        return pd.read_sql_query(query, self.conn)

    # -------------------------------------------------------------

    def listar_fundos_ativos(self, limit=None):
        query = """
        SELECT *
        FROM cad_fi
        WHERE upper(Situacao) = 'EM FUNCIONAMENTO NORMAL'
        """
        if limit is not None:
            query += f" LIMIT {limit}"
        return pd.read_sql_query(query, self.conn)

    # -------------------------------------------------------------

    def listar_fundos_ativos_previdenciario(self, limit=None):
        query = """
        SELECT *
        FROM cad_fi_previdenciario
        WHERE upper(Situacao) = 'EM FUNCIONAMENTO NORMAL'
        """
        if limit is not None:
            query += f" LIMIT {limit}"
        return pd.read_sql_query(query, self.conn)

    # -------------------------------------------------------------

    def listar_fundos_previdenciarios(self, limit=None):
        """Saída com Previdenciario == 'S' (tabela cad_fi_previdenciario)."""
        query = "SELECT * FROM cad_fi_previdenciario"
        if limit is not None:
            query += f" LIMIT {limit}"
        return pd.read_sql_query(query, self.conn)

    # -------------------------------------------------------------

    def buscar_por_cnpj_previdenciario(self, cnpj):
        cnpj = str(cnpj).zfill(14)

        query = """
        SELECT *
        FROM cad_fi_previdenciario
        WHERE CNPJ_Classe=?
        """

        df = pd.read_sql_query(query, self.conn, params=(cnpj,))

        if df.empty:
            return None

        return df.iloc[0].to_dict()

    # -------------------------------------------------------------

    def total_fundos_previdenciarios(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cad_fi_previdenciario")
        return cursor.fetchone()[0]

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
_lock = threading.Lock()


def get_coletor():
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:  # double-checked locking
                _instance = ColetorFundosCVM()
    return _instance


# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------

def listar_fundos(limit=None):
    return get_coletor().listar_fundos(limit)


def listar_fundos_ativos(limit=None):
    return get_coletor().listar_fundos_ativos(limit)


def listar_fundos_ativos_previdenciario(limit=None):
    return get_coletor().listar_fundos_ativos_previdenciario(limit)


def listar_fundos_previdenciarios(limit=None):
    return get_coletor().listar_fundos_previdenciarios(limit)


def buscar_por_cnpj_previdenciario(cnpj):
    return get_coletor().buscar_por_cnpj_previdenciario(cnpj)


def total_fundos_previdenciarios():
    return get_coletor().total_fundos_previdenciarios()


def buscar_por_nome(nome):
    return get_coletor().buscar_por_nome(nome)


def buscar_por_cnpj(cnpj):
    return get_coletor().buscar_por_cnpj(cnpj)


def listar_por_classe(classe):
    return get_coletor().listar_por_classe(classe)


def total_fundos():
    return get_coletor().total_fundos()