import time
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

        with source_engine.connect() as src_conn:
            rows = src_conn.execute(text(select_sql)).mappings().all()

        logger.info(f"Lidas {len(rows)} linhas na origem")

        with dest_engine.begin() as dest_conn:
            dest_conn.execute(text("DELETE FROM dw.mv_clientes"))

            if rows:
                insert_sql = f"""
                    INSERT INTO dw.mv_clientes ({COLUMNS})
                    VALUES (:atualizacao, :cliente_id, :cliente_pai_id, :cliente_razaosocial,
                            :cliente_nomefantasia, :cliente_bairro, :cliente_cidade, :cliente_uf,
                            :cliente_latitude, :cliente_longitude, :representante_id, :vendedor_id,
                            :cliente_status_bloq_ped, :cliente_status_bloq_nf, :cliente_status,
                            :codigo_ibge, :cliente_tipo_empresa, :cliente_grupo, :cliente_grupo_id,
                            :cliente_data_cadastro, :regiao_id, :cliente_situacao, :profissional_id,
                            :cliente_corretor, :cliente_data_aniversario, :bairro_cidade_uf_pais,
                            :cidade_uf_pais, :uf_pais, :pais, :colaborador_id, :cliente_colaborador_id,
                            :cliente_observacao, :cliente_forma_pagamento, :cliente_condicao_pagamento,
                            :cliente_limite_credito, :cliente_contato, :cliente_telefones, :cliente_email,
                            :cliente_segmento, :cliente_magazine, :cliente_disposicao)
                """
                dest_conn.execute(text(insert_sql), [dict(row) for row in rows])

        duration = time.time() - start
        logger.info(f"Pipeline clientes concluído: {len(rows)} linhas inseridas em {duration:.2f}s")

    except Exception as e:
        logger.exception(f"Erro no pipeline clientes: {e}")
        raise
