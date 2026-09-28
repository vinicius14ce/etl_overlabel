import time
import pandas as pd
from sqlalchemy import text
from db import get_source_engine, get_dest_engine, setup_logger

logger = setup_logger("clientes")

COLUMNS = """
    atualizacao, cliente_id, cliente_pai_id, cliente_razaosocial,
    cliente_nomefantasia, cliente_bairro, cliente_cidade, cliente_uf,
    cliente_latitude, cliente_longitude, representante_id, vendedor_id,
    cliente_status_bloq_ped, cliente_status_bloq_nf, cliente_status,
    codigo_ibge, cliente_tipo_empresa, cliente_grupo, cliente_grupo_id,
    cliente_data_cadastro, regiao_id, cliente_situacao, profissional_id,
    cliente_corretor, cliente_data_aniversario, bairro_cidade_uf_pais,
    cidade_uf_pais, uf_pais, pais, colaborador_id, cliente_colaborador_id,
    cliente_observacao, cliente_forma_pagamento, cliente_condicao_pagamento,
    cliente_limite_credito, cliente_contato, cliente_telefones, cliente_email,
    cliente_segmento, cliente_magazine, cliente_disposicao
"""

def run():
    start = time.time()
    logger.info("Iniciando pipeline clientes...")

    try:
        source_engine = get_source_engine()
        dest_engine = get_dest_engine()

        select_sql = f"SELECT {COLUMNS} FROM dw.mv_clientes"

        with source_engine.connect() as conn:
            df = pd.read_sql(select_sql, conn)

        logger.info(f"Lidas {len(df)} linhas na origem")

        with dest_engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE dw.mv_clientes"))
            df.to_sql(
                name="mv_clientes",
                con=conn,
                schema="dw",
                if_exists="append",
                index=False,
                chunksize=1000
            )

        duration = time.time() - start
        logger.info(f"Pipeline clientes concluído: {len(df)} linhas inseridas em {duration:.2f}s")

    except Exception as e:
        logger.exception(f"Erro no pipeline clientes: {e}")
        raise
