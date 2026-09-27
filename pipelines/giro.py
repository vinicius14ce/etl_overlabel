import os
import time
from sqlalchemy import text
from db import get_source_engine, get_dest_engine, setup_logger

logger = setup_logger("giro")

COLUMNS = """
    atualizacao, estabelecimento_origem, loja, data_dt, data_venda, qtd_pecas,
    modelo_id, modelo, cor, tam, familia, mix, subgrupo, marca, perfil_modelo,
    conferencia, valor_unitario, valor_liquido, custo, valor_total, custo_total,
    fator_markup, pedido, tipo, operacao, codigo, numero_cfe, serie, hora_emissao,
    cod_vendedor, nome_vendedor, cliente_id, cliente_nome, uf, cidade, cfop_codigo,
    valor_desconto, promocao, promo_atac, promo_vare, preco_off, promo_off,
    produto_de_troca, tem_venda_fechada, subcliente_id
"""

def run():
    start = time.time()
    dias_carga = int(os.environ["DIAS_CARGA"])
    logger.info(f"Iniciando pipeline giro (dias_carga={dias_carga})...")

    try:
        source_engine = get_source_engine()
        dest_engine = get_dest_engine()

        select_sql = f"""
            SELECT {COLUMNS} FROM dw.mv_giro_supabase
            WHERE data_venda <= CURRENT_DATE
              AND data_venda > CURRENT_DATE - :dias_carga
        """

        with source_engine.connect() as src_conn:
            rows = src_conn.execute(
                text(select_sql),
                {"dias_carga": dias_carga}
            ).mappings().all()

        logger.info(f"Lidas {len(rows)} linhas na origem")

        delete_sql = """
            DELETE FROM dw.mv_giro_supabase
            WHERE data_venda <= CURRENT_DATE
              AND data_venda > CURRENT_DATE - :dias_carga
        """

        with dest_engine.begin() as dest_conn:
            dest_conn.execute(text(delete_sql), {"dias_carga": dias_carga})

            if rows:
                insert_sql = f"""
                    INSERT INTO dw.mv_giro_supabase ({COLUMNS})
                    VALUES (:atualizacao, :estabelecimento_origem, :loja, :data_dt, :data_venda, :qtd_pecas,
                            :modelo_id, :modelo, :cor, :tam, :familia, :mix, :subgrupo, :marca, :perfil_modelo,
                            :conferencia, :valor_unitario, :valor_liquido, :custo, :valor_total, :custo_total,
                            :fator_markup, :pedido, :tipo, :operacao, :codigo, :numero_cfe, :serie, :hora_emissao,
                            :cod_vendedor, :nome_vendedor, :cliente_id, :cliente_nome, :uf, :cidade, :cfop_codigo,
                            :valor_desconto, :promocao, :promo_atac, :promo_vare, :preco_off, :promo_off,
                            :produto_de_troca, :tem_venda_fechada, :subcliente_id)
                """
                dest_conn.execute(text(insert_sql), [dict(row) for row in rows])

        duration = time.time() - start
        logger.info(f"Pipeline giro concluído: {len(rows)} linhas inseridas em {duration:.2f}s")

    except Exception as e:
        logger.exception(f"Erro no pipeline giro: {e}")
        raise
