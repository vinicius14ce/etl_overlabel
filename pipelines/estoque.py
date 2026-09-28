import time
import pandas as pd
from sqlalchemy import text
from db import get_source_engine, get_dest_engine, setup_logger

logger = setup_logger("estoque")

COLUMNS = """
    atualizacao, localizacao_id, modelo_id, loja, familia, modelo,
    cor, tamanho, mix, subgrupo, fabricacao, marca, perfil_modelo,
    estoque, custo, atacado, varejo, promo_atac, promo_vare, preco_off, promo_off
"""

def run():
    start = time.time()
    logger.info("Iniciando pipeline estoque...")

    try:
        source_engine = get_source_engine()
        dest_engine = get_dest_engine()

        select_sql = f"SELECT {COLUMNS} FROM dw.mv_estoque"

        with source_engine.connect() as conn:
            df = pd.read_sql(select_sql, conn)

        logger.info(f"Lidas {len(df)} linhas na origem")

        with dest_engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE dw.mv_estoque"))
            df.to_sql(
                name="mv_estoque",
                con=conn,
                schema="dw",
                if_exists="append",
                index=False,
                chunksize=1000
            )

        duration = time.time() - start
        logger.info(f"Pipeline estoque concluído: {len(df)} linhas inseridas em {duration:.2f}s")

    except Exception as e:
        logger.exception(f"Erro no pipeline estoque: {e}")
        raise
