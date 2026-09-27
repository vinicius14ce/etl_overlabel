import time
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

        with source_engine.connect() as src_conn:
            rows = src_conn.execute(text(select_sql)).mappings().all()

        logger.info(f"Lidas {len(rows)} linhas na origem")

        with dest_engine.begin() as dest_conn:
            dest_conn.execute(text("DELETE FROM dw.mv_estoque"))

            if rows:
                insert_sql = f"""
                    INSERT INTO dw.mv_estoque ({COLUMNS})
                    VALUES (:atualizacao, :localizacao_id, :modelo_id, :loja, :familia, :modelo,
                            :cor, :tamanho, :mix, :subgrupo, :fabricacao, :marca, :perfil_modelo,
                            :estoque, :custo, :atacado, :varejo, :promo_atac, :promo_vare, :preco_off, :promo_off)
                """
                dest_conn.execute(text(insert_sql), [dict(row) for row in rows])

        duration = time.time() - start
        logger.info(f"Pipeline estoque concluído: {len(rows)} linhas inseridas em {duration:.2f}s")

    except Exception as e:
        logger.exception(f"Erro no pipeline estoque: {e}")
        raise
