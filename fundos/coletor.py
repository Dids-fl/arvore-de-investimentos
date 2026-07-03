# fundos/coletor.py
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from .cvm_sqlite import CVMDataProcessor

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "cvm_data.db"
CVM_URL_FUNDOS = "https://dados.cvm.gov.br/dados/FI"


class ColetorFundosCVM:
    def __init__(self, db_path=None, cvm_url=None):
        self.db_path = str(db_path or DB_PATH)
        self.cvm_url = CVM_URL_FUNDOS
        self.processor = None
        self._inicializar()

    def _inicializar(self):
        logger.info(f"Inicializando CVMDataProcessor com URL: {self.cvm_url}")
        # Remove banco residual para garantir uma base limpa (opcional, mas recomendado)
        db_file = Path(self.db_path)
        if db_file.exists():
            try:
                db_file.unlink(missing_ok=True)
                logger.info("Banco residual removido para evitar inconsistências.")
            except Exception as e:
                logger.warning(f"Não foi possível remover banco residual: {e}")

        self.processor = CVMDataProcessor(
            db_path=self.db_path,
            cvm_url=self.cvm_url,
            verbose=False
        )
        self.processor.run()
        logger.info("Processamento CVM concluído.")

    def listar_fundos(self, limit=1000):
        """
        Retorna DataFrame com fundos ativos a partir do atributo processado.
        """
        try:
            # Tenta acessar o DataFrame de cadastro (pode estar em self.processor.fi_cad_fi ou similar)
            df = getattr(self.processor, 'fi_cad_fi', None)
            if df is None:
                # Fallback: tenta acessar via propriedade 'cad_fi' ou outros nomes
                df = getattr(self.processor, 'cad_fi', None)
            if df is None:
                # Último recurso: tenta buscar no banco via SQL (mas com nome correto)
                logger.warning("DataFrame de cadastro não encontrado no processador. Tentando via SQL...")
                conn = self.processor.db.conn
                # Descobre qual tabela de cadastro existe
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%cad%' OR name LIKE '%fi%')")
                tables = cursor.fetchall()
                for (table_name,) in tables:
                    if 'cad' in table_name.lower() or 'fi' in table_name.lower():
                        df = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT {limit}", conn)
                        break
                if df is None:
                    logger.error("Não foi possível localizar tabela de cadastro.")
                    return pd.DataFrame()

            if df.empty:
                return df

            # Filtra fundos ativos (coluna pode ser 'SIT' ou 'SITUACAO')
            sit_col = None
            for col in df.columns:
                if col.upper() in ('SIT', 'SITUACAO'):
                    sit_col = col
                    break
            if sit_col:
                df = df[df[sit_col] == 'EM FUNCIONAMENTO NORMAL']

            df = df.head(limit)
            logger.info(f"Cadastro carregado: {len(df)} fundos ativos.")
            return df

        except Exception as e:
            logger.error(f"Erro em listar_fundos: {e}")
            return pd.DataFrame()

    def buscar_cotas_em_lote(self, lista_cnpjs, dias=365):
        """
        Retorna cotas de múltiplos fundos a partir do DataFrame de inf_diario_fi.
        """
        if not lista_cnpjs:
            return pd.DataFrame()

        try:
            # Tenta acessar o DataFrame de informes diários
            df_cotas = getattr(self.processor, 'fi_inf_diario_fi', None)
            if df_cotas is None:
                df_cotas = getattr(self.processor, 'inf_diario_fi', None)
            if df_cotas is None:
                logger.warning("DataFrame de cotas não encontrado. Tentando via SQL...")
                conn = self.processor.db.conn
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%inf_diario%'")
                tables = cursor.fetchall()
                if not tables:
                    logger.error("Nenhuma tabela de cotas encontrada.")
                    return pd.DataFrame()
                # Usa a primeira tabela de cotas
                table_name = tables[0][0]
                df_cotas = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

            if df_cotas.empty:
                return df_cotas

            # Filtra pelos CNPJs e pelo período
            data_corte = datetime.now() - timedelta(days=dias)
            df_cotas = df_cotas[df_cotas['CNPJ_FUNDO'].isin(lista_cnpjs)]
            df_cotas['DT_COMPTC'] = pd.to_datetime(df_cotas['DT_COMPTC'])
            df_cotas = df_cotas[df_cotas['DT_COMPTC'] >= data_corte]
            df_cotas = df_cotas.sort_values(['CNPJ_FUNDO', 'DT_COMPTC'])
            logger.info(f"Cotas carregadas: {len(df_cotas)} registros.")
            return df_cotas

        except Exception as e:
            logger.error(f"Erro em buscar_cotas_em_lote: {e}")
            return pd.DataFrame()


# Singleton
_coletor_instance = None

def get_coletor():
    global _coletor_instance
    if _coletor_instance is None:
        _coletor_instance = ColetorFundosCVM()
    return _coletor_instance

def listar_fundos(limit=1000):
    return get_coletor().listar_fundos(limit)

def buscar_cotas_em_lote(lista_cnpjs, dias=365):
    return get_coletor().buscar_cotas_em_lote(lista_cnpjs, dias)